# i3rab: Implementation Plan

## Architecture: Hybrid Position Tracking + Forced Alignment Hypothesis Testing

The core insight: since the user reads **known text**, we don't need open-ended diacritized ASR (which doesn't work well for MSA anyway). Instead, we:
1. Track WHERE in the book the user is (easy, any ASR works)
2. Test WHICH diacritization matches their audio per word (forced alignment against known hypotheses)

This avoids the auto-correction problem of seq2seq models and directly answers "what did the user pronounce?"

```
┌─────────────────── PRE-COMPUTATION (when book is loaded) ──────────────────┐
│                                                                             │
│  Book text ──→ CATT diacritizer ──→ fully diacritized reference            │
│                     │                                                       │
│                     ▼                                                       │
│  For each word: CAMeL Tools ──→ all valid i3rab forms (raf3/nasb/jarr)     │
│                     │                                                       │
│                     ▼                                                       │
│  For each form: Phonemizer ──→ phoneme sequence (with short vowels)        │
│                     │                                                       │
│                     ▼                                                       │
│  Store: { word_idx → { "correct": phonemes, "alternatives": [phonemes] } } │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────── RUNTIME (user reads aloud) ─────────────────────────────┐
│                                                                             │
│  Mic audio ──→ VAD ──→ phrase-sized chunks (~3-8s)                         │
│                              │                                              │
│                    ┌─────────┴──────────┐                                   │
│                    ▼                    ▼                                    │
│           [Position Tracker]    [Diacritics Scorer]                         │
│           NeMo PC / Whisper     CTC forced alignment                       │
│           undiacritized ASR     wav2vec2-xlsr-arabic                        │
│                    │                    │                                    │
│                    ▼                    ▼                                    │
│           Fuzzy match to book   Per-word: score audio                      │
│           → word positions      against N hypotheses                        │
│                    │                    │                                    │
│                    └────────┬───────────┘                                   │
│                             ▼                                               │
│                    Merge: for each word at position X,                      │
│                    which hypothesis won?                                    │
│                             │                                               │
│                             ▼                                               │
│                    Compare to correct diacritization                        │
│                    → flag errors above confidence threshold                 │
│                             │                                               │
│                             ▼                                               │
│                    Update UI (reuse existing diff display)                  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Latency Budget (M4 Pro, per phrase)

| Stage | Time | Notes |
|-------|------|-------|
| VAD + buffering | ~0ms | Streaming, no delay |
| ASR position tracking | ~50-100ms | NeMo CTC at 1000x+ RTF |
| Position fuzzy match | ~1ms | String matching |
| CTC forced alignment | ~150-200ms | wav2vec2 on 5s chunk |
| Hypothesis scoring | ~20ms/word | N=4 hypotheses per word |
| UI update | ~10ms | WebSocket push |
| **Total** | **~300-500ms** | **Well within real-time** |

---

## Phase 0: Project Restructure

Refactor from single-file to a clean module structure. Keep existing UI intact.

```
i3rab/
├── server.py                    # FastAPI app (keep, modify routes)
├── static/
│   └── index.html               # Web UI (keep, add book reader mode)
├── i3rab/
│   ├── __init__.py
│   ├── models.py                # Data types (DiffKind, WordDiff, etc.)
│   ├── arabic.py                # Arabic text utils (harakat, normalization)
│   ├── book.py                  # Book loading + pre-computation pipeline
│   ├── phonemizer.py            # Arabic text → phoneme sequences
│   ├── tracker.py               # Position tracking (ASR + fuzzy match)
│   ├── scorer.py                # Diacritics scorer (forced alignment + hypothesis)
│   ├── pipeline.py              # Orchestrator: ties tracker + scorer together
│   └── config.py                # Settings, model paths, thresholds
├── books/                       # Book text files (diacritized or raw)
├── requirements.txt
└── main.py                      # CLI entry point
```

### Dependencies to add:
```
camel-tools              # Morphological analysis, i3rab form generation
catt-tashkeel            # SOTA text diacritizer (if book isn't pre-diacritized)
ctc-forced-aligner       # CTC-based forced alignment (pip install)
torchaudio               # Alternative forced alignment API
silero-vad               # Voice activity detection for phrase segmentation
webrtcvad                # Lightweight alternative VAD
websockets               # Real-time UI updates
```

### Models to download:
```python
# Position tracking (pick one):
"tarteel-ai/whisper-base-ar-quran"              # Current, keep as option
"nvidia/stt_ar_fastconformer_hybrid_large_pc_v1.0"  # Faster, more accurate MSA

# Forced alignment:
"jonatasgrosman/wav2vec2-large-xlsr-53-arabic"  # Best Arabic wav2vec2 for alignment
# OR
"MahmoudAshraf/mms-300m-1130-forced-aligner"   # MMS model, used by ctc-forced-aligner

# Text diacritization (for non-diacritized books):
CATT (pip install catt-tashkeel)                 # SOTA, outperforms GPT-4
```

---

## Phase 1: Book Pre-Computation Pipeline

**Goal:** Load a book, diacritize it if needed, generate all i3rab hypotheses per word.

### `i3rab/book.py`

```python
@dataclass
class WordHypothesis:
    diacritized: str          # e.g. "الكِتَابُ"
    case: str                 # "nom" / "acc" / "gen" / "jussive" / "pausal"
    phonemes: list[str]       # ["ʔal", "k", "i", "t", "aː", "b", "u"]
    is_correct: bool          # Whether this is the reference diacritization

@dataclass
class BookWord:
    index: int
    base: str                 # Undiacritized: "الكتاب"
    correct_diac: str         # Reference: "الكِتَابَ"
    hypotheses: list[WordHypothesis]  # All valid diacritizations
    allows_pausal: bool       # True if at phrase boundary (waqf OK)

@dataclass
class BookPhrase:
    words: list[BookWord]
    start_idx: int
    end_idx: int
    text: str                 # Full phrase text for display

class Book:
    phrases: list[BookPhrase]
    words: list[BookWord]     # Flat list, all words in order

    @classmethod
    def from_text(cls, text: str, diacritized: bool = True) -> "Book":
        """Load book from text. If not diacritized, run CATT first."""
        ...

    @classmethod
    def from_file(cls, path: str) -> "Book":
        """Load from .txt file. Auto-detect if diacritized."""
        ...
```

### Pre-computation steps:

**Step 1 — Diacritize (if needed):**
```python
from catt_tashkeel import CATTEncoderDecoder
catt = CATTEncoderDecoder()
diacritized = catt.do_tashkeel_batch(sentences)
```
CATT achieves ~8.6% DER with case endings — good enough as a starting reference.
For important books, allow manual diacritized text input (100% accuracy).

**Step 2 — Generate i3rab hypotheses per word:**
```python
from camel_tools.morphology.database import MorphologyDB
from camel_tools.morphology.analyzer import Analyzer

db = MorphologyDB.builtin_db()
analyzer = Analyzer(db)

def get_irab_hypotheses(word: str) -> list[WordHypothesis]:
    analyses = analyzer.analyze(strip_harakat(word))
    hypotheses = []
    seen = set()
    for a in analyses:
        diac = a['diac']
        case = a.get('cas', '')  # nom, acc, gen
        if diac not in seen:
            seen.add(diac)
            phonemes = arabic_to_phonemes(diac)
            hypotheses.append(WordHypothesis(
                diacritized=diac,
                case=case,
                phonemes=phonemes,
                is_correct=(diac == word)
            ))
    # Always add pausal form (drop final vowel)
    pausal = make_pausal(word)
    if pausal not in seen:
        hypotheses.append(WordHypothesis(
            diacritized=pausal, case="pausal",
            phonemes=arabic_to_phonemes(pausal),
            is_correct=False  # pausal is "acceptable", not "correct"
        ))
    return hypotheses
```

**Step 3 — Phonemize each hypothesis:**
```python
# Simple rule-based Arabic phonemizer (sufficient for hypothesis testing):
PHONEME_MAP = {
    'ب': 'b', 'ت': 't', 'ث': 'θ', 'ج': 'dʒ', 'ح': 'ħ', 'خ': 'x',
    'د': 'd', 'ذ': 'ð', 'ر': 'r', 'ز': 'z', 'س': 's', 'ش': 'ʃ',
    'ص': 'sˤ', 'ض': 'dˤ', 'ط': 'tˤ', 'ظ': 'ðˤ', 'ع': 'ʕ', 'غ': 'ɣ',
    'ف': 'f', 'ق': 'q', 'ك': 'k', 'ل': 'l', 'م': 'm', 'ن': 'n',
    'ه': 'h', 'و': 'w', 'ي': 'j', 'ء': 'ʔ', 'ا': 'aː', 'ة': 'a',
    '\u064e': 'a',   # fatha
    '\u064f': 'u',   # damma
    '\u0650': 'i',   # kasra
    '\u064b': 'an',  # fathatan
    '\u064c': 'un',  # dammatan
    '\u064d': 'in',  # kasratan
    '\u0652': '',     # sukun (no vowel)
    '\u0651': 'ː',   # shadda (gemination)
}
```
This maps diacritics directly to the phonemes we care about — short vowels a/u/i are exactly the i3rab markers. The forced aligner will score whether the user produced /a/, /u/, /i/, or nothing at each word ending.

**Step 4 — Mark phrase boundaries:**
Detect sentence boundaries (periods, commas) and mark which words allow pausal forms. Last word before any pause = pausal is acceptable (not an error).

---

## Phase 2: Position Tracker

**Goal:** Given a phrase of audio, determine which words in the book the user just read.

### `i3rab/tracker.py`

```python
class PositionTracker:
    def __init__(self, book: Book, model_name: str):
        self.book = book
        self.asr_model = load_asr_model(model_name)
        self.current_position = 0  # Word index in book

    def locate(self, audio: np.ndarray) -> tuple[int, int]:
        """Return (start_word_idx, end_word_idx) in the book."""
        # 1. Transcribe (undiacritized)
        text = self.asr_model.transcribe(audio)
        words = strip_all_harakat(text).split()

        # 2. Fuzzy match against book text starting from current position
        # Use a sliding window around current_position for efficiency
        window = self.book.words[self.current_position:self.current_position + 50]
        window_bases = [w.base for w in window]

        # SequenceMatcher to find best alignment
        best_start = find_best_alignment(words, window_bases)

        start_idx = self.current_position + best_start
        end_idx = start_idx + len(words)
        self.current_position = end_idx  # Advance cursor

        return start_idx, end_idx
```

**ASR model choice:**
- **Tarteel Whisper** (current): Fine for now, works on M4 Pro, ~400ms per 5s chunk
- **NeMo PC model**: Faster (1000x RTF), more accurate on MSA, but requires NeMo install
- Keep both as options in config. Start with Tarteel Whisper since it's already working.

**Fuzzy matching strategy:**
- Only search a window of ~50 words ahead of current position (user reads sequentially)
- Use `difflib.SequenceMatcher` on base (undiacritized) words
- Handle skipped words, repeated words, false starts
- Advance the cursor monotonically (user reads forward)

---

## Phase 3: Diacritics Scorer (Core Innovation)

**Goal:** Given an audio segment and the known word + its hypotheses, determine which diacritization the user actually produced.

### `i3rab/scorer.py`

```python
class DiacriticsScorer:
    def __init__(self, model_name: str = "jonatasgrosman/wav2vec2-large-xlsr-53-arabic"):
        self.model, self.processor = load_wav2vec2(model_name)

    def score_word(
        self,
        audio_segment: np.ndarray,
        word: BookWord
    ) -> ScoredResult:
        """Score which diacritization hypothesis best matches the audio."""

        # Get CTC log-probabilities from wav2vec2
        emissions = self.get_emissions(audio_segment)

        best_score = float('-inf')
        best_hypothesis = None

        for hyp in word.hypotheses:
            # Score this phoneme sequence against the emissions
            score = self.align_and_score(emissions, hyp.phonemes)

            if score > best_score:
                best_score = score
                best_hypothesis = hyp

        return ScoredResult(
            word=word,
            detected=best_hypothesis,
            confidence=compute_confidence(best_score, word.hypotheses),
            is_correct=best_hypothesis.is_correct,
            is_pausal=(best_hypothesis.case == "pausal" and word.allows_pausal)
        )

    def get_emissions(self, audio: np.ndarray) -> torch.Tensor:
        """Run wav2vec2 forward pass → CTC log-probabilities."""
        inputs = self.processor(audio, sampling_rate=16000, return_tensors="pt")
        with torch.no_grad():
            logits = self.model(**inputs).logits  # (1, T, vocab_size)
        return torch.log_softmax(logits, dim=-1).squeeze(0)

    def align_and_score(
        self,
        emissions: torch.Tensor,
        phonemes: list[str]
    ) -> float:
        """CTC forced alignment score for a phoneme sequence."""
        # Convert phonemes to token IDs
        targets = phonemes_to_token_ids(phonemes, self.processor)

        # Use torchaudio forced alignment
        alignment, score = torchaudio.functional.forced_align(
            emissions.unsqueeze(0), targets
        )
        return score
```

**Key technical detail — what we're actually comparing:**

For the word الكتاب at the end of a sentence, the hypotheses differ only in the final vowel:
```
الكتابُ → [..., b, u]     score: -12.3
الكتابَ → [..., b, a]     score: -8.7   ← winner (user said fatha)
الكتابِ → [..., b, i]     score: -15.1
الكتاب  → [..., b]        score: -10.2  (pausal, no final vowel)
```

The forced aligner scores the entire sequence but the discriminative signal comes from the final vowel phoneme. A score difference of >3 between the top two hypotheses = high confidence.

### Alternative scoring approach: frame-level posterior comparison

Instead of full forced alignment, a simpler approach that may be equally effective:

```python
def score_final_vowel(self, audio_segment: np.ndarray, word: BookWord) -> str:
    """Just check the last ~100ms of the word segment for which vowel is present."""
    emissions = self.get_emissions(audio_segment)

    # Look at final ~10 frames (100ms at 10ms frame rate)
    final_frames = emissions[-10:]

    # Get average log-prob for each vowel token
    vowel_scores = {}
    for vowel_name, token_id in [("fatha", A_ID), ("damma", U_ID), ("kasra", I_ID)]:
        vowel_scores[vowel_name] = final_frames[:, token_id].mean().item()

    # Also check for "no vowel" (blank/silence dominates)
    blank_score = final_frames[:, BLANK_ID].mean().item()

    if blank_score > max(vowel_scores.values()):
        return "pausal"  # No final vowel detected
    return max(vowel_scores, key=vowel_scores.get)
```

This simpler approach focuses on the exact signal we care about: which vowel (if any) appears at the word boundary.

**Confidence thresholds (tunable):**
```python
HIGH_CONFIDENCE = 3.0    # Score gap > 3 → definitely this diacritization
MEDIUM_CONFIDENCE = 1.5  # Score gap 1.5-3 → probably this one
LOW_CONFIDENCE = 0       # Score gap < 1.5 → uncertain, don't flag
```

Only flag errors at HIGH_CONFIDENCE initially. Tuning these thresholds trades off between catching real errors vs. false alarms.

---

## Phase 4: Pipeline Orchestrator

**Goal:** Wire everything together into a real-time pipeline.

### `i3rab/pipeline.py`

```python
class I3rabPipeline:
    def __init__(self, book: Book, config: Config):
        self.book = book
        self.tracker = PositionTracker(book, config.asr_model)
        self.scorer = DiacriticsScorer(config.alignment_model)
        self.vad = load_vad()  # Silero VAD

    def process_phrase(self, audio: np.ndarray) -> list[WordResult]:
        """Process one phrase of audio. Returns per-word results."""
        # 1. Find position in book
        start_idx, end_idx = self.tracker.locate(audio)

        # 2. Segment audio into per-word chunks using forced alignment
        word_segments = self.segment_words(audio, start_idx, end_idx)

        # 3. Score each word's diacritics
        results = []
        for word, audio_seg in word_segments:
            result = self.scorer.score_word(audio_seg, word)
            results.append(result)

        return results

    def segment_words(self, audio, start_idx, end_idx):
        """Use CTC alignment to split audio into word-sized chunks."""
        words = self.book.words[start_idx:end_idx]
        # Get word-level timestamps via forced alignment to undiacritized text
        timestamps = forced_align_words(audio, [w.base for w in words])
        segments = []
        for word, (t_start, t_end) in zip(words, timestamps):
            seg = audio[int(t_start * 16000):int(t_end * 16000)]
            segments.append((word, seg))
        return segments
```

### Streaming wrapper for real-time:

```python
class StreamingPipeline:
    def __init__(self, pipeline: I3rabPipeline):
        self.pipeline = pipeline
        self.audio_buffer = []
        self.vad = load_silero_vad()

    async def on_audio_chunk(self, chunk: np.ndarray):
        """Called every ~100ms with new audio data."""
        self.audio_buffer.append(chunk)

        # Check VAD for phrase boundary (speech → silence transition)
        if self.detect_phrase_end(chunk):
            phrase_audio = np.concatenate(self.audio_buffer)
            self.audio_buffer = []

            # Process phrase (runs in ~300-500ms)
            results = self.pipeline.process_phrase(phrase_audio)

            # Push to UI via WebSocket
            await self.send_results(results)
```

---

## Phase 5: Server + UI Updates

### Server changes (`server.py`):

**New endpoints:**
```
POST /api/book/load          # Upload/paste book text, triggers pre-computation
GET  /api/book/phrases       # Get paginated book phrases for display
WS   /ws/session             # WebSocket for real-time audio streaming + results
POST /api/phrase/evaluate     # Non-streaming: evaluate one phrase recording
```

**WebSocket protocol:**
```
Client → Server: binary audio chunks (16kHz PCM, every 100ms)
Server → Client: JSON results per phrase:
{
    "type": "phrase_result",
    "phrase_idx": 3,
    "words": [
        {
            "idx": 12,
            "ref": "الكِتَابَ",
            "detected": "الكِتَابُ",
            "correct": false,
            "error": "You said damma (nominative), should be fatha (accusative)",
            "confidence": "high",
            "kind": "tashkeel"
        },
        ...
    ],
    "score": {"correct": 4, "total": 6}
}
```

### UI changes (`static/index.html`):

Extend the existing beautiful UI with:
1. **Book reader view** — display the full text with phrase markers, highlight current phrase
2. **Real-time word highlighting** — as user reads, highlight words being processed
3. **Inline error markers** — color-code words with i3rab errors directly in the text
4. **Keep existing comparison cards** — show them below the text for detailed feedback
5. **Session progress** — track accuracy over the full reading session

---

## Phase 6: Accuracy Improvements (Iterate)

### 6a: Fine-tune wav2vec2 for Arabic vowel discrimination

The Horouf paper (2025) showed that fine-tuning wav2vec2-xlsr on diacritized Arabic phonemes improved accuracy from 37% → 65% (isolated letters). For our constrained hypothesis testing (4-way choice, connected speech), fine-tuning should push accuracy higher.

**Data:** EveryAyah (~830h with diacritized transcripts) + ClArTTS (12h)
**Method:** Fine-tune wav2vec2-xlsr-53-arabic with CTC loss on phoneme-level labels
**Compute:** Single GPU, ~1 day for the EveryAyah dataset

### 6b: Contextual re-ranking with lightweight grammar model

After the acoustic scorer picks a hypothesis, re-rank using grammatical context:
```python
# If acoustic score is ambiguous (MEDIUM_CONFIDENCE):
# Use a simple rule-based Arabic grammar checker or BERT-based
# syntactic model to re-rank hypotheses

# Example: if previous word is a preposition (في, من, على, etc.)
# → next noun MUST be genitive (kasra/jarr)
# This constraint can override ambiguous acoustic scores
```

CAMeL Tools provides morphological disambiguation that can help:
```python
from camel_tools.disambig.mle import MLEDisambiguator
disambiguator = MLEDisambiguator.pretrained()
disambiguated = disambiguator.disambiguate(sentence_words)
# Returns most likely POS + case for each word
```

### 6c: Pausal form detection

When the user pauses (detected by VAD), the preceding word's case ending is dropped. This is correct Arabic grammar (waqf). The system must:
1. Detect pauses via Silero VAD (>300ms silence)
2. Mark the preceding word as "pausal context"
3. Accept both the correct diacritization AND the pausal form as correct
4. Only flag as error if user produced a WRONG vowel (not just missing vowel)

### 6d: User-adaptive calibration

After 10-20 phrases, calibrate confidence thresholds per user:
- Some speakers produce clearer vowels → lower thresholds
- Some speakers naturally reduce final vowels → raise thresholds
- Track false positive rate (user says "that was correct!" → recalibrate)

---

## Implementation Order

| Step | Description | Effort | Dependencies |
|------|------------|--------|-------------|
| **0** | Restructure into `i3rab/` package, extract existing code | 1 day | None |
| **1a** | Book loader + CATT diacritizer integration | 1 day | `catt-tashkeel` |
| **1b** | CAMeL Tools i3rab hypothesis generation | 2 days | `camel-tools` |
| **1c** | Arabic phonemizer (rule-based) | 1 day | None |
| **2** | Position tracker (reuse existing ASR + add fuzzy matching) | 1 day | Step 0 |
| **3a** | CTC forced alignment integration | 2 days | `ctc-forced-aligner` or `torchaudio` |
| **3b** | Hypothesis scorer (score word audio against N phoneme seqs) | 3 days | Steps 1c, 3a |
| **3c** | Confidence thresholds + pausal form handling | 1 day | Step 3b |
| **4** | Pipeline orchestrator + phrase segmentation | 2 days | Steps 2, 3b |
| **5a** | WebSocket streaming endpoint | 1 day | Step 4 |
| **5b** | Book reader UI + real-time highlighting | 2 days | Step 5a |
| **6a** | Fine-tune wav2vec2 on EveryAyah for better vowel discrimination | 3 days | GPU access |
| **6b** | Grammar-based re-ranking for ambiguous cases | 2 days | Step 3b |
| **6c** | VAD-based pausal detection | 1 day | `silero-vad` |
| **6d** | User-adaptive calibration | 2 days | Step 4 running |

**MVP (Steps 0-4):** ~2 weeks → working phrase-by-phrase evaluation
**Full real-time (Steps 5a-5b):** +1 week → streaming book reading with live feedback
**High accuracy (Steps 6a-6d):** +2 weeks → tuned, production-quality system

---

## Expected Accuracy at Each Stage

| Stage | Approach | i3rab Accuracy (est.) | Notes |
|-------|---------|----------------------|-------|
| Current | Tarteel Whisper + diff | ~40-50% | Whisper auto-corrects errors, barely diacritizes MSA |
| After Phase 3 (MVP) | Forced alignment + hypothesis testing | ~75-85% | Known text advantage, CTC scoring |
| After Phase 6a | + Fine-tuned wav2vec2 | ~80-88% | Better vowel discrimination |
| After Phase 6b | + Grammar re-ranking | ~83-90% | Contextual disambiguation |
| After Phase 6c | + Pausal handling | ~85-92% | Eliminates false positives at pauses |
| After Phase 6d | + User calibration | ~87-93% | Adapted to individual speaker |

The **known-text constraint** is the biggest accuracy lever — it turns open-ended 112-class phoneme recognition into a constrained 3-4 way choice per word, which is dramatically easier.

---

## Risk Mitigations

**Risk: wav2vec2 Arabic models can't distinguish short vowels reliably**
→ Mitigation: Fine-tune on EveryAyah (Phase 6a). Fallback: only flag HIGH_CONFIDENCE errors.

**Risk: Word segmentation errors (wrong word boundaries from forced alignment)**
→ Mitigation: Use phrase-level alignment first, then word-level within the phrase. The known text sequence provides strong constraints.

**Risk: camel-tools morphology doesn't cover all words in the book**
→ Mitigation: Fall back to rule-based i3rab generation (just try all 3 case endings on the last letter). Most Arabic words follow regular patterns.

**Risk: NeMo tokenizer bug (#3795) blocks fine-tuning**
→ Mitigation: We don't fine-tune NeMo at all in this plan. We use it only for undiacritized position tracking (PC model). The diacritics work is done by wav2vec2 + forced alignment.

**Risk: User reads with heavy dialect/accent**
→ Mitigation: The hypothesis testing approach is naturally robust to accent because it's comparative (which hypothesis is CLOSEST?), not absolute. Even if all scores are low, the relative ranking still works.
