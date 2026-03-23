"""Phoneme-based scorer using Wav2Vec2 CTC logits.

Uses IbrahimSalah/Wav2vecLarge_quran_syllables_recognition to score
hypothesis texts against audio using CTC forward probabilities.

Instead of decoding syllables and matching, this directly computes
P(hypothesis | audio) using the CTC model's logits, analogous to
how Whisper scores via decoder log-probs.

Used as a fallback when Whisper's confidence is low on case ending detection.
"""

import numpy as np
import torch

from .models import (
    BookWord,
    ScoredWord,
    Confidence,
)
from .config import Config


class PhonemeScorer:
    """Scores hypotheses using Wav2Vec2 CTC probabilities."""

    def __init__(self, config: Config | None = None):
        self.config = config or Config()
        self.model = None
        self.processor = None
        self._loaded = False
        self._device = torch.device("cpu")
        self._blank_id = 0

    def load(self):
        """Load the Wav2Vec2 phoneme model."""
        if self._loaded:
            return

        from transformers import Wav2Vec2ForCTC, Wav2Vec2Processor

        model_name = self.config.phoneme_model
        print(f"Loading phoneme model: {model_name}")

        # Use regular processor (we need the tokenizer, not the LM decoder)
        self.processor = Wav2Vec2Processor.from_pretrained(model_name)
        self.model = Wav2Vec2ForCTC.from_pretrained(model_name)

        # Resolve device
        if self.config.device != "auto":
            self._device = torch.device(self.config.device)
        elif torch.cuda.is_available():
            self._device = torch.device("cuda")
        elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            self._device = torch.device("mps")

        self.model = self.model.to(self._device)
        self.model.eval()

        # Get blank token ID (usually pad_token_id for CTC)
        self._blank_id = self.processor.tokenizer.pad_token_id or 0

        self._loaded = True
        print("Phoneme model loaded.")

    def get_logits(self, audio: np.ndarray) -> torch.Tensor:
        """Get CTC logits for full audio. Returns (1, T, V) tensor."""
        self.load()

        inputs = self.processor(
            audio, sampling_rate=self.config.sample_rate,
            return_tensors="pt", padding=True,
        )
        input_values = inputs.input_values.to(self._device)

        with torch.no_grad():
            logits = self.model(input_values).logits

        return logits

    def _ctc_score(
        self,
        log_probs: torch.Tensor,
        target_ids: list[int],
    ) -> float:
        """Compute CTC log-probability of target sequence given log_probs.

        Uses torch.nn.functional.ctc_loss (which computes negative log-likelihood).

        Args:
            log_probs: (1, T, V) log-softmax output
            target_ids: list of target token IDs

        Returns:
            Negative CTC loss (higher = better match)
        """
        if not target_ids or log_probs.size(1) == 0:
            return float("-inf")

        # CTC requires T >= target_length
        if log_probs.size(1) < len(target_ids):
            return float("-inf")

        # CTC loss not supported on MPS — compute on CPU
        lp_cpu = log_probs.cpu()
        target = torch.tensor([target_ids], dtype=torch.long)
        input_lengths = torch.tensor([lp_cpu.size(1)])
        target_lengths = torch.tensor([len(target_ids)])

        # ctc_loss expects (T, N, V) input
        loss = torch.nn.functional.ctc_loss(
            lp_cpu.transpose(0, 1),  # (T, 1, V)
            target,
            input_lengths,
            target_lengths,
            blank=self._blank_id,
            reduction="none",
            zero_infinity=True,
        )

        return -loss.item()  # negative loss = higher is better

    def score_word(
        self,
        full_audio: np.ndarray,
        word: BookWord,
        all_words: list[BookWord],
        word_start: float,
        word_end: float,
        logits: torch.Tensor | None = None,
    ) -> ScoredWord | None:
        """Score a word's hypotheses using CTC probabilities.

        Runs the CTC model on the full audio, extracts logits for the
        word's time range, and scores each hypothesis.

        Args:
            full_audio: Full sentence audio (16kHz float32)
            word: The BookWord to score
            all_words: All words in the sentence (unused, kept for API compat)
            word_start: Word start time in seconds
            word_end: Word end time in seconds
            logits: Pre-computed logits (optional, to avoid recomputing)

        Returns:
            ScoredWord with the best hypothesis, or None if scoring fails.
        """
        if len(word.hypotheses) <= 1:
            return None

        self.load()

        if logits is None:
            logits = self.get_logits(full_audio)

        # Map timestamps to frame indices
        # Wav2Vec2 stride: 320 samples per frame at 16kHz = 50 fps
        fps = self.config.sample_rate / 320
        start_frame = max(0, int((word_start - 0.05) * fps))
        end_frame = min(logits.size(1), int((word_end + 0.05) * fps))

        if end_frame <= start_frame:
            return None

        # Extract logits for this word's time range
        word_logits = logits[:, start_frame:end_frame, :]
        log_probs = torch.log_softmax(word_logits, dim=-1)

        # Score each hypothesis
        scored = []
        for hyp in word.hypotheses:
            # Tokenize the hypothesis text
            token_ids = self.processor.tokenizer.encode(hyp.diacritized)
            # Remove special tokens if any
            if hasattr(self.processor.tokenizer, 'bos_token_id') and token_ids and token_ids[0] == self.processor.tokenizer.bos_token_id:
                token_ids = token_ids[1:]
            if hasattr(self.processor.tokenizer, 'eos_token_id') and token_ids and token_ids[-1] == self.processor.tokenizer.eos_token_id:
                token_ids = token_ids[:-1]

            score = self._ctc_score(log_probs, token_ids)
            scored.append((score, hyp))

        scored.sort(key=lambda x: x[0], reverse=True)

        best_score, best_hyp = scored[0]
        second_score = scored[1][0] if len(scored) > 1 else float("-inf")
        gap = best_score - second_score

        if best_score == float("-inf"):
            return None

        # Use gap to determine confidence
        if gap >= 0.5:
            confidence = Confidence.HIGH
        elif gap >= 0.2:
            confidence = Confidence.MEDIUM
        else:
            confidence = Confidence.LOW

        return ScoredWord(
            word=word,
            detected_hyp=best_hyp,
            confidence=confidence,
            score_gap=gap,
        )
