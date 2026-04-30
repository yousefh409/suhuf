from __future__ import annotations
import hashlib
import unicodedata
from pydantic import BaseModel, computed_field


class Token(BaseModel):
    id: str          # "p42_b1_w0"
    text: str        # "حَدَّثَنَا"
    text_raw: str | None = None  # original pre-tashkeel form, set only when diacritization changed text


class Block(BaseModel):
    key: str         # "b0", "b1", ...
    type: str        # prose | hadith | isnad | matn | poetry | biography | heading
    tokens: list[Token] = []
    hemistichs: list[list[list[Token]]] = []
    metadata: dict | None = None


class Page(BaseModel):
    page_number: int
    volume: int = 1
    content_blocks: list[Block] = []

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
