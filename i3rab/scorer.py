"""Diacritics scorer using Whisper hypothesis testing.

Core idea: for each word, we know all possible diacritized forms.
We use Whisper's encoder-decoder architecture to score how well
the audio matches each hypothesis. The hypothesis with the highest
log-likelihood is what the user most likely pronounced.
"""

import re

import numpy as np
import torch
from transformers.modeling_outputs import BaseModelOutput

from .models import (
    BookWord,
    ScoredWord,
    Confidence,
    WordHypothesis,
)
from .config import Config


class DiacriticsScorer:
    """Scores diacritization hypotheses against audio using Whisper."""

    def __init__(self, config: Config | None = None):
        self.config = config or Config()
        self.model = None
        self.processor = None
        self._loaded = False
        self._device = torch.device("cpu")
        self._dtype = torch.float32

    def _resolve_device(self) -> torch.device:
        """Resolve the compute device from config."""
        if self.config.device != "auto":
            return torch.device(self.config.device)
        if torch.cuda.is_available():
            return torch.device("cuda")
        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            return torch.device("mps")
        return torch.device("cpu")

    def _resolve_dtype(self, device: torch.device) -> torch.dtype:
        """Resolve torch dtype from config and device."""
        if self.config.torch_dtype != "auto":
            dtype_map = {
                "float16": torch.float16,
                "float32": torch.float32,
                "bfloat16": torch.bfloat16,
            }
            return dtype_map.get(self.config.torch_dtype, torch.float32)
        if device.type == "cuda":
            return torch.float16
        # MPS (Apple Silicon) has float16 precision issues with large Whisper
        # models — produces garbage output. Use float32 for stability.
        return torch.float32

    def load(self):
        """Load the Whisper model for scoring."""
        if self._loaded:
            return

        from transformers import WhisperProcessor, WhisperForConditionalGeneration

        self._device = self._resolve_device()
        self._dtype = self._resolve_dtype(self._device)

        model_name = self.config.asr_model
        print(f"Loading scorer model: {model_name} on {self._device} ({self._dtype})")
        self.processor = WhisperProcessor.from_pretrained(model_name)
        self.model = WhisperForConditionalGeneration.from_pretrained(
            model_name, torch_dtype=self._dtype
        )
        self.model = self.model.to(self._device)
        self.model.eval()

        # For generate() calls — pass language/task directly (forced_decoder_ids is deprecated)
        self._generate_kwargs = {"language": "ar", "task": "transcribe"}

        # For _score_text() forced decoding — store the decoder prefix token IDs
        self._prefix_ids = [self.model.config.decoder_start_token_id]
        forced_ids = self.processor.get_decoder_prompt_ids(
            language="ar", task="transcribe"
        )
        for _, token_id in forced_ids:
            self._prefix_ids.append(token_id)

        self._loaded = True
        print("Scorer model loaded.")

    def _get_input_features(self, audio: np.ndarray):
        """Get mel spectrogram input features from audio."""
        return self.processor(
            audio, sampling_rate=self.config.sample_rate, return_tensors="pt"
        ).input_features.to(device=self._device, dtype=self._dtype)

    def _make_attention_mask(self, input_features):
        """Create all-1s attention mask to suppress pad/eos token warning."""
        return torch.ones(
            input_features.shape[0], input_features.shape[-1],
            dtype=torch.long, device=self._device,
        )

    def _get_encoder_output(self, audio: np.ndarray):
        """Get Whisper encoder output for an audio segment."""
        input_features = self._get_input_features(audio)

        with torch.no_grad():
            encoder_outputs = self.model.get_encoder()(input_features)
        return encoder_outputs

    def _score_text(self, encoder_outputs, text: str) -> float:
        """Score how well a text hypothesis matches the encoder output.

        Returns the average per-token log-likelihood of the hypothesis
        given the audio.
        """
        token_ids, token_logprobs = self._get_per_token_logprobs(encoder_outputs, text)
        if not token_logprobs:
            return float("-inf")
        return sum(token_logprobs) / len(token_logprobs)

    def _get_per_token_logprobs(
        self, encoder_outputs, text: str
    ) -> tuple[list[int], list[float]]:
        """Get per-token log-probabilities and token IDs for text.

        Returns (token_ids, token_logprobs) where each list corresponds
        to the text portion only (prefix tokens excluded).
        """
        prefix_ids = list(self._prefix_ids)
        text_ids = self.processor.tokenizer.encode(text, add_special_tokens=False)
        if not text_ids:
            return [], []

        all_ids = prefix_ids + text_ids
        decoder_input = torch.tensor(
            [all_ids[:-1]], dtype=torch.long, device=self._device
        )
        target = torch.tensor(
            [all_ids[1:]], dtype=torch.long, device=self._device
        )

        with torch.no_grad():
            outputs = self.model(
                encoder_outputs=encoder_outputs,
                decoder_input_ids=decoder_input,
            )
            logits = outputs.logits
            if self.config.score_temperature != 1.0:
                logits = logits / self.config.score_temperature
            log_probs = torch.log_softmax(logits, dim=-1)

        prefix_len = len(prefix_ids) - 1
        token_ids = []
        token_logprobs = []
        for t in range(prefix_len, target.size(1)):
            token_ids.append(target[0, t].item())
            token_logprobs.append(log_probs[0, t, target[0, t]].item())

        return token_ids, token_logprobs

    def _get_per_token_logprobs_batch(
        self, encoder_outputs, texts: list[str]
    ) -> list[tuple[list[int], list[float]]]:
        """Batched version: score multiple texts in chunked decoder passes.

        Processes up to config.scorer_batch_size texts per forward pass.
        Right-pads shorter sequences within each chunk. Causal attention
        ensures padding doesn't affect real token logprobs.
        """
        if len(texts) <= 1:
            if not texts:
                return []
            return [self._get_per_token_logprobs(encoder_outputs, texts[0])]

        prefix_ids = list(self._prefix_ids)
        prefix_len = len(prefix_ids) - 1
        pad_id = self.processor.tokenizer.pad_token_id
        if pad_id is None:
            pad_id = self.processor.tokenizer.eos_token_id

        # Tokenize all texts upfront
        all_sequences = []
        for text in texts:
            text_ids = self.processor.tokenizer.encode(text, add_special_tokens=False)
            all_sequences.append(prefix_ids + text_ids)

        # Process in chunks of scorer_batch_size
        chunk_size = self.config.scorer_batch_size
        all_results = []

        for start in range(0, len(all_sequences), chunk_size):
            chunk_seqs = all_sequences[start : start + chunk_size]
            n_chunk = len(chunk_seqs)

            if n_chunk == 1:
                # Single item — use unbatched path (no padding overhead)
                all_results.append(
                    self._get_per_token_logprobs(encoder_outputs, texts[start])
                )
                continue

            max_len = max(len(seq) for seq in chunk_seqs)

            decoder_inputs = []
            targets = []
            seq_lengths = []
            for seq in chunk_seqs:
                n = len(seq) - 1
                seq_lengths.append(n)
                pad_count = max_len - 1 - n
                decoder_inputs.append(seq[:-1] + [pad_id] * pad_count)
                targets.append(seq[1:] + [pad_id] * pad_count)

            decoder_input = torch.tensor(
                decoder_inputs, dtype=torch.long, device=self._device
            )
            target = torch.tensor(
                targets, dtype=torch.long, device=self._device
            )

            expanded_encoder = BaseModelOutput(
                last_hidden_state=encoder_outputs.last_hidden_state.expand(
                    n_chunk, -1, -1
                )
            )

            with torch.no_grad():
                outputs = self.model(
                    encoder_outputs=expanded_encoder,
                    decoder_input_ids=decoder_input,
                )
                logits = outputs.logits
                if self.config.score_temperature != 1.0:
                    logits = logits / self.config.score_temperature
                log_probs = torch.log_softmax(logits, dim=-1)

            for i in range(n_chunk):
                token_ids = []
                token_logprobs = []
                for t in range(prefix_len, seq_lengths[i]):
                    token_ids.append(target[i, t].item())
                    token_logprobs.append(log_probs[i, t, target[i, t]].item())
                all_results.append((token_ids, token_logprobs))

        return all_results

    def score_word(
        self,
        audio: np.ndarray,
        word: BookWord,
        encoder_outputs=None,
    ) -> ScoredWord:
        """Score which diacritization hypothesis best matches the audio."""
        self.load()

        if encoder_outputs is None:
            encoder_outputs = self._get_encoder_output(audio)

        if len(word.hypotheses) <= 1:
            hyp = word.hypotheses[0] if word.hypotheses else None
            return ScoredWord(
                word=word,
                detected_hyp=hyp,
                confidence=Confidence.HIGH,
                score_gap=float("inf"),
            )

        # Score all hypotheses in one batched decoder pass
        texts = [hyp.diacritized for hyp in word.hypotheses]
        batch_results = self._get_per_token_logprobs_batch(encoder_outputs, texts)
        scored = []
        for hyp, (_, token_logprobs) in zip(word.hypotheses, batch_results):
            score = (
                sum(token_logprobs) / len(token_logprobs)
                if token_logprobs
                else float("-inf")
            )
            scored.append((score, hyp))

        # Sort by score (highest = best match)
        scored.sort(key=lambda x: x[0], reverse=True)

        best_score, best_hyp = scored[0]
        second_score = scored[1][0] if len(scored) > 1 else float("-inf")
        gap = best_score - second_score

        # Scale thresholds by temperature (higher temp = smaller gaps)
        temp = self.config.score_temperature
        high_thresh = self.config.high_confidence_gap / temp
        med_thresh = self.config.medium_confidence_gap / temp

        if gap >= high_thresh:
            confidence = Confidence.HIGH
        elif gap >= med_thresh:
            confidence = Confidence.MEDIUM
        else:
            confidence = Confidence.LOW

        return ScoredWord(
            word=word,
            detected_hyp=best_hyp,
            confidence=confidence,
            score_gap=gap,
        )

    def score_word_in_context(
        self,
        audio: np.ndarray,
        target_word: BookWord,
        all_words: list[BookWord],
        encoder_outputs=None,
    ) -> ScoredWord:
        """Score a word's hypotheses using full-sentence context.

        Builds full sentence with each hypothesis swapped in, then compares
        log-probs only at token positions where hypotheses diverge.
        """
        self.load()

        if encoder_outputs is None:
            encoder_outputs = self._get_encoder_output(audio)

        if len(target_word.hypotheses) <= 1:
            hyp = target_word.hypotheses[0] if target_word.hypotheses else None
            return ScoredWord(
                word=target_word,
                detected_hyp=hyp,
                confidence=Confidence.HIGH,
                score_gap=float("inf"),
            )

        # Build full sentence with each hypothesis swapped in — batch all at once
        context_parts = [w.correct_diac for w in all_words]
        target_pos = next(
            i for i, w in enumerate(all_words) if w.index == target_word.index
        )
        full_texts = []
        for hyp in target_word.hypotheses:
            parts = list(context_parts)
            parts[target_pos] = hyp.diacritized
            full_texts.append(" ".join(parts))

        batch_results = self._get_per_token_logprobs_batch(
            encoder_outputs, full_texts
        )
        hyp_results = [
            (hyp, ids, lps)
            for hyp, (ids, lps) in zip(target_word.hypotheses, batch_results)
        ]

        # Find positions where token IDs differ across hypotheses
        max_len = max(len(r[1]) for r in hyp_results) if hyp_results else 0
        differing_positions = set()
        for pos in range(max_len):
            tokens_at_pos = set()
            for _, token_ids, _ in hyp_results:
                if pos < len(token_ids):
                    tokens_at_pos.add(token_ids[pos])
                else:
                    tokens_at_pos.add(None)
            if len(tokens_at_pos) > 1:
                differing_positions.add(pos)

        # Score each hypothesis using only diverging positions
        scored = []
        for hyp, token_ids, token_logprobs in hyp_results:
            if not differing_positions:
                avg = (
                    sum(token_logprobs) / len(token_logprobs)
                    if token_logprobs
                    else float("-inf")
                )
            else:
                diff_logprobs = [
                    token_logprobs[pos]
                    for pos in sorted(differing_positions)
                    if pos < len(token_logprobs)
                ]
                avg = (
                    sum(diff_logprobs) / len(diff_logprobs)
                    if diff_logprobs
                    else float("-inf")
                )
            scored.append((avg, hyp))

        scored.sort(key=lambda x: x[0], reverse=True)

        best_score, best_hyp = scored[0]
        second_score = scored[1][0] if len(scored) > 1 else float("-inf")
        gap = best_score - second_score

        temp = self.config.score_temperature
        high_thresh = self.config.high_confidence_gap / temp
        med_thresh = self.config.medium_confidence_gap / temp

        if gap >= high_thresh:
            confidence = Confidence.HIGH
        elif gap >= med_thresh:
            confidence = Confidence.MEDIUM
        else:
            confidence = Confidence.LOW

        return ScoredWord(
            word=target_word,
            detected_hyp=best_hyp,
            confidence=confidence,
            score_gap=gap,
        )

    def score_phrase_contextual(
        self,
        audio: np.ndarray,
        words: list[BookWord],
        encoder_outputs=None,
    ) -> list[ScoredWord]:
        """Score all words using full-sentence contextual scoring.

        Each word is scored with the full sentence as context, comparing
        log-probs only at diverging token positions.
        """
        self.load()

        if encoder_outputs is None:
            encoder_outputs = self._get_encoder_output(audio)

        results = []
        for word in words:
            result = self.score_word_in_context(
                audio, word, words, encoder_outputs
            )
            results.append(result)

        return results

    def score_phrase(
        self,
        audio: np.ndarray,
        words: list[BookWord],
        word_timestamps: list[tuple[float, float]] | None = None,
    ) -> list[ScoredWord]:
        """Score all words in a phrase.

        Always uses contextual scoring (full sentence with hypothesis swapping)
        as it significantly outperforms per-word isolated scoring.
        """
        self.load()

        encoder_outputs = self._get_encoder_output(audio)
        return self.score_phrase_contextual(audio, words, encoder_outputs)

    def transcribe(self, audio: np.ndarray) -> str:
        """Standard transcription (for position tracking)."""
        self.load()

        input_features = self._get_input_features(audio)
        attention_mask = self._make_attention_mask(input_features)

        with torch.no_grad():
            predicted_ids = self.model.generate(
                input_features,
                attention_mask=attention_mask,
                **self._generate_kwargs,
            )

        text = self.processor.batch_decode(predicted_ids, skip_special_tokens=True)[0]
        return text

    def transcribe_with_timestamps(
        self, audio: np.ndarray, prompt: str | None = None,
    ) -> tuple[str, list[dict]]:
        """Transcribe and return word-level timestamps.

        If prompt is provided, it's used as decoder context to bias
        Whisper toward expected vocabulary (guided transcription).
        """
        self.load()

        input_features = self._get_input_features(audio)
        attention_mask = self._make_attention_mask(input_features)

        generate_kwargs = dict(self._generate_kwargs)
        if prompt:
            prompt_ids = self.processor.tokenizer.encode(
                prompt, add_special_tokens=False
            )
            generate_kwargs["prompt_ids"] = torch.tensor(
                prompt_ids, dtype=torch.long, device=self._device
            )

        with torch.no_grad():
            result = self.model.generate(
                input_features,
                attention_mask=attention_mask,
                return_timestamps=True,
                **generate_kwargs,
            )

        text = self.processor.batch_decode(result, skip_special_tokens=True)[0]

        timestamps = []
        try:
            decoded = self.processor.batch_decode(
                result, skip_special_tokens=False, decode_with_timestamps=True
            )[0]
            pattern = r"<\|(\d+\.\d+)\|>(.*?)<\|(\d+\.\d+)\|>"
            for match in re.finditer(pattern, decoded):
                start = float(match.group(1))
                word_text = match.group(2).strip()
                end = float(match.group(3))
                if word_text:
                    timestamps.append({
                        "word": word_text,
                        "start": start,
                        "end": end,
                    })
        except Exception:
            pass

        return text, timestamps
