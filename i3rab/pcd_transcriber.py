"""PCD (Punctuated, Case-ending, Diacritization) transcriber and scorer.

Uses a fine-tuned NVIDIA FastConformer model to:
1. Directly transcribe Arabic audio with full diacritics (free transcription)
2. Score diacritization hypotheses using CTC log-probabilities (constrained scoring)
3. Force-align reference text to CTC log-probs for per-word boundaries and scoring

The forced-alignment approach runs the encoder ONCE, then:
- Forced alignment → per-word frame boundaries (for segmentation)
- Per-word greedy decode → tashkeel comparison (short sequences are reliable)
- Per-word CTC scoring → i3rab hypothesis ranking (case endings)
"""

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import torch
from torchaudio.functional import forced_align

from .config import Config
from .models import BookWord, ScoredWord, Confidence


@dataclass
class WordBoundary:
    """Frame boundaries and alignment score for a single word."""
    word_idx: int
    start_frame: int
    end_frame: int
    score: float  # mean log-prob (higher = better alignment)


class PCDTranscriber:
    """Transcribes and scores Arabic audio using NeMo PCD model."""

    def __init__(self, config: Config | None = None):
        self.config = config or Config()
        self.model = None
        self._loaded = False
        self._ctc_loss_fn = None
        self._blank_id = None

    def load(self):
        """Load the NeMo PCD model."""
        if self._loaded:
            return

        import nemo.collections.asr as nemo_asr

        model_path = self.config.pcd_model_path
        if not model_path:
            raise ValueError("pcd_model_path not set in config")

        path = Path(model_path)
        if not path.exists():
            raise FileNotFoundError(f"PCD model not found: {path}")

        print(f"Loading PCD model from {model_path}...")
        self.model = nemo_asr.models.EncDecHybridRNNTCTCBPEModel.restore_from(
            str(path)
        )
        self.model.eval()
        self.model.change_decoding_strategy(decoder_type="ctc")

        # Set up CTC scoring
        self._blank_id = self.model.ctc_decoder.num_classes_with_blank - 1
        self._ctc_loss_fn = torch.nn.CTCLoss(
            blank=self._blank_id, reduction="none", zero_infinity=True
        )

        self._loaded = True
        print("PCD model loaded.")

    # ── Encoder + log-probs (shared by transcription and scoring) ────────

    def encode(self, audio: np.ndarray):
        """Run encoder + CTC decoder → frame-level log-probs + raw encoder output.

        Returns (log_probs, encoded_len, encoded):
            log_probs:    [1, T_frames, vocab_size+1]
            encoded_len:  [1]
            encoded:      [1, D_enc, T_frames]  (raw encoder for RNN-T)
        """
        self.load()

        audio_signal = torch.tensor(audio).unsqueeze(0)
        signal_len = torch.tensor([len(audio)])

        with torch.no_grad():
            encoded, encoded_len = self.model.forward(
                input_signal=audio_signal, input_signal_length=signal_len
            )
            log_probs = self.model.ctc_decoder(encoder_output=encoded)

        return log_probs, encoded_len, encoded

    # ── Free transcription (greedy CTC decode) ──────────────────────────

    def greedy_decode(self, log_probs, encoded_len) -> str:
        """Greedy CTC decode: argmax per frame, collapse repeats, remove blanks."""
        T = encoded_len[0].item()
        preds = log_probs[0, :T].argmax(dim=-1).tolist()  # [T]

        # Collapse consecutive duplicates, then remove blanks
        collapsed = []
        prev = None
        for p in preds:
            if p != prev:
                if p != self._blank_id:
                    collapsed.append(p)
                prev = p

        # Decode token IDs → text
        if not collapsed:
            return ""
        return self.model.tokenizer.ids_to_text(collapsed)

    def transcribe(self, audio: np.ndarray) -> str:
        """Transcribe audio to diacritized Arabic text (free transcription).

        Uses the encoder → greedy CTC decode path (no temp file I/O).
        """
        log_probs, encoded_len, _encoded = self.encode(audio)
        return self.greedy_decode(log_probs, encoded_len)

    def transcribe_and_encode(self, audio: np.ndarray):
        """Single encoder pass: returns (transcript, log_probs, encoded_len, encoded).

        Use this for the hybrid approach — get both free transcription
        and the log-probs needed for hypothesis scoring from one pass.
        encoded is the raw encoder output needed for RNN-T scoring.
        """
        log_probs, encoded_len, encoded = self.encode(audio)
        transcript = self.greedy_decode(log_probs, encoded_len)
        return transcript, log_probs, encoded_len, encoded

    # ── RNN-T (transducer) hypothesis scoring ────────────────────────────

    def _rnnt_score(self, encoded, encoded_len, text: str) -> float:
        """Score a text hypothesis using RNN-T teacher-forced log-probability.

        Uses the model's prediction network + joint network + RNNT loss.
        Returns negative RNNT loss (higher = better match).
        """
        token_ids = self.model.tokenizer.text_to_ids(text)
        if not token_ids:
            return float("-inf")

        targets = torch.tensor([token_ids], dtype=torch.long)
        target_len = torch.tensor([len(token_ids)], dtype=torch.long)

        with torch.no_grad():
            # Prediction (decoder) network: token sequence → embeddings
            decoder_output, dec_len, _ = self.model.decoder(
                targets=targets, target_length=target_len
            )
            # Joint network: combine encoder + decoder → log-probs
            # fuse_loss_wer requires extra args; disable WER computation
            joint_output = self.model.joint(
                encoder_outputs=encoded,
                decoder_outputs=decoder_output,
                encoder_lengths=encoded_len,
                transcripts=targets,
                transcript_lengths=target_len,
                compute_wer=False,
            )
            # When fuse_loss_wer is set, joint returns (loss, wer, ...) or
            # just the joint tensor depending on compute_wer.  Handle both.
            if isinstance(joint_output, tuple):
                # fused mode returns (loss, wer, joint_tensor, ...)
                # We want the loss directly
                loss = joint_output[0]
                return -loss.item()

            # RNNT loss: negative log-likelihood of the label sequence
            loss = self.model.loss(
                log_probs=joint_output,
                targets=targets,
                input_lengths=encoded_len,
                target_lengths=target_len,
            )

        return -loss.item()

    # ── CTC hypothesis scoring ──────────────────────────────────────────

    def _ctc_score(self, log_probs, encoded_len, text: str) -> float:
        """Score a text hypothesis using CTC log-probability.

        Returns negative CTC loss (higher = better match).
        """
        token_ids = self.model.tokenizer.text_to_ids(text)
        if not token_ids:
            return float("-inf")

        targets = torch.tensor([token_ids])
        target_len = torch.tensor([len(token_ids)])

        # CTCLoss expects [T, B, C]
        lp = log_probs.transpose(0, 1)

        with torch.no_grad():
            loss = self._ctc_loss_fn(lp, targets, encoded_len, target_len)

        return -loss.item()

    def _ctc_score_segment(
        self, log_probs, start_frame: int, end_frame: int, text: str
    ) -> float:
        """Score a text hypothesis using CTC on a frame segment only."""
        token_ids = self.model.tokenizer.text_to_ids(text)
        if not token_ids:
            return float("-inf")
        seg = log_probs[:, start_frame:end_frame, :]
        seg_len = torch.tensor([seg.shape[1]])
        if seg_len.item() < len(token_ids):
            return float("-inf")
        targets = torch.tensor([token_ids])
        target_len = torch.tensor([len(token_ids)])
        lp = seg.transpose(0, 1)  # [T, B, C]
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
        """Compare ref vs hyp using frame-level posteriors.

        Instead of CTC loss (which marginalizes over blank patterns),
        this sums raw log-probs of each token set across frames.
        Returns hyp_score - ref_score (positive = hyp preferred).
        """
        ref_ids = self.model.tokenizer.text_to_ids(ref_word)
        hyp_ids = self.model.tokenizer.text_to_ids(hyp_word)
        if not ref_ids or not hyp_ids:
            return 0.0

        seg = log_probs[0, start_frame:end_frame, :]  # [T_seg, V]
        T_seg = seg.shape[0]
        if T_seg == 0:
            return 0.0

        with torch.no_grad():
            # For each frame, get the max log-prob across the token
            # set for each hypothesis (best single-token match)
            ref_ids_t = torch.tensor(ref_ids, dtype=torch.long)
            hyp_ids_t = torch.tensor(hyp_ids, dtype=torch.long)

            ref_scores = seg[:, ref_ids_t].max(dim=1).values  # [T_seg]
            hyp_scores = seg[:, hyp_ids_t].max(dim=1).values  # [T_seg]

            # Average the per-frame advantage
            diff = (hyp_scores - ref_scores).mean().item()

        return diff

    def score_word_in_context(
        self,
        log_probs,
        encoded_len,
        target_word: BookWord,
        all_words: list[BookWord],
        encoded=None,
        rnnt_weight: float = 0.0,
    ) -> ScoredWord:
        """Score a word's i3rab hypotheses using full-sentence scoring.

        When encoded is provided and rnnt_weight > 0, uses a weighted
        combination of CTC and RNN-T teacher-forced scores.
        """
        if len(target_word.hypotheses) <= 1:
            hyp = target_word.hypotheses[0] if target_word.hypotheses else None
            return ScoredWord(
                word=target_word,
                detected_hyp=hyp,
                confidence=Confidence.HIGH,
                score_gap=float("inf"),
            )

        use_rnnt = encoded is not None and rnnt_weight > 0

        context_parts = [w.correct_diac for w in all_words]
        target_pos = next(
            i for i, w in enumerate(all_words) if w.index == target_word.index
        )

        scored = []
        for hyp in target_word.hypotheses:
            parts = list(context_parts)
            parts[target_pos] = hyp.diacritized
            full_text = " ".join(parts)
            ctc_sc = self._ctc_score(log_probs, encoded_len, full_text)

            if use_rnnt:
                rnnt_sc = self._rnnt_score(encoded, encoded_len, full_text)
                combined = (1 - rnnt_weight) * ctc_sc + rnnt_weight * rnnt_sc
            else:
                combined = ctc_sc

            scored.append((combined, hyp))

        scored.sort(key=lambda x: x[0], reverse=True)

        best_score, best_hyp = scored[0]
        second_score = scored[1][0] if len(scored) > 1 else float("-inf")
        gap = best_score - second_score

        lc_thresh = getattr(self.config, 'low_confidence_threshold', 1.5)
        high_thresh = lc_thresh + 0.5  # HIGH = LOW + 0.5

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

    # ── Forced alignment ─────────────────────────────────────────────

    def forced_align_reference(
        self, log_probs, encoded_len, reference_text: str
    ):
        """Force-align reference text to CTC log-probs.

        Returns (alignment, scores):
            alignment: [1, T] — token label per frame (blank or token id)
            scores:    [1, T] — log-prob at each frame
        """
        token_ids = self.model.tokenizer.text_to_ids(reference_text)
        if not token_ids:
            return None, None

        T = encoded_len[0].item()
        # forced_align requires T >= len(targets)
        if T < len(token_ids):
            return None, None

        targets = torch.tensor([token_ids], dtype=torch.int32)
        input_lengths = encoded_len.to(torch.int32)
        target_lengths = torch.tensor([len(token_ids)], dtype=torch.int32)

        with torch.no_grad():
            alignment, scores = forced_align(
                log_probs,
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
        """Map forced-alignment output to per-word frame boundaries.

        The alignment contains token IDs per frame (blank_id for blank frames).
        Since the Viterbi path is monotonic through the target sequence, we
        walk the alignment and track which target position each emission maps to.

        Rules for monotonic tracking:
        - Same non-blank token as previous frame (no blank between) → repeat, same target pos
        - New non-blank token (or same token after a blank) → advance target pos
        """
        if alignment is None:
            return []

        # Build flat target token list + token→word mapping
        full_tokens = []
        token_to_word = []
        for wi, word in enumerate(reference_words):
            ids = self.model.tokenizer.text_to_ids(word)
            for tok_id in ids:
                full_tokens.append(tok_id)
                token_to_word.append(wi)

        align_path = alignment[0].tolist()
        frame_scores = scores[0].tolist()

        # Walk alignment monotonically through the target sequence
        word_frames: dict[int, list[tuple[int, float]]] = {}
        target_pos = -1
        prev_label = self._blank_id

        for t, label in enumerate(align_path):
            if label == self._blank_id:
                prev_label = self._blank_id
                continue

            if label == prev_label:
                # Repeat of same token (no blank in between) → same target pos
                pass
            else:
                # New emission: advance target_pos to find this token
                target_pos += 1
                while (
                    target_pos < len(full_tokens)
                    and full_tokens[target_pos] != label
                ):
                    target_pos += 1

            if 0 <= target_pos < len(token_to_word):
                wi = token_to_word[target_pos]
                word_frames.setdefault(wi, []).append(
                    (t, frame_scores[t])
                )

            prev_label = label

        # Build WordBoundary list
        boundaries = []
        for wi in range(len(reference_words)):
            if wi in word_frames:
                frames = word_frames[wi]
                start = frames[0][0]
                end = frames[-1][0] + 1  # exclusive end
                mean_score = sum(s for _, s in frames) / len(frames)
                boundaries.append(WordBoundary(wi, start, end, mean_score))
            else:
                boundaries.append(WordBoundary(wi, 0, 0, float("-inf")))

        return boundaries

    def decode_word_segment(self, log_probs, start_frame: int, end_frame: int) -> str:
        """Greedy CTC decode on a single word's frame segment.

        Short sequences (3-8 tokens) decode reliably vs full-sentence garbling.
        """
        if start_frame >= end_frame:
            return ""

        segment = log_probs[:, start_frame:end_frame, :]
        seg_len = torch.tensor([end_frame - start_frame])
        return self.greedy_decode(segment, seg_len)

    # ── Joint lattice scoring (WFST-style beam search) ─────────────

    def score_words_joint(
        self,
        log_probs,
        encoded_len,
        all_words: list[BookWord],
        beam_width: int = 16,
    ) -> list[ScoredWord]:
        """Score all words jointly using beam search over hypothesis lattice.

        Instead of scoring each word independently, this explores combinations
        of hypotheses across words.  A beam of the top-K sentence variants is
        maintained and expanded at each multi-hypothesis word position.

        Returns one ScoredWord per element of *all_words* (same order).
        """
        # Identify positions that need branching
        branch_positions: list[int] = []
        for i, w in enumerate(all_words):
            if len(w.hypotheses) > 1:
                branch_positions.append(i)

        if not branch_positions:
            # Nothing to score — return defaults
            results = []
            for w in all_words:
                hyp = w.hypotheses[0] if w.hypotheses else None
                results.append(ScoredWord(
                    word=w, detected_hyp=hyp,
                    confidence=Confidence.HIGH, score_gap=float("inf"),
                ))
            return results

        # Initial beam: one path using correct_diac for every word
        # Each beam entry: (score, choices) where choices[i] = hypothesis index for branch_positions[i]
        base_parts = [w.correct_diac for w in all_words]

        # Seed beam with all hypotheses at the first branch position
        beam: list[tuple[float, list[int]]] = []
        first_pos = branch_positions[0]
        for hi, hyp in enumerate(all_words[first_pos].hypotheses):
            parts = list(base_parts)
            parts[first_pos] = hyp.diacritized
            text = " ".join(parts)
            score = self._ctc_score(log_probs, encoded_len, text)
            beam.append((score, [hi]))

        beam.sort(key=lambda x: x[0], reverse=True)
        beam = beam[:beam_width]

        # Expand beam at each subsequent branch position
        for bp_idx in range(1, len(branch_positions)):
            pos = branch_positions[bp_idx]
            new_beam: list[tuple[float, list[int]]] = []

            for parent_score, parent_choices in beam:
                for hi, hyp in enumerate(all_words[pos].hypotheses):
                    # Build sentence with all previous choices + this one
                    parts = list(base_parts)
                    for prev_bp_idx, prev_hi in enumerate(parent_choices):
                        prev_pos = branch_positions[prev_bp_idx]
                        parts[prev_pos] = all_words[prev_pos].hypotheses[prev_hi].diacritized
                    parts[pos] = hyp.diacritized
                    text = " ".join(parts)
                    score = self._ctc_score(log_probs, encoded_len, text)
                    new_beam.append((score, parent_choices + [hi]))

            new_beam.sort(key=lambda x: x[0], reverse=True)
            beam = new_beam[:beam_width]

        # Extract per-word results by marginalizing over beam
        # For each branch position, accumulate scores per hypothesis
        results: list[ScoredWord] = []
        for i, w in enumerate(all_words):
            if i not in branch_positions:
                hyp = w.hypotheses[0] if w.hypotheses else None
                results.append(ScoredWord(
                    word=w, detected_hyp=hyp,
                    confidence=Confidence.HIGH, score_gap=float("inf"),
                ))
                continue

            bp_idx = branch_positions.index(i)
            # Sum scores for each hypothesis across all beam paths
            hyp_scores: dict[int, float] = {}
            for path_score, choices in beam:
                hi = choices[bp_idx]
                # Use log-sum-exp style: accumulate in linear space
                if hi not in hyp_scores:
                    hyp_scores[hi] = path_score
                else:
                    # Take the max path score for this hypothesis
                    hyp_scores[hi] = max(hyp_scores[hi], path_score)

            ranked = sorted(hyp_scores.items(), key=lambda x: x[1], reverse=True)
            best_hi, best_score = ranked[0]
            second_score = ranked[1][1] if len(ranked) > 1 else float("-inf")
            gap = best_score - second_score

            if gap >= 2.0:
                confidence = Confidence.HIGH
            elif gap >= 1.5:
                confidence = Confidence.MEDIUM
            else:
                confidence = Confidence.LOW

            results.append(ScoredWord(
                word=w,
                detected_hyp=w.hypotheses[best_hi],
                confidence=confidence,
                score_gap=gap,
            ))

        return results

    def score_word_segmented(
        self,
        log_probs,
        start_frame: int,
        end_frame: int,
        target_word: BookWord,
    ) -> ScoredWord:
        """Score a word's i3rab hypotheses using only its frame segment.

        More discriminative than full-sentence scoring — no leakage from
        surrounding words.
        """
        if len(target_word.hypotheses) <= 1:
            hyp = target_word.hypotheses[0] if target_word.hypotheses else None
            return ScoredWord(
                word=target_word,
                detected_hyp=hyp,
                confidence=Confidence.HIGH,
                score_gap=float("inf"),
            )

        if start_frame >= end_frame:
            # No frames for this word — can't score
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
