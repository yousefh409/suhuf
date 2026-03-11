"""CTC forced alignment for precise word-level timestamps.

Uses ctc-forced-aligner (pip install ctc-forced-aligner) with MMS-300M
for monotonic frame-level alignment, much more precise than Whisper's
attention-based timestamps.

CTC models strip Arabic diacritics, so this is used ONLY for timestamps,
not for hypothesis scoring.
"""

import numpy as np

from .config import Config

_CTC_AVAILABLE = False
try:
    from ctc_forced_aligner import (
        load_alignment_model,
        generate_emissions,
        preprocess_text,
        get_alignments,
        get_spans,
        postprocess_results,
    )
    _CTC_AVAILABLE = True
except ImportError:
    pass


def is_available() -> bool:
    """Check if ctc-forced-aligner is installed."""
    return _CTC_AVAILABLE


class CTCAligner:
    """Wraps ctc-forced-aligner for word-level timestamp extraction."""

    def __init__(self, config: Config):
        self.config = config
        self._model = None
        self._tokenizer = None
        self._dictionary = None
        self._loaded = False

    def load(self):
        """Load the CTC alignment model."""
        if self._loaded or not _CTC_AVAILABLE:
            return

        import torch

        device = "cuda" if torch.cuda.is_available() else "cpu"
        dtype = torch.float16 if device == "cuda" else torch.float32

        print("Loading CTC alignment model...")
        self._model, self._tokenizer = load_alignment_model(
            device, dtype=dtype
        )
        self._loaded = True
        print("CTC alignment model loaded.")

    def align(
        self, audio: np.ndarray, text: str
    ) -> list[dict] | None:
        """Align text to audio, returning word-level timestamps.

        Returns list of {"word": str, "start": float, "end": float}
        or None if alignment fails.
        """
        if not _CTC_AVAILABLE or not self._loaded:
            return None

        try:
            import torch

            audio_tensor = torch.tensor(audio, dtype=torch.float32).unsqueeze(0)
            emissions, stride = generate_emissions(
                self._model,
                audio_tensor,
                batch_size=1,
            )

            tokens_starred, text_starred = preprocess_text(
                text,
                romanize=True,
                language="ara",
            )

            segments, scores, blank_id = get_alignments(
                emissions,
                tokens_starred,
                self._tokenizer,
            )
            spans = get_spans(tokens_starred, segments, blank_id)
            word_results = postprocess_results(text_starred, spans, stride, scores)

            results = []
            for item in word_results:
                results.append({
                    "word": item["word"],
                    "start": item["start"],
                    "end": item["end"],
                })
            return results if results else None
        except Exception:
            return None
