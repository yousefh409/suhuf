"""Position tracker: determines where in the book the user is reading."""

import difflib

import numpy as np

from .models import BookWord
from .book import Book
from .arabic import strip_harakat, normalize_arabic, normalize_for_matching
from .config import Config


class PositionTracker:
    """Tracks the user's reading position in the book."""

    def __init__(self, book: Book, config: Config | None = None):
        self.book = book
        self.config = config or Config()
        self.current_position = 0

    def locate(
        self,
        transcript: str,
    ) -> tuple[int, int, list[tuple[BookWord, str]]]:
        """Find where the transcript matches in the book.

        Args:
            transcript: The ASR transcription of the user's speech.

        Returns:
            (start_idx, end_idx, matched_pairs) where matched_pairs
            is a list of (BookWord, transcript_word) tuples.
        """
        transcript = normalize_arabic(transcript)
        hyp_words = transcript.split()

        if not hyp_words:
            return self.current_position, self.current_position, []

        hyp_bases = [strip_harakat(w) for w in hyp_words]
        # Normalized bases for fuzzy matching (strips ta marbuta differences)
        hyp_norm = [normalize_for_matching(w) for w in hyp_words]

        # Search window around current position
        window_start = max(0, self.current_position - 5)
        window_end = min(
            len(self.book.words),
            self.current_position + self.config.tracker_window,
        )
        window = self.book.words[window_start:window_end]
        window_bases = [w.base for w in window]
        window_norm = [normalize_for_matching(b) for b in window_bases]

        # Find best alignment within window
        best_score = 0
        best_offset = 0

        for offset in range(len(window_norm) - len(hyp_norm) + 1):
            candidate = window_norm[offset : offset + len(hyp_norm)]
            sm = difflib.SequenceMatcher(None, hyp_norm, candidate)
            score = sm.ratio()
            if score > best_score:
                best_score = score
                best_offset = offset

        # If match is too poor, try a wider search
        if best_score < 0.5:
            window_start = 0
            window_end = len(self.book.words)
            window = self.book.words[window_start:window_end]
            window_bases = [w.base for w in window]
            window_norm = [normalize_for_matching(b) for b in window_bases]

            for offset in range(len(window_norm) - len(hyp_norm) + 1):
                candidate = window_norm[offset : offset + len(hyp_norm)]
                sm = difflib.SequenceMatcher(None, hyp_norm, candidate)
                score = sm.ratio()
                if score > best_score:
                    best_score = score
                    best_offset = offset

        start_idx = window_start + best_offset
        end_idx = min(start_idx + len(hyp_bases), len(self.book.words))

        # Build matched pairs using SequenceMatcher for fine alignment
        matched_words = self.book.words[start_idx:end_idx]
        matched_norm = [normalize_for_matching(w.base) for w in matched_words]

        sm = difflib.SequenceMatcher(None, hyp_norm, matched_norm)
        pairs: list[tuple[BookWord, str]] = []

        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            if tag == "equal":
                for hi, bi in zip(range(i1, i2), range(j1, j2)):
                    pairs.append((matched_words[bi], hyp_words[hi]))
            elif tag == "replace":
                paired = min(i2 - i1, j2 - j1)
                for k in range(paired):
                    pairs.append((matched_words[j1 + k], hyp_words[i1 + k]))

        # Advance position
        self.current_position = end_idx

        return start_idx, end_idx, pairs

    def reset(self):
        """Reset to beginning of book."""
        self.current_position = 0
