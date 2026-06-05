"""The simpler tagged book format.

Canonical per-block field is `tagged` (HTML-style boundary tags). `text`,
`spans`, and `lines` are derived by `tags.compile_tagged`. Metadata (`sub`,
`ref`, `conf`) is a resolved layer on the span, never authored in the tags.

Lives alongside the legacy token/token-id-span format in `models.py` during the
migration; the pipeline is ported onto it in Phase 2 and the legacy types are
then removed. See docs/superpowers/specs/2026-06-04-simpler-book-format.md.
"""
from __future__ import annotations
from pydantic import BaseModel

from ingestion.models import BookMetadata, Chapter

# Inline tags become spans; structural tags become `lines`.
INLINE_TAGS = {
    "hadith", "heading", "isnad", "matn", "takhrij",
    "person", "place", "quran", "book_ref", "hadith_ref", "date_hijri", "footnote",
}
STRUCT_TAGS = {"verse", "hemistich"}
BLOCK_TYPES = {"prose", "heading", "poetry", "quran"}


class Span(BaseModel):
    """Inline annotation as a character range into the block's derived `text`.

    `start` inclusive, `end` exclusive. `label` is the only thing the tags
    carry; `sub`/`ref`/`conf` are filled by resolution passes.
    """
    start: int
    end: int
    label: str
    sub: str | None = None
    ref: str | None = None
    conf: float | None = None


class Block(BaseModel):
    key: str
    type: str                       # prose | heading | poetry | quran
    tagged: str                     # CANONICAL
    text: str = ""                  # derived: tags stripped
    text_raw: str | None = None     # undiacritized parallel, for the tashkeel diff
    spans: list[Span] = []          # derived: inline tag offsets + resolved metadata
    lines: list[list[str]] = []     # derived: poetry hemistich pairs
    number: str | None = None
    level: int | None = None
    parser_type: str | None = None
    flags: list[str] = []


class Footnote(BaseModel):
    marker: str
    tagged: str
    text: str = ""
    spans: list[Span] = []


class Page(BaseModel):
    page_number: int
    volume: int = 1
    blocks: list[Block] = []
    footnotes: list[Footnote] = []


class Book(BaseModel):
    metadata: BookMetadata
    pages: list[Page] = []
    chapters: list[Chapter] = []
