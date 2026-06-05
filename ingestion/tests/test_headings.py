"""Tests for heading-range detection.

`heading_ranges` reports each heading block's plain-text range, in the same
offset space as `assemble`. The flow pipeline emits these as standoff
`heading` annotations so the reader splits heading blocks by offset (without
modifying the AI-tagged document).
"""
from ingestion.assemble import heading_ranges
from ingestion.models import Block, BookMetadata, Page, ParseResult, Token

_META = BookMetadata(openiti_id="x.Y", author_openiti_id="x", title_ar="ت")


def _block(key, type_, words):
    return Block(key=key, type=type_,
                 tokens=[Token(id=f"{key}_w{i}", text=w) for i, w in enumerate(words)])


def test_heading_ranges_marks_each_heading_block():
    page = Page(page_number=1, volume=1, content_blocks=[
        _block("b0", "heading", ["الحديث", "الثاني"]),     # "الحديث الثاني" -> [0, 13)
        _block("b1", "prose", ["عن", "عمر"]),
    ])
    result = ParseResult(pages=[page], metadata=_META)
    assert heading_ranges(result) == [(0, len("الحديث الثاني"))]


def test_heading_ranges_offsets_span_pages():
    p1 = Page(page_number=1, volume=1, content_blocks=[_block("b0", "prose", ["مقدمة"])])
    p2 = Page(page_number=2, volume=1, content_blocks=[
        _block("b0", "heading", ["باب", "الإيمان"]),
        _block("b1", "prose", ["نص"]),
    ])
    result = ParseResult(pages=[p1, p2], metadata=_META)
    # page 2 starts after "مقدمة" + the page separator space
    start = len("مقدمة") + 1
    assert heading_ranges(result) == [(start, start + len("باب الإيمان"))]


def test_heading_ranges_empty_without_headings():
    page = Page(page_number=1, volume=1, content_blocks=[_block("b0", "prose", ["نص", "بلا", "عنوان"])])
    result = ParseResult(pages=[page], metadata=_META)
    assert heading_ranges(result) == []
