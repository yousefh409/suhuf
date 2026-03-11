"""Pipeline orchestrator: ties together tracking, scoring, and diffing."""

import difflib
import unicodedata

import numpy as np

from .models import (
    BookWord,
    WordDiff,
    DiffKind,
    Confidence,
    ScoredWord,
    HARAKAT,
    HarakaDiff,
)
from .arabic import (
    strip_harakat,
    compare_harakat,
    normalize_arabic,
    normalize_for_matching,
    format_haraka_list,
)
from .book import Book
from .scorer import DiacriticsScorer
from .phoneme_scorer import PhonemeScorer
from .pcd_transcriber import PCDTranscriber
from .tracker import PositionTracker
from .config import Config
from .aligner import CTCAligner, is_available as ctc_available


_SHADDA = "\u0651"

# Internal vowel marks for tashkeel hypothesis scoring
_VOWELS = {"\u064E", "\u064F", "\u0650"}  # fatha, damma, kasra


def _generate_tashkeel_alternatives(word: str) -> list[tuple[str, int, str, str]]:
    """Generate alternative diacritizations at internal vowel positions.

    For each internal base letter (not first, not last) that has a vowel,
    generate variants by swapping the vowel with each of the other two.

    Returns list of (alternative_word, base_letter_idx, orig_vowel, new_vowel).
    """
    from .arabic import get_harakat_map
    base = strip_harakat(word)
    if len(base) < 3:
        return []

    hmap = get_harakat_map(word)
    alternatives = []

    for bi in range(1, len(base) - 1):  # internal positions only
        harakat = hmap.get(bi, [])
        # Find the vowel mark (not shadda)
        vowel = None
        for h in harakat:
            if h in _VOWELS:
                vowel = h
                break
        if vowel is None:
            continue

        # Generate alternatives by swapping with each other vowel
        for alt_vowel in _VOWELS:
            if alt_vowel == vowel:
                continue
            # Build alternative: replace the vowel at this position
            new_harakat = []
            for h in harakat:
                if h == vowel:
                    new_harakat.append(alt_vowel)
                else:
                    new_harakat.append(h)
            # Rebuild the word with the new harakat at this position
            chars = list(word)
            # Find the character position corresponding to base_idx bi
            base_idx = -1
            char_positions = {}
            for ci, ch in enumerate(word):
                if ch not in HARAKAT:
                    base_idx += 1
                    char_positions[base_idx] = ci
            if bi not in char_positions:
                continue
            # Replace harakat after this base letter
            cp = char_positions[bi]
            # Find extent of harakat after this base letter
            end = cp + 1
            while end < len(chars) and chars[end] in HARAKAT:
                end += 1
            # Build replacement
            new_word = word[:cp + 1] + "".join(new_harakat) + word[end:]
            new_word = unicodedata.normalize("NFC", new_word)
            if new_word != word:
                alternatives.append((new_word, bi, vowel, alt_vowel))

    return alternatives


def _clean_diacritics(text: str) -> str:
    """Normalize diacritics from CTC-decoded text.

    1. Per-letter: collect all harakat, deduplicate by type, put shadda first
    2. Apply NFC to canonicalise combining-character byte order

    CTC greedy decoding sometimes emits pathological diacritic sequences
    such as fatha+shadda+fatha (an extra fatha after a shadda+fatha cluster).
    A simple consecutive-dedup pass misses this because the two fathas are
    not adjacent.  This function therefore operates per-letter: for each base
    character it collects ALL following harakat, deduplicates by Unicode
    code-point (keeping first occurrence), and emits shadda before the vowel.

    Arabic diacritics have Unicode combining classes:
      fatha(30) < damma(31) < kasra(32) < shadda(33)
    NFC canonical order puts lower-cc marks first (vowel before shadda).
    This ensures decoded strings compare equal to book hypothesis strings
    regardless of which order the CTC tokeniser emits them.
    """
    result = []
    i = 0
    n = len(text)
    while i < n:
        c = text[i]
        if c in HARAKAT:
            # Isolated diacritics at the start (before any base letter) — keep as-is
            result.append(c)
            i += 1
        else:
            result.append(c)
            i += 1
            # Collect all following harakat for this letter
            marks = []
            while i < n and text[i] in HARAKAT:
                marks.append(text[i])
                i += 1
            if marks:
                # Deduplicate by code-point while preserving first-seen order
                seen_marks: set[str] = set()
                deduped_marks = []
                for m in marks:
                    if m not in seen_marks:
                        seen_marks.add(m)
                        deduped_marks.append(m)
                # Shadda (U+0651) goes first, then other harakat
                shadda_list = [m for m in deduped_marks if m == _SHADDA]
                other_list = [m for m in deduped_marks if m != _SHADDA]
                result.extend(shadda_list)
                result.extend(other_list)

    # NFC — final canonical byte ordering (also normalises shadda+vowel → vowel+shadda)
    return unicodedata.normalize("NFC", "".join(result))


class I3rabPipeline:
    """Main pipeline: audio in → diacritics assessment out."""

    def __init__(self, book: Book, config: Config | None = None):
        self.config = config or Config()
        self.book = book
        self.scorer = DiacriticsScorer(self.config)
        self.tracker = PositionTracker(book, self.config)
        self._ctc_aligner = None
        self._phoneme_scorer = None
        self._pcd_transcriber = None
        if ctc_available() and self.config.use_ctc_timestamps:
            self._ctc_aligner = CTCAligner(self.config)
        if self.config.use_phoneme_fallback:
            self._phoneme_scorer = PhonemeScorer(self.config)

    def load_models(self):
        """Pre-load all models."""
        self.scorer.load()
        if self._ctc_aligner:
            self._ctc_aligner.load()
        if self._phoneme_scorer:
            self._phoneme_scorer.load()

    def load_pcd(self):
        """Load the PCD transcriber (lazy — only when first needed)."""
        if self._pcd_transcriber is None:
            self._pcd_transcriber = PCDTranscriber(self.config)
        self._pcd_transcriber.load()


    def _align_timestamps(
        self,
        timestamps: list[dict],
        book_bases: list[str],
    ) -> list[tuple[float, float]] | None:
        """Align Whisper/CTC word timestamps to matched book words.

        Returns a list of (start, end) tuples parallel to book_bases,
        or None if alignment fails.
        """
        if not timestamps or not book_bases:
            return None

        ts_bases = [
            normalize_for_matching(normalize_arabic(t["word"])) for t in timestamps
        ]
        book_norm = [normalize_for_matching(b) for b in book_bases]

        sm = difflib.SequenceMatcher(None, book_norm, ts_bases)
        result: list[tuple[float, float] | None] = [None] * len(book_bases)

        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            if tag in ("equal", "replace"):
                paired = min(i2 - i1, j2 - j1)
                for k in range(paired):
                    ts = timestamps[j1 + k]
                    result[i1 + k] = (ts["start"], ts["end"])

        return result

    def _apply_phoneme_fallback(
        self,
        audio: np.ndarray,
        scored_words: list[ScoredWord],
        book_words: list[BookWord],
        word_timestamps: list[tuple[float, float] | None] | None,
    ) -> list[ScoredWord]:
        """Re-score low-confidence words using phoneme CTC model.

        Runs the phoneme model once on the full audio, then uses timestamps
        to extract per-word logits and score each hypothesis via CTC loss.
        Only overrides Whisper's verdict for non-HIGH confidence words.
        """
        if not self._phoneme_scorer or not word_timestamps:
            return scored_words

        # Check if any word needs rescoring before loading the model
        needs_rescore = any(
            word_timestamps[i] is not None
            and scored.confidence != Confidence.HIGH
            and len(scored.word.hypotheses) > 1
            for i, scored in enumerate(scored_words)
        )
        if not needs_rescore:
            return scored_words

        # Run phoneme model once on full audio
        phoneme_logits = self._phoneme_scorer.get_logits(audio)

        results = list(scored_words)
        for i, scored in enumerate(results):
            if word_timestamps[i] is None:
                continue
            if len(scored.word.hypotheses) <= 1:
                continue
            if scored.confidence == Confidence.HIGH:
                continue

            start_sec, end_sec = word_timestamps[i]
            phoneme_result = self._phoneme_scorer.score_word(
                audio, scored.word, book_words,
                word_start=start_sec,
                word_end=end_sec,
                logits=phoneme_logits,
            )
            if phoneme_result is not None:
                results[i] = phoneme_result

        return results

    def evaluate_phrase(self, audio: np.ndarray) -> dict:
        """Evaluate a phrase of audio against the book.

        Returns a dict with:
        - transcript: what ASR thinks the user said
        - results: list of WordDiff objects
        - score: {correct, total}
        - phrase_idx: which phrase in the book
        - words_assessed: list of detailed scoring info
        """
        # Step 1: Transcribe with timestamps for position tracking + per-word scoring
        transcript, whisper_timestamps = self.scorer.transcribe_with_timestamps(audio)
        transcript_normalized = normalize_arabic(transcript)

        # Step 2: Find position in book
        start_idx, end_idx, matched_pairs = self.tracker.locate(transcript_normalized)

        if not matched_pairs:
            return {
                "transcript": transcript_normalized,
                "results": [],
                "score": {"correct": 0, "total": 0},
                "phrase_idx": None,
                "words_assessed": [],
            }

        # Step 3: Score diacritics for matched words
        book_words = [bw for bw, _ in matched_pairs]

        # Try CTC alignment for better timestamps, fall back to Whisper timestamps
        timestamps = whisper_timestamps
        if self._ctc_aligner and transcript_normalized:
            ctc_timestamps = self._ctc_aligner.align(audio, transcript_normalized)
            if ctc_timestamps:
                timestamps = ctc_timestamps

        # Align timestamps to matched book words
        word_timestamps = self._align_timestamps(
            timestamps, [bw.base for bw in book_words]
        )
        scored_words = self.scorer.score_phrase(audio, book_words, word_timestamps)

        # Step 3b: Phoneme fallback for low-confidence words
        scored_words = self._apply_phoneme_fallback(
            audio, scored_words, book_words, word_timestamps
        )

        # Step 4: Build diff results
        results = []
        words_assessed = []

        for (book_word, hyp_text), scored in zip(matched_pairs, scored_words):
            diff = self._build_word_diff(book_word, hyp_text, scored)
            results.append(diff)

            words_assessed.append({
                "index": book_word.index,
                "reference": book_word.correct_diac,
                "base": book_word.base,
                "detected": scored.detected_hyp.diacritized if scored.detected_hyp else None,
                "detected_case": scored.detected_hyp.case if scored.detected_hyp else None,
                "confidence": scored.confidence.value,
                "score_gap": scored.score_gap,
                "is_correct": diff.kind in (DiffKind.CORRECT, DiffKind.PAUSAL_OK),
                "num_hypotheses": len(book_word.hypotheses),
            })

        # Score
        correct = sum(
            1 for d in results
            if d.kind in (DiffKind.CORRECT, DiffKind.PAUSAL_OK)
        )

        phrase = self.book.get_phrase_for_position(start_idx)

        return {
            "transcript": transcript_normalized,
            "results": results,
            "score": {"correct": correct, "total": len(results)},
            "phrase_idx": self.book.phrases.index(phrase) if phrase else None,
            "words_assessed": words_assessed,
        }

    def evaluate_phrase_streaming(self, audio: np.ndarray):
        """Evaluate a phrase, yielding SSE-ready events word by word.

        Yields dicts with an 'event' key and additional data fields:
        - transcript: the ASR transcription
        - word_start: about to score a word
        - word_result: scored result for a word
        - done: final score summary
        """
        # Step 1: Transcribe with timestamps
        transcript, whisper_timestamps = self.scorer.transcribe_with_timestamps(audio)
        transcript_normalized = normalize_arabic(transcript)

        yield {"event": "transcript", "transcript": transcript_normalized}

        # Step 2: Find position in book
        start_idx, end_idx, matched_pairs = self.tracker.locate(transcript_normalized)

        if not matched_pairs:
            yield {"event": "done", "score": {"correct": 0, "total": 0}}
            return

        book_words = [bw for bw, _ in matched_pairs]

        # Try CTC alignment for better timestamps
        timestamps = whisper_timestamps
        if self._ctc_aligner and transcript_normalized:
            ctc_timestamps = self._ctc_aligner.align(audio, transcript_normalized)
            if ctc_timestamps:
                timestamps = ctc_timestamps

        word_timestamps = self._align_timestamps(
            timestamps, [bw.base for bw in book_words]
        )

        # Encode full audio once
        encoder_outputs = self.scorer._get_encoder_output(audio)
        phoneme_logits = None  # lazy-loaded if needed

        correct = 0
        total = len(matched_pairs)

        for i, (book_word, hyp_text) in enumerate(matched_pairs):
            # Signal: starting to score this word
            yield {
                "event": "word_start",
                "index": book_word.index,
                "word": book_word.correct_diac,
            }

            # Always use contextual scoring for best accuracy
            scored = self.scorer.score_word_in_context(
                audio, book_word, book_words, encoder_outputs
            )

            # Phoneme fallback for non-HIGH confidence words
            if (
                self._phoneme_scorer
                and word_timestamps
                and word_timestamps[i] is not None
                and scored.confidence != Confidence.HIGH
                and len(book_word.hypotheses) > 1
            ):
                if phoneme_logits is None:
                    phoneme_logits = self._phoneme_scorer.get_logits(audio)
                start_sec, end_sec = word_timestamps[i]
                phoneme_result = self._phoneme_scorer.score_word(
                    audio, book_word, book_words,
                    word_start=start_sec,
                    word_end=end_sec,
                    logits=phoneme_logits,
                )
                if phoneme_result is not None:
                    scored = phoneme_result

            diff = self._build_word_diff(book_word, hyp_text, scored)

            if diff.kind in (DiffKind.CORRECT, DiffKind.PAUSAL_OK):
                correct += 1

            # Serialize haraka diffs
            haraka_diffs_json = []
            for hd in diff.haraka_diffs:
                haraka_diffs_json.append({
                    "letter": hd.letter,
                    "position": hd.position,
                    "expected": format_haraka_list(hd.expected),
                    "got": format_haraka_list(hd.got),
                    "is_irab": hd.is_irab,
                })

            yield {
                "event": "word_result",
                "index": book_word.index,
                "kind": diff.kind.value,
                "ref_word": diff.ref_word,
                "hyp_word": diff.hyp_word,
                "haraka_diffs": haraka_diffs_json,
                "confidence": diff.confidence.value if isinstance(diff.confidence, Confidence) else "high",
                "detected_case": diff.detected_case,
                "expected_case": diff.expected_case,
            }

        yield {"event": "done", "score": {"correct": correct, "total": total}}

    def _build_word_diff(
        self,
        book_word: BookWord,
        hyp_text: str,
        scored: ScoredWord,
    ) -> WordDiff:
        """Build a WordDiff from scoring results."""
        detected = scored.detected_hyp

        if detected is None:
            return WordDiff(
                kind=DiffKind.MISSING,
                ref_word=book_word.correct_diac,
                hyp_word=None,
                confidence=Confidence.LOW,
            )

        # Check if base words match (normalize to handle ASR variants like ة addition)
        hyp_norm = normalize_for_matching(hyp_text)
        book_norm = normalize_for_matching(book_word.base)
        if hyp_norm != book_norm:
            # Fuzzy tolerance: if words are very similar, it's likely an ASR
            # artifact rather than the user reading a different word.
            # Use SequenceMatcher ratio as a similarity metric.
            similarity = difflib.SequenceMatcher(None, hyp_norm, book_norm).ratio()
            if similarity < 0.6:
                return WordDiff(
                    kind=DiffKind.WRONG_WORD,
                    ref_word=book_word.correct_diac,
                    hyp_word=hyp_text,
                    confidence=scored.confidence,
                )
            # Similar enough — proceed with hypothesis scoring (ASR noise tolerance)

        # Check if detected matches correct
        if detected.is_correct:
            return WordDiff(
                kind=DiffKind.CORRECT,
                ref_word=book_word.correct_diac,
                hyp_word=detected.diacritized,
                confidence=scored.confidence,
            )

        # Safety net: if the detected grammatical case matches the expected
        # case, treat the word as correct even when is_correct=False.
        #
        # This handles a Unicode byte-ordering edge case: when the last letter
        # carries a shadda, _generate_irab_hypotheses (before the NFC fix) may
        # produce TWO hypotheses with the same surface form but different byte
        # order (e.g. vowel+shadda vs shadda+vowel).  The CTC scorer can then
        # pick the non-canonical copy (is_correct=False) even though it encodes
        # the correct grammatical case, causing a false WRONG_IRAB.
        #
        # Keeping this check is harmless after the NFC fix is applied to
        # _generate_irab_hypotheses (duplicates are no longer generated), but
        # it acts as a robust fallback for any residual ordering discrepancies.
        expected_case = next(
            (h.case for h in book_word.hypotheses if h.is_correct), None
        )
        if expected_case and detected.case == expected_case:
            return WordDiff(
                kind=DiffKind.CORRECT,
                ref_word=book_word.correct_diac,
                hyp_word=book_word.correct_diac,  # report canonical ref form
                confidence=scored.confidence,
            )

        # Check if detected case is "related" to expected (e.g., nom ↔ nom_indef)
        # Tanween vs single haraka share the same grammatical role
        RELATED_CASES = {
            "nom": "nom_indef", "nom_indef": "nom",
            "acc": "acc_indef", "acc_indef": "acc",
            "gen": "gen_indef", "gen_indef": "gen",
        }
        if expected_case and detected.case == RELATED_CASES.get(expected_case):
            return WordDiff(
                kind=DiffKind.PAUSAL_OK,
                ref_word=book_word.correct_diac,
                hyp_word=detected.diacritized,
                confidence=scored.confidence,
                detected_case=detected.case,
                expected_case=expected_case,
            )

        # Check if pausal form is acceptable (bidirectional)
        # Forward: detected=pausal, expected=has-vowel → reader stopped
        # Reverse: expected=pausal, detected=has-vowel → reader added case
        # Both are acceptable when pausal is allowed.
        if detected.is_pausal and book_word.allows_pausal:
            return WordDiff(
                kind=DiffKind.PAUSAL_OK,
                ref_word=book_word.correct_diac,
                hyp_word=detected.diacritized,
                confidence=scored.confidence,
                detected_case="pausal",
            )
        if (
            book_word.allows_pausal
            and expected_case in ("pausal", "jussive")
            and not detected.is_pausal
        ):
            # Reference is pausal (no case specified); reader produced a
            # case ending.  Since the reference doesn't mandate a specific
            # case, any vowelised form is acceptable.
            return WordDiff(
                kind=DiffKind.PAUSAL_OK,
                ref_word=book_word.correct_diac,
                hyp_word=detected.diacritized,
                confidence=scored.confidence,
                detected_case=detected.case,
                expected_case=expected_case,
            )

        # Wrong diacritics — determine if it's i3rab or internal tashkeel
        haraka_diffs = compare_harakat(book_word.correct_diac, detected.diacritized)

        if not haraka_diffs:
            return WordDiff(
                kind=DiffKind.CORRECT,
                ref_word=book_word.correct_diac,
                hyp_word=detected.diacritized,
                confidence=scored.confidence,
            )

        # Check if error is only on the last letter (i3rab) or internal (tashkeel)
        has_irab_error = any(hd.is_irab for hd in haraka_diffs)
        has_internal_error = any(not hd.is_irab for hd in haraka_diffs)

        if has_irab_error and not has_internal_error:
            kind = DiffKind.WRONG_IRAB
        else:
            kind = DiffKind.WRONG_TASHKEEL

        return WordDiff(
            kind=kind,
            ref_word=book_word.correct_diac,
            hyp_word=detected.diacritized,
            haraka_diffs=haraka_diffs,
            confidence=scored.confidence,
            detected_case=detected.case,
            expected_case=next(
                (h.case for h in book_word.hypotheses if h.is_correct), None
            ),
        )

    def evaluate_simple(self, audio: np.ndarray, reference: str) -> dict:
        """Simplified evaluation: transcribe and diff against a reference.

        This is the legacy mode (like the original main.py) but enhanced
        with hypothesis scoring when the book is loaded.
        """
        transcript = self.scorer.transcribe(audio)
        transcript = normalize_arabic(transcript)

        if not transcript.strip():
            return {
                "transcript": "",
                "results": [],
                "score": {"correct": 0, "total": 0},
            }

        ref_normalized = normalize_arabic(reference)
        ref_words = ref_normalized.split()
        hyp_words = transcript.split()

        # Build a temporary book from the reference
        temp_book = Book.from_sentence(reference)

        # Score using hypothesis testing
        scored = self.scorer.score_phrase(audio, temp_book.words)

        results = []
        # Align ref and hyp words
        ref_bases = [strip_harakat(w) for w in ref_words]
        hyp_bases = [strip_harakat(w) for w in hyp_words]

        sm = difflib.SequenceMatcher(None, ref_bases, hyp_bases)

        scored_idx = 0
        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            if tag == "equal":
                for ri, hi in zip(range(i1, i2), range(j1, j2)):
                    if scored_idx < len(scored):
                        diff = self._build_word_diff(
                            temp_book.words[ri] if ri < len(temp_book.words) else
                            BookWord(ri, ref_bases[ri], ref_words[ri], [], False),
                            hyp_words[hi],
                            scored[scored_idx],
                        )
                        scored_idx += 1
                    else:
                        # Fallback to simple comparison
                        if ref_words[ri] == hyp_words[hi]:
                            diff = WordDiff(DiffKind.CORRECT, ref_words[ri], hyp_words[hi])
                        else:
                            hd = compare_harakat(ref_words[ri], hyp_words[hi])
                            diff = WordDiff(DiffKind.WRONG_TASHKEEL, ref_words[ri], hyp_words[hi], hd)
                    results.append(diff)

            elif tag == "replace":
                paired = min(i2 - i1, j2 - j1)
                for offset in range(paired):
                    ri = i1 + offset
                    hi = j1 + offset
                    if ref_bases[ri] == hyp_bases[hi]:
                        if ref_words[ri] == hyp_words[hi]:
                            results.append(WordDiff(DiffKind.CORRECT, ref_words[ri], hyp_words[hi]))
                        else:
                            hd = compare_harakat(ref_words[ri], hyp_words[hi])
                            results.append(WordDiff(DiffKind.WRONG_TASHKEEL, ref_words[ri], hyp_words[hi], hd))
                    else:
                        results.append(WordDiff(DiffKind.WRONG_WORD, ref_words[ri], hyp_words[hi]))
                for ri in range(i1 + paired, i2):
                    results.append(WordDiff(DiffKind.MISSING, ref_words[ri], None))
                for hi in range(j1 + paired, j2):
                    results.append(WordDiff(DiffKind.EXTRA, None, hyp_words[hi]))

            elif tag == "delete":
                for ri in range(i1, i2):
                    results.append(WordDiff(DiffKind.MISSING, ref_words[ri], None))

            elif tag == "insert":
                for hi in range(j1, j2):
                    results.append(WordDiff(DiffKind.EXTRA, None, hyp_words[hi]))

        correct = sum(1 for d in results if d.kind in (DiffKind.CORRECT, DiffKind.PAUSAL_OK))

        return {
            "transcript": transcript,
            "results": results,
            "score": {"correct": correct, "total": len(results)},
        }

    def evaluate_pcd(self, audio: np.ndarray) -> dict:
        """Evaluate using PCD model: transcribe with diacritics, then diff.

        The PCD model directly outputs diacritized text. We align the
        PCD transcription against the reference and compare diacritics
        word-by-word.

        Returns same format as evaluate_phrase for UI compatibility.
        """
        self.load_pcd()

        # Step 1: Get diacritized transcription from PCD model
        pcd_text = self._pcd_transcriber.transcribe(audio)

        if not pcd_text.strip():
            return {
                "transcript": "",
                "results": [],
                "score": {"correct": 0, "total": 0},
                "phrase_idx": None,
                "words_assessed": [],
                "mode": "pcd",
            }

        # Step 2: Also get undiacritized transcript for position tracking
        pcd_normalized = normalize_arabic(pcd_text)

        # Step 3: Find position in book using base text
        start_idx, end_idx, matched_pairs = self.tracker.locate(
            strip_harakat(pcd_normalized)
        )

        if not matched_pairs:
            return {
                "transcript": pcd_text,
                "results": [],
                "score": {"correct": 0, "total": 0},
                "phrase_idx": None,
                "words_assessed": [],
                "mode": "pcd",
            }

        # Step 4: Align PCD words to book words and diff
        aligned = self._match_pcd_words(pcd_text, matched_pairs)

        results = []
        words_assessed = []

        for book_word, pcd_match in aligned:
            diff = self._diff_pcd_word(book_word, pcd_match)
            results.append(diff)

            words_assessed.append({
                "index": book_word.index,
                "reference": book_word.correct_diac,
                "base": book_word.base,
                "detected": diff.hyp_word,
                "detected_case": None,
                "confidence": diff.confidence.value,
                "score_gap": 0.0,
                "is_correct": diff.kind in (DiffKind.CORRECT, DiffKind.PAUSAL_OK),
                "num_hypotheses": len(book_word.hypotheses),
            })

        correct = sum(
            1 for d in results
            if d.kind in (DiffKind.CORRECT, DiffKind.PAUSAL_OK)
        )

        phrase = self.book.get_phrase_for_position(start_idx)

        return {
            "transcript": pcd_text,
            "results": results,
            "score": {"correct": correct, "total": len(results)},
            "phrase_idx": self.book.phrases.index(phrase) if phrase else None,
            "words_assessed": words_assessed,
            "mode": "pcd",
        }

    def _diff_pcd_word(self, book_word: BookWord, pcd_match: str | None) -> WordDiff:
        """Compare a single PCD-transcribed word against its reference."""
        if pcd_match is None:
            return WordDiff(
                kind=DiffKind.MISSING,
                ref_word=book_word.correct_diac,
                hyp_word=None,
                confidence=Confidence.LOW,
            )

        if pcd_match == book_word.correct_diac:
            return WordDiff(
                kind=DiffKind.CORRECT,
                ref_word=book_word.correct_diac,
                hyp_word=pcd_match,
                confidence=Confidence.HIGH,
            )

        pcd_base = strip_harakat(pcd_match)
        sim = difflib.SequenceMatcher(
            None,
            normalize_for_matching(pcd_base),
            normalize_for_matching(book_word.base),
        ).ratio()

        if sim < 0.6:
            return WordDiff(
                kind=DiffKind.WRONG_WORD,
                ref_word=book_word.correct_diac,
                hyp_word=pcd_match,
                confidence=Confidence.MEDIUM,
            )

        haraka_diffs = compare_harakat(book_word.correct_diac, pcd_match)
        has_irab = any(hd.is_irab for hd in haraka_diffs)
        has_internal = any(not hd.is_irab for hd in haraka_diffs)

        if not haraka_diffs:
            kind = DiffKind.CORRECT
        elif has_irab and not has_internal:
            kind = DiffKind.WRONG_IRAB
        else:
            kind = DiffKind.WRONG_TASHKEEL

        return WordDiff(
            kind=kind,
            ref_word=book_word.correct_diac,
            hyp_word=pcd_match,
            haraka_diffs=haraka_diffs,
            confidence=Confidence.MEDIUM,
        )

    def _match_pcd_words(
        self, pcd_text: str, matched_pairs: list
    ) -> list[tuple[BookWord, str | None]]:
        """Align normalized PCD words to matched book words."""
        pcd_normalized = normalize_arabic(pcd_text)
        pcd_words = pcd_normalized.split()
        pcd_bases = [strip_harakat(w) for w in pcd_words]
        pcd_used = [False] * len(pcd_words)

        aligned = []
        for book_word, _hyp_text in matched_pairs:
            book_base = normalize_for_matching(book_word.base)
            pcd_match = None
            for k, (pw, pb) in enumerate(zip(pcd_words, pcd_bases)):
                if not pcd_used[k] and normalize_for_matching(pb) == book_base:
                    pcd_match = pw
                    pcd_used[k] = True
                    break
            aligned.append((book_word, pcd_match))
        return aligned

    def evaluate_pcd_live(
        self, audio: np.ndarray, already_scored: set[int] | None = None
    ) -> dict:
        """Forced-alignment PCD evaluation — single encoder pass.

        1. Encode audio once → log_probs + free transcript
        2. Free transcript → position tracking (which book words were read?)
        3. Fill gaps: include ALL book words between first and last matched
        4. Forced alignment → per-word frame boundaries
        5. Edge recovery: check for unaligned frames at start/end of audio,
           try aligning neighboring book words against those frames
        6. Per-word i3rab: full-sentence CTC hypothesis scoring
        7. Per-word tashkeel: greedy decode + CTC-verified comparison

        Free transcript is ONLY used for position tracking.
        All accuracy-sensitive work uses forced alignment + CTC scoring.

        Does NOT advance the tracker — safe for repeated calls.
        """
        self.load_pcd()
        already_scored = already_scored or set()

        # ── Step 1: Single encoder pass ──────────────────────────────
        pcd_text, log_probs, encoded_len, encoded = (
            self._pcd_transcriber.transcribe_and_encode(audio)
        )

        if not pcd_text.strip():
            return {"transcript": "", "matched_indices": [], "scored_words": []}

        pcd_normalized = normalize_arabic(pcd_text)

        # ── Step 2: Position tracking using free transcript ──────────
        saved_pos = self.tracker.current_position
        start_idx, end_idx, matched_pairs = self.tracker.locate(
            strip_harakat(pcd_normalized)
        )
        self.tracker.current_position = saved_pos

        if not matched_pairs:
            return {
                "transcript": pcd_normalized,
                "matched_indices": [],
                "scored_words": [],
            }

        # Build free-transcript cross-reference: book_word.index → free word
        free_word_map: dict[int, str] = {
            bw.index: tw for bw, tw in matched_pairs
        }

        # ── Step 3: Fill gaps between matched words ──────────────────
        # Use ALL book words between the first and last matched indices.
        # This recovers words that the free transcript garbled but that
        # are between correctly-identified words.
        matched_book_indices = sorted(bw.index for bw, _ in matched_pairs)
        fill_start = matched_book_indices[0]
        fill_end = matched_book_indices[-1] + 1
        all_words = list(self.book.words[fill_start:fill_end])

        # ── Step 4: Forced alignment ─────────────────────────────────
        reference_words = [bw.correct_diac for bw in all_words]
        reference_text = " ".join(reference_words)

        alignment, align_scores = (
            self._pcd_transcriber.forced_align_reference(
                log_probs, encoded_len, reference_text
            )
        )

        if alignment is None:
            return {
                "transcript": pcd_normalized,
                "matched_indices": [bw.index for bw, _ in matched_pairs],
                "scored_words": [],
            }

        word_boundaries = self._pcd_transcriber.get_word_boundaries(
            alignment, align_scores, reference_words
        )

        # ── Step 5: Edge recovery ────────────────────────────────────
        # Check for significant unaligned frames at the edges of the
        # audio. If there's audio before the first word or after the
        # last word, try adding neighboring book words.
        T = encoded_len[0].item()
        phrase = self.book.get_phrase_for_position(fill_start)
        phrase_start = phrase.start_idx if phrase else 0
        phrase_end = phrase.end_idx if phrase else len(self.book.words)

        first_frame = word_boundaries[0].start_frame if word_boundaries else T
        last_frame = word_boundaries[-1].end_frame if word_boundaries else 0

        # Recover word(s) BEFORE the first matched word
        if first_frame > 8 and fill_start > phrase_start:
            prev_word = self.book.words[fill_start - 1]
            expanded = [prev_word] + all_words
            exp_ref = [bw.correct_diac for bw in expanded]
            exp_align, exp_scores = (
                self._pcd_transcriber.forced_align_reference(
                    log_probs, encoded_len, " ".join(exp_ref)
                )
            )
            if exp_align is not None:
                exp_bounds = self._pcd_transcriber.get_word_boundaries(
                    exp_align, exp_scores, exp_ref
                )
                # Accept if the new word got reasonable alignment
                if exp_bounds and exp_bounds[0].score > -4.0:
                    all_words = expanded
                    reference_words = exp_ref
                    word_boundaries = exp_bounds

        last_frame = word_boundaries[-1].end_frame if word_boundaries else 0
        # Recover word(s) AFTER the last matched word
        if T - last_frame > 8 and fill_end < phrase_end:
            next_word = self.book.words[fill_end]
            expanded = all_words + [next_word]
            exp_ref = [bw.correct_diac for bw in expanded]
            exp_align, exp_scores = (
                self._pcd_transcriber.forced_align_reference(
                    log_probs, encoded_len, " ".join(exp_ref)
                )
            )
            if exp_align is not None:
                exp_bounds = self._pcd_transcriber.get_word_boundaries(
                    exp_align, exp_scores, exp_ref
                )
                # Accept if the new word got reasonable alignment
                if exp_bounds and exp_bounds[-1].score > -4.0:
                    all_words = expanded
                    reference_words = exp_ref
                    word_boundaries = exp_bounds

        # ── Step 6: Per-word scoring ─────────────────────────────────

        # Pre-compute joint scores if enabled
        joint_scores: dict[int, ScoredWord] | None = None
        if getattr(self.config, "use_joint_scoring", False):
            joint_results = self._pcd_transcriber.score_words_joint(
                log_probs, encoded_len, all_words,
            )
            joint_scores = {
                all_words[j].index: jr
                for j, jr in enumerate(joint_results)
            }

        matched_indices = []
        scored_words = []

        for i, book_word in enumerate(all_words):
            if book_word.index in already_scored:
                continue

            wb = word_boundaries[i] if i < len(word_boundaries) else None

            # Missing detection: no frames or very low alignment score
            if wb is None or wb.start_frame >= wb.end_frame:
                diff = WordDiff(
                    kind=DiffKind.MISSING,
                    ref_word=book_word.correct_diac,
                    hyp_word=None,
                    confidence=Confidence.LOW,
                )
            else:
                sf, ef = wb.start_frame, wb.end_frame

                # ── Word identity check via free transcript ──────
                # If the free transcript's consonant skeleton doesn't
                # match the book word, the reader said a different word.
                # CTC-verify: only flag if a sentence with the free
                # transcript word genuinely scores better than the
                # reference (avoids noisy free-decode false positives).
                _wrong_word_detected = False
                free_word = free_word_map.get(book_word.index)
                if free_word:
                    free_base = strip_harakat(free_word)
                    book_base = strip_harakat(book_word.base)
                    if free_base != book_base:
                        sim = difflib.SequenceMatcher(
                            None, free_base, book_base
                        ).ratio()
                        if sim < 0.5:
                            ref_parts = [
                                w.correct_diac for w in all_words
                            ]
                            free_parts = list(ref_parts)
                            free_parts[i] = free_word
                            ref_sc = self._pcd_transcriber._ctc_score(
                                log_probs, encoded_len,
                                " ".join(ref_parts),
                            )
                            free_sc = self._pcd_transcriber._ctc_score(
                                log_probs, encoded_len,
                                " ".join(free_parts),
                            )
                            if free_sc > ref_sc + 2.0:
                                _wrong_word_detected = True
                                diff = WordDiff(
                                    kind=DiffKind.WRONG_WORD,
                                    ref_word=book_word.correct_diac,
                                    hyp_word=free_word,
                                    confidence=Confidence.HIGH,
                                )

                # ── I3rab: full-sentence CTC hypothesis scoring ──
                if _wrong_word_detected:
                    pass  # skip scoring, already have diff
                elif len(book_word.hypotheses) > 1:
                    if joint_scores is not None:
                        scored = joint_scores[book_word.index]
                    else:
                        scored = self._pcd_transcriber.score_word_in_context(
                            log_probs, encoded_len,
                            book_word, all_words,
                            encoded=encoded,
                            rnnt_weight=getattr(self.config, "rnnt_weight", 0.0),
                        )

                    # Low-confidence fallback: when CTC can't
                    # confidently distinguish hypotheses, assume
                    # the student read correctly.  Better to miss
                    # an error than flag a correct reading.
                    if scored.confidence == Confidence.LOW:
                        correct_hyp = next(
                            (h for h in book_word.hypotheses
                             if h.is_correct),
                            scored.detected_hyp,
                        )
                        scored = ScoredWord(
                            word=book_word,
                            detected_hyp=correct_hyp,
                            confidence=Confidence.LOW,
                            score_gap=scored.score_gap,
                        )

                    # Pausal-bias re-verification:
                    #
                    # The CTC model has a structural preference for
                    # pausal/jussive (no final vowel) because final
                    # short vowels are acoustically brief and the
                    # shorter token sequence always has a CTC
                    # advantage.  When the detected hypothesis is
                    # pausal or jussive but the correct form has a
                    # final vowel, we re-score both full-sentence
                    # variants and only keep the pausal verdict if it
                    # is convincingly better (margin > PAUSAL_MARGIN).
                    # Otherwise we revert to the correct hypothesis.
                    #
                    # This is deliberately conservative (PAUSAL_MARGIN
                    # > the generic 2.0 used elsewhere) to avoid
                    # masking genuine pausal errors at true phrase
                    # boundaries.
                    _PAUSAL_CASES = {"pausal", "jussive"}
                    _PAUSAL_MARGIN = 2.0

                    det = scored.detected_hyp
                    correct_hyp = next(
                        (h for h in book_word.hypotheses if h.is_correct),
                        None,
                    )
                    if (
                        det is not None
                        and correct_hyp is not None
                        and not correct_hyp.is_pausal
                        and det.case in _PAUSAL_CASES
                        and not det.is_correct
                        and scored.confidence in (
                            Confidence.HIGH, Confidence.MEDIUM
                        )
                    ):
                        # Build full-sentence texts for both variants
                        ctx_parts = [w.correct_diac for w in all_words]
                        target_pos = next(
                            j for j, w in enumerate(all_words)
                            if w.index == book_word.index
                        )
                        correct_parts = list(ctx_parts)
                        correct_parts[target_pos] = correct_hyp.diacritized
                        pausal_parts = list(ctx_parts)
                        pausal_parts[target_pos] = det.diacritized

                        correct_score = self._pcd_transcriber._ctc_score(
                            log_probs, encoded_len,
                            " ".join(correct_parts),
                        )
                        pausal_score = self._pcd_transcriber._ctc_score(
                            log_probs, encoded_len,
                            " ".join(pausal_parts),
                        )

                        # If the pausal variant is not convincingly
                        # better than the correct variant, assume
                        # the model is exhibiting pausal bias and
                        # revert to the correct hypothesis.
                        if pausal_score <= correct_score + _PAUSAL_MARGIN:
                            scored = ScoredWord(
                                word=book_word,
                                detected_hyp=correct_hyp,
                                confidence=scored.confidence,
                                score_gap=scored.score_gap,
                            )

                    # ── Segment-level cross-check for i3rab ────────
                    # Full-sentence CTC may prefer a wrong case ending
                    # due to context effects.  Cross-check by scoring
                    # ONLY the word's audio segment: if the segment
                    # prefers the correct hypothesis (or can't decide),
                    # revert to correct.
                    det = scored.detected_hyp
                    if (
                        det is not None
                        and not det.is_correct
                        and not det.is_pausal
                        and correct_hyp is not None
                        and wb is not None
                        and scored.confidence in (
                            Confidence.HIGH, Confidence.MEDIUM
                        )
                    ):
                        _seg_correct = self._pcd_transcriber._ctc_score_segment(
                            log_probs, sf, ef, correct_hyp.diacritized
                        )
                        _seg_detected = self._pcd_transcriber._ctc_score_segment(
                            log_probs, sf, ef, det.diacritized
                        )
                        # If segment doesn't agree that detected is
                        # better, revert to correct
                        _SEG_MARGIN = 1.0
                        if _seg_detected <= _seg_correct + _SEG_MARGIN:
                            scored = ScoredWord(
                                word=book_word,
                                detected_hyp=correct_hyp,
                                confidence=scored.confidence,
                                score_gap=scored.score_gap,
                            )

                    diff = self._build_word_diff(
                        book_word, book_word.base, scored
                    )

                    # Liaison kasra tolerance: when a word ends in ت
                    # and the reference has kasra (liaison before ال),
                    # but CTC detected sukun/jussive, this is a
                    # phonological connector, not an i3rab error.
                    if (
                        diff.kind == DiffKind.WRONG_IRAB
                        and diff.expected_case == "gen"
                        and diff.detected_case in ("jussive", "pausal")
                        and book_word.base.endswith("\u062a")  # ت
                        and i + 1 < len(all_words)
                        and all_words[i + 1].base.startswith("\u0627\u0644")  # ال
                    ):
                        diff = WordDiff(
                            kind=DiffKind.PAUSAL_OK,
                            ref_word=book_word.correct_diac,
                            hyp_word=diff.hyp_word,
                            confidence=diff.confidence,
                            detected_case=diff.detected_case,
                            expected_case=diff.expected_case,
                        )

                else:
                    # Single hypothesis (particle/preposition)
                    hyp = book_word.hypotheses[0] if book_word.hypotheses else None
                    scored = ScoredWord(
                        word=book_word,
                        detected_hyp=hyp,
                        confidence=Confidence.HIGH,
                        score_gap=float("inf"),
                    )
                    diff = self._build_word_diff(
                        book_word, book_word.base, scored
                    )

                # ── Tashkeel + wrong-word: per-word decode + verification ─
                # Skip for known particles where CTC systematically
                # drops diacritics (e.g., إِلَى → إلَى)
                _SKIP_TASHKEEL_BASES = {
                    "إلى", "الى", "على", "عن", "من", "في",
                    "ان", "أن", "إن", "هل", "ما", "لا",
                    "ثم", "لم", "لن",
                }
                if (
                    diff.kind in (DiffKind.CORRECT, DiffKind.PAUSAL_OK)
                    and wb is not None
                    and wb.score > -2.0
                    and book_word.base not in _SKIP_TASHKEEL_BASES
                ):
                    raw_decoded = self._pcd_transcriber.decode_word_segment(
                        log_probs, sf, ef
                    )
                    decoded_word = normalize_arabic(
                        _clean_diacritics(raw_decoded)
                    )
                    ref_norm = normalize_arabic(book_word.correct_diac)

                    dec_base = strip_harakat(decoded_word) if decoded_word else ""
                    ref_base = strip_harakat(ref_norm)

                    # ── Wrong word via per-word decode ──
                    # If the decoded segment's consonants strongly differ
                    # from the reference, the reader said a different word.
                    # CTC-verify: only flag if the decoded version scores
                    # better than the reference (avoids noisy short decodes).
                    if (
                        decoded_word
                        and dec_base != ref_base
                        and dec_base  # non-empty decode
                    ):
                        seg_sim = difflib.SequenceMatcher(
                            None, dec_base, ref_base
                        ).ratio()
                        if seg_sim < 0.5:
                            ref_parts = [w.correct_diac for w in all_words]
                            dec_parts = list(ref_parts)
                            dec_parts[i] = decoded_word
                            ref_sc = self._pcd_transcriber._ctc_score(
                                log_probs, encoded_len,
                                " ".join(ref_parts),
                            )
                            dec_sc = self._pcd_transcriber._ctc_score(
                                log_probs, encoded_len,
                                " ".join(dec_parts),
                            )
                            if dec_sc > ref_sc + 2.0:
                                diff = WordDiff(
                                    kind=DiffKind.WRONG_WORD,
                                    ref_word=book_word.correct_diac,
                                    hyp_word=decoded_word,
                                    confidence=Confidence.HIGH,
                                )

                    # ── Tashkeel verification ──
                    elif (
                        decoded_word
                        and dec_base == ref_base
                        and decoded_word != ref_norm
                    ):
                        tashkeel_diffs = compare_harakat(
                            ref_norm, decoded_word
                        )

                        # For single-hypothesis words (particles),
                        # also check i3rab-position errors since there's
                        # no hypothesis scoring to catch them.
                        single_hyp = len(book_word.hypotheses) <= 1

                        # All tashkeel errors (substitution + omission)
                        tashkeel_errs = [
                            hd for hd in tashkeel_diffs
                            if not hd.is_irab or single_hyp
                        ]

                        # CTC-verify tashkeel errors: build two
                        # full sentences (ref vs decoded) and only flag
                        # errors if the decoded version genuinely scores
                        # better against the audio.
                        # Single-position errors require a higher
                        # threshold since CTC commonly confuses
                        # individual vowels (noise floor issue).
                        all_errors = []
                        if tashkeel_errs:
                            ref_parts = [w.correct_diac for w in all_words]
                            word_offset = i
                            dec_parts = list(ref_parts)
                            dec_parts[word_offset] = decoded_word

                            ref_sentence = " ".join(ref_parts)
                            dec_sentence = " ".join(dec_parts)
                            ref_score = self._pcd_transcriber._ctc_score(
                                log_probs, encoded_len, ref_sentence
                            )
                            dec_score = self._pcd_transcriber._ctc_score(
                                log_probs, encoded_len, dec_sentence
                            )
                            _tashkeel_thresh = getattr(
                                self.config, "tashkeel_threshold", 2.0
                            )
                            # Single-position errors require a higher
                            # threshold (segment-level proactive scoring
                            # handles these with better discrimination).
                            if len(tashkeel_errs) == 1:
                                _single_thresh = getattr(
                                    self.config,
                                    "single_pos_tashkeel_threshold",
                                    10.0,
                                )
                                _tashkeel_thresh = max(
                                    _tashkeel_thresh, _single_thresh
                                )
                            if dec_score > ref_score + _tashkeel_thresh:
                                all_errors = tashkeel_errs

                        if all_errors:
                            diff = WordDiff(
                                kind=DiffKind.WRONG_TASHKEEL,
                                ref_word=book_word.correct_diac,
                                hyp_word=decoded_word,
                                haraka_diffs=tashkeel_diffs,
                                confidence=diff.confidence,
                                detected_case=diff.detected_case,
                                expected_case=diff.expected_case,
                            )

                # ── Proactive tashkeel scoring (segment-level) ──
                # Test internal vowel alternatives using SEGMENT-level
                # CTC scoring (word's frames only).  For function words
                # (skip list), additionally verify with full-sentence
                # CTC to prevent false positives from CTC noise on
                # short/common words.
                if (
                    diff.kind in (DiffKind.CORRECT, DiffKind.PAUSAL_OK)
                    and wb is not None
                    and wb.score > -6.0
                ):
                    ref_norm_p = normalize_arabic(book_word.correct_diac)
                    tash_alts = _generate_tashkeel_alternatives(ref_norm_p)
                    if tash_alts:
                        ref_seg = self._pcd_transcriber._ctc_score_segment(
                            log_probs, sf, ef, ref_norm_p
                        )
                        _seg_thresh = getattr(
                            self.config,
                            "proactive_tashkeel_threshold", 2.0
                        )
                        best_alt = None
                        best_gap = 0.0
                        for alt_word, bi, orig_v, new_v in tash_alts:
                            alt_seg = (
                                self._pcd_transcriber._ctc_score_segment(
                                    log_probs, sf, ef, alt_word
                                )
                            )
                            gap = alt_seg - ref_seg
                            if gap > best_gap:
                                best_gap = gap
                                best_alt = (alt_word, bi, orig_v, new_v)

                        # Low-alignment words need a higher bar
                        # to avoid FPs from noisy frame boundaries.
                        _eff_thresh = (
                            _seg_thresh
                            if wb.score > -4.0
                            else max(_seg_thresh, 3.0)
                        )

                        # Decode-assisted: if the decoded form
                        # independently has the SAME vowel change
                        # as the best alt, lower the threshold.
                        if (
                            best_alt
                            and best_gap > 1.0
                            and best_gap <= _eff_thresh
                        ):
                            _raw = (
                                self._pcd_transcriber
                                .decode_word_segment(
                                    log_probs, sf, ef
                                )
                            )
                            _dec = normalize_arabic(
                                _clean_diacritics(_raw)
                            ) if _raw else ""
                            _dec_base = strip_harakat(_dec)
                            _ref_base = strip_harakat(ref_norm_p)
                            if (
                                _dec
                                and _dec_base == _ref_base
                            ):
                                # Check if decoded form has the
                                # same vowel as the alternative
                                # at the changed position.
                                _alt_w = best_alt[0]
                                _alt_diffs = compare_harakat(
                                    ref_norm_p, _alt_w
                                )
                                _dec_diffs = compare_harakat(
                                    ref_norm_p, _dec
                                )
                                _dec_positions = {
                                    hd.position for hd in _dec_diffs
                                }
                                _alt_positions = {
                                    hd.position for hd in _alt_diffs
                                }
                                if _alt_positions & _dec_positions:
                                    _eff_thresh = 1.0

                        if best_alt and best_gap > _eff_thresh:
                                alt_w, bi, orig_v, new_v = best_alt
                                _p_diffs = compare_harakat(
                                    ref_norm_p, alt_w
                                )
                                diff = WordDiff(
                                    kind=DiffKind.WRONG_TASHKEEL,
                                    ref_word=book_word.correct_diac,
                                    hyp_word=alt_w,
                                    haraka_diffs=_p_diffs,
                                    confidence=Confidence.HIGH
                                    if best_gap > 5.0
                                    else Confidence.MEDIUM,
                                )

            matched_indices.append(book_word.index)

            haraka_diffs_json = []
            for hd in diff.haraka_diffs:
                haraka_diffs_json.append({
                    "letter": hd.letter,
                    "position": hd.position,
                    "expected": format_haraka_list(hd.expected),
                    "got": format_haraka_list(hd.got),
                    "is_irab": hd.is_irab,
                })

            scored_words.append({
                "index": book_word.index,
                "kind": diff.kind.value,
                "ref_word": diff.ref_word,
                "hyp_word": diff.hyp_word,
                "haraka_diffs": haraka_diffs_json,
                "confidence": diff.confidence.value
                if isinstance(diff.confidence, Confidence)
                else "high",
                "detected_case": diff.detected_case,
                "expected_case": diff.expected_case,
            })

        return {
            "transcript": pcd_normalized,
            "matched_indices": matched_indices,
            "scored_words": scored_words,
        }

    def reset(self):
        """Reset tracker to beginning of book."""
        self.tracker.reset()
