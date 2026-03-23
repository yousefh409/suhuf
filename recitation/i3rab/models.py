"""Data types for i3rab."""

from dataclasses import dataclass, field
from enum import Enum


# Arabic harakat (diacritical marks) codepoints
HARAKAT = set(chr(c) for c in range(0x064B, 0x0653))
HARAKAT.add("\u0670")  # superscript alef

HARAKA_NAMES = {
    "\u064B": "fathatan",
    "\u064C": "dammatan",
    "\u064D": "kasratan",
    "\u064E": "fatha",
    "\u064F": "damma",
    "\u0650": "kasra",
    "\u0651": "shadda",
    "\u0652": "sukun",
    "\u0670": "superscript alef",
}

# Case ending markers
CASE_HARAKAT = {
    "nom": "\u064F",   # damma  ُ
    "acc": "\u064E",   # fatha  َ
    "gen": "\u0650",   # kasra  ِ
    "nom_indef": "\u064C",  # dammatan  ٌ
    "acc_indef": "\u064B",  # fathatan  ً
    "gen_indef": "\u064D",  # kasratan  ٍ
    "jussive": "\u0652",    # sukun  ْ
}


class DiffKind(Enum):
    CORRECT = "correct"
    WRONG_TASHKEEL = "tashkeel"
    WRONG_IRAB = "irab"
    WRONG_WORD = "wrong"
    MISSING = "missing"
    EXTRA = "extra"
    PAUSAL_OK = "pausal_ok"


class Confidence(Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass
class HarakaDiff:
    letter: str
    position: int
    expected: list[str]
    got: list[str]
    is_irab: bool = False  # True if this is the final case-ending position


@dataclass
class WordHypothesis:
    """A possible diacritized form of a word."""
    diacritized: str
    case: str  # "nom", "acc", "gen", "pausal", "original", etc.
    is_correct: bool
    is_pausal: bool = False


@dataclass
class BookWord:
    """A word in the book with all its i3rab hypotheses."""
    index: int
    base: str  # Undiacritized form
    correct_diac: str  # Reference diacritized form
    hypotheses: list[WordHypothesis]
    allows_pausal: bool = False  # True at phrase boundaries


@dataclass
class BookPhrase:
    """A phrase (sentence or clause) in the book."""
    words: list[BookWord]
    start_idx: int
    end_idx: int
    text: str  # Full diacritized phrase text


@dataclass
class ScoredWord:
    """Result of scoring a single word."""
    word: BookWord
    detected_hyp: WordHypothesis | None
    confidence: Confidence
    score_gap: float  # Gap between best and second-best hypothesis


@dataclass
class WordDiff:
    """Result of comparing one word."""
    kind: DiffKind
    ref_word: str | None
    hyp_word: str | None
    haraka_diffs: list[HarakaDiff] = field(default_factory=list)
    confidence: Confidence = Confidence.HIGH
    detected_case: str | None = None
    expected_case: str | None = None


# ── PDF Pipeline Models ─────────────────────────────────────────────────────


@dataclass
class PDFWord:
    """A word extracted from a PDF with its bounding box."""
    text: str
    page_num: int
    bbox: tuple[float, float, float, float]  # (x0, y0, x1, y1)
    line_num: int = 0
    word_idx_in_line: int = 0
    confidence: float = 1.0  # 1.0 for digital, OCR score for scanned


@dataclass
class PDFPage:
    """A page from a PDF with extracted words."""
    page_num: int
    width: float
    height: float
    words: list[PDFWord] = field(default_factory=list)
    is_scanned: bool = False


@dataclass
class PDFDocument:
    """A complete PDF with all extracted text and positions."""
    pages: list[PDFPage] = field(default_factory=list)
    title: str = ""
    full_text: str = ""

    @property
    def total_words(self) -> int:
        return sum(len(p.words) for p in self.pages)


@dataclass
class WordI3rab:
    """Full i3rab analysis for a single word."""
    word_index: int
    word_base: str
    word_diacritized: str
    pos: str  # Part of speech
    syntactic_role: str  # Subject, object, etc.
    case: str  # nom, acc, gen, jussive, etc.
    case_reason: str  # Arabic explanation
    i3rab_full: str  # Full i3rab statement in Arabic
    translation_word: str  # Dictionary translation
    translation_contextual: str  # Translation in context
    confidence: str = "high"  # high, medium, low
    sources: dict = field(default_factory=dict)  # {"catt": "nom", "llm1": "nom", ...}


@dataclass
class SentenceAnalysis:
    """I3rab analysis for a complete sentence."""
    sentence_text: str
    sentence_index: int
    words: list[WordI3rab] = field(default_factory=list)


@dataclass
class DocumentAnalysis:
    """Full analysis of a PDF document."""
    document_id: str = ""
    title: str = ""
    sentences: list[SentenceAnalysis] = field(default_factory=list)
    total_words: int = 0
    analyzed_words: int = 0
