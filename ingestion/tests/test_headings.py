"""Tests for deterministic heading tagging.

`heading_ranges` reports each heading block's plain-text range; `tag_headings`
wraps those ranges in <heading> tags in the continuous tagged document without
changing the plain text.
"""
from ingestion.assemble import heading_ranges
from ingestion.headings import tag_headings
from ingestion.tags import compile_tagged
from ingestion.models import Block, BookMetadata, Page, ParseResult, Token

_META = BookMetadata(openiti_id="x.Y", author_openiti_id="x", title_ar="ت")


def _block(key, type_, words):
    return Block(key=key, type=type_,
                 tokens=[Token(id=f"{key}_w{i}", text=w) for i, w in enumerate(words)])


def test_heading_ranges_marks_each_heading_block():
    page = Page(page_number=1, volume=1, content_blocks=[
        _block("b0", "heading", ["الحديث", "الثاني"]),     # "الحديث الثاني" -> [0,13)
        _block("b1", "prose", ["عن", "عمر"]),
    ])
    result = ParseResult(pages=[page], metadata=_META)
    ranges = heading_ranges(result)
    assert ranges == [(0, len("الحديث الثاني"))]


def test_tag_headings_wraps_range_plain_text_unchanged():
    # plain text: "الحديث الثاني عن عمر"  (heading is the first 13 chars)
    tagged = "الحديث الثاني <hadith id=\"h2\"><isnad>عن عمر</isnad></hadith>"
    plain_before = compile_tagged(tagged)[0]
    out = tag_headings(tagged, [(0, 13)])
    assert out.startswith("<heading>الحديث الثاني</heading>")
    # plain text is unchanged; a heading span now covers the title
    text, spans, _ = compile_tagged(out)
    assert text == plain_before
    heading = [s for s in spans if s.label == "heading"]
    assert len(heading) == 1
    assert text[heading[0].start:heading[0].end] == "الحديث الثاني"


def test_tag_headings_noop_without_ranges():
    tagged = "<hadith id=\"h1\"><matn>متن</matn></hadith>"
    assert tag_headings(tagged, []) == tagged


def test_tag_headings_close_before_following_tag():
    # heading ends exactly where the <hadith> tag begins
    tagged = "باب <hadith id=\"h1\"><matn>متن</matn></hadith>"
    out = tag_headings(tagged, [(0, len("باب"))])
    assert "<heading>باب</heading>" in out
    # still compiles and the matn is intact
    text, spans, _ = compile_tagged(out)
    assert text == "باب متن"
    assert any(s.label == "matn" for s in spans)
    assert any(s.label == "heading" for s in spans)
