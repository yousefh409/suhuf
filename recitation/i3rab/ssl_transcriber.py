"""SSL CTC transcriber and scorer (HuggingFace wav2vec2 / w2v-bert).

Drop-in replacement for PCDTranscriber that uses HuggingFace SSL models
instead of NeMo FastConformer. Provides the same interface:
- encode(audio) → (log_probs, encoded_len, encoded)
- greedy_decode / transcribe / transcribe_and_encode
- _ctc_score / _ctc_score_segment
- forced_align_reference / get_word_boundaries
- score_word_in_context / score_word_segmented
- decode_word_segment
"""

import numpy as np
import torch
import torch.nn.functional as F
from pathlib import Path
from torchaudio.functional import forced_align

from .config import Config
from .models import BookWord, ScoredWord, Confidence
from .pcd_transcriber import WordBoundary


class SSLTranscriber:
    """Transcribes and scores Arabic audio using HuggingFace SSL CTC models."""

    def __init__(self, config: Config | None = None, model_dir: str | None = None):
        self.config = config or Config()
        self.model_dir = model_dir
        self.model = None
        self.tokenizer = None
        self.feature_extractor = None
        self._loaded = False
        self._ctc_loss_fn = None
        self._blank_id = None
        self._is_w2v_bert = False
        # The training sample rate — models trained with v1 script used 40100Hz
        # (resampling bug), v2+ uses 16000Hz. Read from config.
        self._training_sr = getattr(config, "ssl_training_sr", 16000)

    def load(self):
        """Load the HuggingFace SSL CTC model."""
        if self._loaded:
            return

        from transformers import (
            Wav2Vec2ForCTC, Wav2Vec2Processor,
            Wav2Vec2BertForCTC, SeamlessM4TFeatureExtractor, AutoTokenizer,
        )

        model_dir = self.model_dir
        if not model_dir:
            raise ValueError("model_dir not set for SSLTranscriber")

        path = Path(model_dir)
        if not path.exists():
            raise FileNotFoundError(f"SSL model not found: {path}")

        # Detect model type from config
        from transformers import AutoConfig
        model_config = AutoConfig.from_pretrained(str(path))
        self._is_w2v_bert = "wav2vec2-bert" in model_config.model_type.lower()

        print(f"Loading SSL model from {model_dir} ({'w2v-bert' if self._is_w2v_bert else 'wav2vec2'})...")

        if self._is_w2v_bert:
            self.feature_extractor = SeamlessM4TFeatureExtractor.from_pretrained(str(path))
            self.tokenizer = AutoTokenizer.from_pretrained(str(path))
            self.model = Wav2Vec2BertForCTC.from_pretrained(str(path))
        else:
            processor = Wav2Vec2Processor.from_pretrained(str(path))
            self.tokenizer = processor.tokenizer
            self.feature_extractor = processor.feature_extractor
            self.model = Wav2Vec2ForCTC.from_pretrained(str(path))

        self.model.eval()

        # Device
        device = self.config.device
        if device == "auto":
            if torch.cuda.is_available():
                device = "cuda"
            elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
                device = "mps"
            else:
                device = "cpu"
        self._device = device
        self.model = self.model.to(device)

        # CTC blank = pad_token_id
        self._blank_id = self.model.config.pad_token_id
        self._ctc_loss_fn = torch.nn.CTCLoss(
            blank=self._blank_id, reduction="none", zero_infinity=True
        )

        self._loaded = True
        print(f"SSL model loaded. Vocab={self.model.config.vocab_size}, blank={self._blank_id}, device={device}")

    def _resample_to_training_sr(self, audio: np.ndarray) -> np.ndarray:
        """Resample from pipeline sample rate (16kHz) to training sample rate (40100Hz).

        The SSL models were trained on ClArTTS audio at 40100Hz without resampling.
        The training code passed 40100Hz audio to the feature extractor claiming it
        was 16kHz. To match this behavior, we upsample pipeline audio to 40100Hz
        and then pass it as 16kHz to the feature extractor.

        When _training_sr == 16000 (properly retrained model), this is a no-op.
        """
        if self.config.sample_rate == self._training_sr:
            return audio
        from scipy.signal import resample
        n_samples = int(len(audio) * self._training_sr / self.config.sample_rate)
        return resample(audio, n_samples).astype(np.float32)

    def _tokenize(self, text: str) -> list[int]:
        """Tokenize text using HF tokenizer (| as word separator)."""
        text_with_delim = text.replace(" ", "|")
        encoding = self.tokenizer(text_with_delim, return_tensors=None)
        return encoding["input_ids"]

    # ── Encoder + log-probs ────────────────────────────────────────────

    def encode(self, audio: np.ndarray):
        """Run encoder → frame-level log-probs.

        Returns (log_probs, encoded_len, encoded):
            log_probs:   [1, T_frames, vocab_size]
            encoded_len: [1]
            encoded:     None (no RNN-T decoder for SSL models)
        """
        self.load()

        # Resample to match training conditions (upsample 16kHz → 40100Hz if needed)
        audio = self._resample_to_training_sr(audio)

        # Feature extractor validates sampling_rate. During training, 40100Hz audio
        # was passed with sampling_rate=16000 (a bug). We must match this behavior:
        # pass the upsampled audio but claim it's 16000Hz.
        declared_sr = 16000  # always tell the feature extractor 16kHz

        if self._is_w2v_bert:
            inputs = self.feature_extractor(
                audio, sampling_rate=declared_sr, return_tensors="pt"
            )
            input_features = inputs["input_features"].to(self._device)
            attention_mask = torch.ones(
                input_features.shape[:2], dtype=torch.long, device=self._device
            )
            with torch.no_grad():
                logits = self.model(
                    input_features=input_features,
                    attention_mask=attention_mask,
                ).logits
        else:
            inputs = self.feature_extractor(
                audio, sampling_rate=declared_sr, return_tensors="pt"
            )
            input_values = inputs["input_values"].to(self._device)
            with torch.no_grad():
                logits = self.model(input_values).logits

        # Apply log_softmax to get log-probabilities
        log_probs = F.log_softmax(logits, dim=-1)  # [1, T, V]
        encoded_len = torch.tensor([log_probs.shape[1]], dtype=torch.long)

        return log_probs, encoded_len, None

    # ── Free transcription ──────────────────────────────────────────

    def greedy_decode(self, log_probs, encoded_len) -> str:
        """Greedy CTC decode: argmax per frame, collapse repeats, remove blanks."""
        T = encoded_len[0].item()
        preds = log_probs[0, :T].argmax(dim=-1).tolist()

        collapsed = []
        prev = None
        for p in preds:
            if p != prev:
                if p != self._blank_id:
                    collapsed.append(p)
                prev = p

        if not collapsed:
            return ""
        return self.tokenizer.decode(collapsed).replace("|", " ").strip()

    def transcribe(self, audio: np.ndarray) -> str:
        """Transcribe audio to diacritized Arabic text."""
        log_probs, encoded_len, _ = self.encode(audio)
        return self.greedy_decode(log_probs, encoded_len)

    def transcribe_and_encode(self, audio: np.ndarray):
        """Single encoder pass: returns (transcript, log_probs, encoded_len, encoded)."""
        log_probs, encoded_len, encoded = self.encode(audio)
        transcript = self.greedy_decode(log_probs, encoded_len)
        return transcript, log_probs, encoded_len, encoded

    # ── CTC hypothesis scoring ──────────────────────────────────────

    def _ctc_score(self, log_probs, encoded_len, text: str) -> float:
        """Score a text hypothesis using CTC log-probability.

        Returns negative CTC loss (higher = better match).
        """
        token_ids = self._tokenize(text)
        if not token_ids:
            return float("-inf")

        # CTC loss not implemented on MPS — always compute on CPU
        lp = log_probs.cpu().transpose(0, 1)  # [T, B, C]
        targets = torch.tensor([token_ids])
        target_len = torch.tensor([len(token_ids)])
        enc_len = encoded_len.cpu()

        with torch.no_grad():
            loss = self._ctc_loss_fn(lp, targets, enc_len, target_len)

        return -loss.item()

    def _ctc_score_segment(
        self, log_probs, start_frame: int, end_frame: int, text: str
    ) -> float:
        """Score a text hypothesis using CTC on a frame segment only."""
        token_ids = self._tokenize(text)
        if not token_ids:
            return float("-inf")
        seg = log_probs[:, start_frame:end_frame, :]
        seg_len = torch.tensor([seg.shape[1]])
        if seg_len.item() < len(token_ids):
            return float("-inf")
        # CTC loss on CPU (not implemented on MPS)
        lp = seg.cpu().transpose(0, 1)
        targets = torch.tensor([token_ids])
        target_len = torch.tensor([len(token_ids)])
        with torch.no_grad():
            loss = self._ctc_loss_fn(lp, targets, seg_len, target_len)
        return -loss.item()

    def _posterior_ratio(
        self,
        log_probs,
        start_frame: int,
        end_frame: int,
        ref_word: str,
        hyp_word: str,
    ) -> float:
        """Compare ref vs hyp using frame-level posteriors."""
        ref_ids = self._tokenize(ref_word)
        hyp_ids = self._tokenize(hyp_word)
        if not ref_ids or not hyp_ids:
            return 0.0

        seg = log_probs[0, start_frame:end_frame, :]
        T_seg = seg.shape[0]
        if T_seg == 0:
            return 0.0

        with torch.no_grad():
            ref_ids_t = torch.tensor(ref_ids, dtype=torch.long, device=seg.device)
            hyp_ids_t = torch.tensor(hyp_ids, dtype=torch.long, device=seg.device)
            ref_scores = seg[:, ref_ids_t].max(dim=1).values
            hyp_scores = seg[:, hyp_ids_t].max(dim=1).values
            diff = (hyp_scores - ref_scores).mean().item()

        return diff

    # ── Forced alignment ───────────────────────────────────────────

    def forced_align_reference(self, log_probs, encoded_len, reference_text: str):
        """Force-align reference text to CTC log-probs.

        Returns (alignment, scores):
            alignment: [1, T] — token label per frame
            scores:    [1, T] — log-prob at each frame
        """
        token_ids = self._tokenize(reference_text)
        if not token_ids:
            return None, None

        T = encoded_len[0].item()
        if T < len(token_ids):
            return None, None

        # forced_align needs CPU tensors or matching device
        targets = torch.tensor([token_ids], dtype=torch.int32)
        input_lengths = encoded_len.to(torch.int32)
        target_lengths = torch.tensor([len(token_ids)], dtype=torch.int32)

        # forced_align requires log_probs on CPU
        lp = log_probs.cpu() if log_probs.device.type != "cpu" else log_probs

        with torch.no_grad():
            alignment, scores = forced_align(
                lp,
                targets,
                input_lengths=input_lengths,
                target_lengths=target_lengths,
                blank=self._blank_id,
            )

        return alignment, scores

    def get_word_boundaries(
        self,
        alignment,
        scores,
        reference_words: list[str],
    ) -> list[WordBoundary]:
        """Map forced-alignment output to per-word frame boundaries."""
        if alignment is None:
            return []

        # Build token→word map from full reference text (including | separators)
        # to match what forced_align_reference() tokenized.
        full_text = " ".join(reference_words)
        full_tokens = self._tokenize(full_text)

        # Map each token to its word index. The | separator token sits between
        # words and is assigned to word -1 (ignored).
        sep_id = self.tokenizer.convert_tokens_to_ids("|")
        token_to_word = []
        wi = 0
        for tok_id in full_tokens:
            if tok_id == sep_id:
                token_to_word.append(-1)  # separator, not a word
                wi += 1
            else:
                token_to_word.append(min(wi, len(reference_words) - 1))

        align_path = alignment[0].tolist()
        frame_scores = scores[0].tolist()

        word_frames: dict[int, list[tuple[int, float]]] = {}
        target_pos = -1
        prev_label = self._blank_id

        for t, label in enumerate(align_path):
            if label == self._blank_id:
                prev_label = self._blank_id
                continue

            if label == prev_label:
                pass
            else:
                target_pos += 1
                while (
                    target_pos < len(full_tokens)
                    and full_tokens[target_pos] != label
                ):
                    target_pos += 1

            if 0 <= target_pos < len(token_to_word):
                wi = token_to_word[target_pos]
                if wi >= 0:  # skip separator tokens
                    word_frames.setdefault(wi, []).append(
                        (t, frame_scores[t])
                    )

            prev_label = label

        boundaries = []
        for wi in range(len(reference_words)):
            if wi in word_frames:
                frames = word_frames[wi]
                start = frames[0][0]
                end = frames[-1][0] + 1
                mean_score = sum(s for _, s in frames) / len(frames)
                boundaries.append(WordBoundary(wi, start, end, mean_score))
            else:
                boundaries.append(WordBoundary(wi, 0, 0, float("-inf")))

        return boundaries

    # ── Segment decoding ─────────────────────────────────────────

    def decode_word_segment(self, log_probs, start_frame: int, end_frame: int) -> str:
        """Greedy CTC decode on a single word's frame segment."""
        if start_frame >= end_frame:
            return ""
        segment = log_probs[:, start_frame:end_frame, :]
        seg_len = torch.tensor([end_frame - start_frame])
        return self.greedy_decode(segment, seg_len)

    # ── High-level scoring ─────────────────────────────────────────

    def score_word_in_context(
        self,
        log_probs,
        encoded_len,
        target_word: BookWord,
        all_words: list[BookWord],
        encoded=None,
        rnnt_weight: float = 0.0,
    ) -> ScoredWord:
        """Score a word's i3rab hypotheses using full-sentence scoring."""
        if len(target_word.hypotheses) <= 1:
            hyp = target_word.hypotheses[0] if target_word.hypotheses else None
            return ScoredWord(
                word=target_word,
                detected_hyp=hyp,
                confidence=Confidence.HIGH,
                score_gap=float("inf"),
            )

        context_parts = [w.correct_diac for w in all_words]
        target_pos = next(
            i for i, w in enumerate(all_words) if w.index == target_word.index
        )

        scored = []
        for hyp in target_word.hypotheses:
            parts = list(context_parts)
            parts[target_pos] = hyp.diacritized
            full_text = " ".join(parts)
            sc = self._ctc_score(log_probs, encoded_len, full_text)
            scored.append((sc, hyp))

        scored.sort(key=lambda x: x[0], reverse=True)

        best_score, best_hyp = scored[0]
        second_score = scored[1][0] if len(scored) > 1 else float("-inf")
        gap = best_score - second_score

        lc_thresh = getattr(self.config, "low_confidence_threshold", 1.5)
        high_thresh = lc_thresh + 0.5

        if gap >= high_thresh:
            confidence = Confidence.HIGH
        elif gap >= lc_thresh:
            confidence = Confidence.MEDIUM
        else:
            confidence = Confidence.LOW

        return ScoredWord(
            word=target_word,
            detected_hyp=best_hyp,
            confidence=confidence,
            score_gap=gap,
        )

    def score_word_segmented(
        self,
        log_probs,
        start_frame: int,
        end_frame: int,
        target_word: BookWord,
    ) -> ScoredWord:
        """Score a word's i3rab hypotheses using only its frame segment."""
        if len(target_word.hypotheses) <= 1:
            hyp = target_word.hypotheses[0] if target_word.hypotheses else None
            return ScoredWord(
                word=target_word,
                detected_hyp=hyp,
                confidence=Confidence.HIGH,
                score_gap=float("inf"),
            )

        if start_frame >= end_frame:
            return ScoredWord(
                word=target_word,
                detected_hyp=None,
                confidence=Confidence.LOW,
                score_gap=0.0,
            )

        segment = log_probs[:, start_frame:end_frame, :]
        seg_len = torch.tensor([end_frame - start_frame])

        scored = []
        for hyp in target_word.hypotheses:
            score = self._ctc_score(segment, seg_len, hyp.diacritized)
            scored.append((score, hyp))

        scored.sort(key=lambda x: x[0], reverse=True)

        best_score, best_hyp = scored[0]
        second_score = scored[1][0] if len(scored) > 1 else float("-inf")
        gap = best_score - second_score

        if gap >= 1.0:
            confidence = Confidence.HIGH
        elif gap >= 0.3:
            confidence = Confidence.MEDIUM
        else:
            confidence = Confidence.LOW

        return ScoredWord(
            word=target_word,
            detected_hyp=best_hyp,
            confidence=confidence,
            score_gap=gap,
        )
