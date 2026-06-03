from __future__ import annotations
import hashlib
import unicodedata
from pydantic import BaseModel, computed_field


class Token(BaseModel):
    id: str          # "p42_b1_w0"
    text: str        # "حَدَّثَنَا"
    text_raw: str | None = None  # original pre-tashkeel form, set only when diacritization changed text


class Span(BaseModel):
    """Inline annotation over a contiguous range of tokens within a block.

    Token range is inclusive on both ends. Labels come from the v2 annotation
    pass; renderer uses them to wrap matched ranges with span classes.
    """
    start_token_id: str            # first token id, e.g. "p3_b5_w2"
    end_token_id: str              # last token id (inclusive)
    label: str                     # quran | person | place | book_ref | hadith_ref | date_hijri | footnote | isnad | matn | takhrij
    sub_label: str | None = None   # e.g. companion / tabii / scholar / prophet for person
    ref: str | None = None         # e.g. sura:ayah for quran; openiti_id for book_ref; marker for footnote
    confidence: float | None = None


class Block(BaseModel):
    key: str         # "b0", "b1", ...
    type: str        # prose | heading | poetry | isnad | matn | takhrij | quran
    tokens: list[Token] = []
    hemistichs: list[list[list[Token]]] = []
    metadata: dict | None = None
    # Set by the annotation pass when the model overrides the parser's guess.
    # Preserved so downstream tooling can audit/diff annotation drift.
    parser_type: str | None = None
    spans: list[Span] = []
    flags: list[str] = []
    level: int | None = None       # heading depth 1/2/3, None for non-headings
    number: str | None = None      # printed item ordinal as string to preserve fidelity


class Footnote(BaseModel):
    marker: str
    tokens: list[Token] = []


class Page(BaseModel):
    page_number: int
    volume: int = 1
    content_blocks: list[Block] = []
    footnotes: list[Footnote] = []

    @computed_field
    @property
    def content_plain(self) -> str:
        words = []
        for block in self.content_blocks:
            if block.type == "poetry":
                for verse in block.hemistichs:
                    for hemistich in verse:
                        words.extend(t.text for t in hemistich)
            else:
                words.extend(t.text for t in block.tokens)
        return " ".join(words)

    @computed_field
    @property
    def content_hash(self) -> str:
        normalized = unicodedata.normalize("NFC", self.content_plain)
        return hashlib.sha256(normalized.encode()).hexdigest()


class Chapter(BaseModel):
    title: str
    level: int
    page_number: int
    sort_order: int
    parent_index: int | None = None
    # Index of the heading block within its page's content_blocks. Lets the
    # reader slice pages that contain multiple chapter starts (e.g. several
    # hadiths printed on one physical page).
    block_index: int | None = None


class BookMetadata(BaseModel):
    openiti_id: str
    title_ar: str
    title_lat: str | None = None
    author_openiti_id: str
    genres: list[str] = []
    word_count: int | None = None
    char_count: int | None = None
    version_status: str | None = None
    language: str = "ara"


class ParseResult(BaseModel):
    metadata: BookMetadata
    pages: list[Page] = []
    chapters: list[Chapter] = []
