"""Tests for the parse -> continuous-text assembler.

``assemble`` concatenates each page's plain text (same derivation as
``Page.content_plain``) in document order with a single space between pages, and
reports per-page start offsets plus the heading-block start offsets (the only
allowed chunk cut points). Page boundaries are NOT chunk boundaries — a page may
begin mid-hadith.
"""
from ingestion.models import Block, Token, Page, ParseResult, BookMetadata
from ingestion.assemble import assemble, numbered_units


def _toks(page, key, words):
    return [Token(id=f"p{page}_{key}_w{i}", text=w) for i, w in enumerate(words)]


def _heading(page, key, words, level=3):
    return Block(key=key, type="heading", level=level, tokens=_toks(page, key, words))


def _prose(page, key, words):
    return Block(key=key, type="prose", tokens=_toks(page, key, words))


def _fixture():
    """Two hadiths; hadith 2 straddles the page 2 -> 3 boundary."""
    meta = BookMetadata(openiti_id="t.1", title_ar="x", author_openiti_id="a")
    p1 = Page(page_number=1, content_blocks=[
        _heading(1, "b0", ["الحديث", "الأول"]),
        _prose(1, "b1", ["نص", "أول"]),
    ])
    p2 = Page(page_number=2, content_blocks=[
        _heading(2, "b0", ["الحديث", "الثاني"]),
        _prose(2, "b1", ["بداية", "المتن"]),
    ])
    p3 = Page(page_number=3, content_blocks=[
        _prose(3, "b0", ["تتمة", "المتن"]),
    ])
    return ParseResult(metadata=meta, pages=[p1, p2, p3])


def test_assemble_text_is_pages_joined_by_single_space():
    text, _, _ = assemble(_fixture())
    expected = " ".join([
        "الحديث الأول نص أول",       # page 1 content_plain
        "الحديث الثاني بداية المتن",  # page 2
        "تتمة المتن",                 # page 3
    ])
    assert text == expected


def test_assemble_page_offsets():
    text, page_offsets, _ = assemble(_fixture())
    # one entry per page: (page_number, volume, start_offset)
    assert [po[0] for po in page_offsets] == [1, 2, 3]
    assert all(po[1] == 1 for po in page_offsets)
    # page 1 starts at 0
    assert page_offsets[0][2] == 0
    # page 2 begins right after page 1's plain text + the single-space separator
    p1_plain = "الحديث الأول نص أول"
    assert page_offsets[1][2] == len(p1_plain) + 1
    assert text[page_offsets[1][2]:].startswith("الحديث الثاني")
    # page 3 begins mid-hadith-2 (right after "بداية المتن")
    assert text[page_offsets[2][2]:].startswith("تتمة المتن")


def test_assemble_boundaries_are_heading_starts_only():
    text, _, boundaries = assemble(_fixture())
    # exactly two headings -> two boundaries
    assert len(boundaries) == 2
    assert text[boundaries[0]:].startswith("الحديث الأول")
    assert text[boundaries[1]:].startswith("الحديث الثاني")
    # the page 2 -> 3 boundary (mid-hadith) is NOT a chunk boundary
    page3_start = text.index("تتمة المتن")
    assert page3_start not in boundaries


def test_assemble_page_offset_can_land_mid_unit():
    # The page-3 offset falls strictly between the two heading boundaries: it is
    # inside hadith 2, proving a page break is independent of unit boundaries.
    _, page_offsets, boundaries = assemble(_fixture())
    page3_off = page_offsets[2][2]
    assert boundaries[1] < page3_off


def test_numbered_units_records_block_numbers():
    meta = BookMetadata(openiti_id="t.1", title_ar="x", author_openiti_id="a")
    h = _heading(1, "b0", ["الحديث", "الأول"])
    numbered = Block(key="b1", type="prose", tokens=_toks(1, "b1", ["نص"]), number="1")
    page = Page(page_number=1, content_blocks=[h, numbered])
    text, _, _ = assemble(ParseResult(metadata=meta, pages=[page]))
    units = numbered_units(ParseResult(metadata=meta, pages=[page]))
    assert len(units) == 1
    off, num = units[0]
    assert num == "1"
    assert text[off:].startswith("نص")


def test_numbered_units_empty_when_no_numbers():
    assert numbered_units(_fixture()) == []
