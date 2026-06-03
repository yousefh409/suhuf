"""Tests for the legacy token format -> tagged format aligner."""
from ingestion.models import (
    Block, Token, Span as TokenSpan, Page, ParseResult, BookMetadata, Footnote,
)
from ingestion.migrate_format import align_book


def _toks(key, words):
    return [Token(id=f"p1_{key}_w{i}", text=w) for i, w in enumerate(words)]


def _book(block):
    meta = BookMetadata(openiti_id="t.1", title_ar="x", author_openiti_id="a")
    return ParseResult(metadata=meta, pages=[Page(page_number=1, content_blocks=[block])])


def test_align_prose_spans_to_offsets():
    toks = _toks("b0", ["عن", "أبي", "قال"])
    block = Block(
        key="b0", type="prose", tokens=toks,
        spans=[
            TokenSpan(start_token_id="p1_b0_w0", end_token_id="p1_b0_w2", label="isnad", confidence=0.95),
            TokenSpan(start_token_id="p1_b0_w1", end_token_id="p1_b0_w1", label="person", sub_label="companion"),
        ],
    )
    out = align_book(_book(block))
    b = out.pages[0].blocks[0]
    assert b.type == "prose"
    assert b.text == "عن أبي قال"
    labels = {(s.start, s.end, s.label) for s in b.spans}
    assert (0, 10, "isnad") in labels          # whole string
    assert (3, 6, "person") in labels           # "أبي"
    isnad = next(s for s in b.spans if s.label == "isnad")
    assert isnad.conf == 0.95
    person = next(s for s in b.spans if s.label == "person")
    assert person.sub == "companion"
    assert "<isnad>" in b.tagged and "<person>" in b.tagged


def test_align_isnad_block_type_becomes_prose_with_span():
    # A legacy block whose TYPE is matn collapses to a prose block carrying a
    # matn span over its whole text.
    block = Block(key="b0", type="matn", tokens=_toks("b0", ["سبعة", "يظلهم"]))
    out = align_book(_book(block))
    b = out.pages[0].blocks[0]
    assert b.type == "prose"
    assert any(s.label == "matn" and s.start == 0 and s.end == len(b.text) for s in b.spans)


def test_align_poetry_to_lines():
    v = [[_toks("b0", ["صدر", "البيت"]), _toks("b0b", ["عجز", "البيت"])]]
    block = Block(key="b0", type="poetry", hemistichs=v)
    out = align_book(_book(block))
    b = out.pages[0].blocks[0]
    assert b.type == "poetry"
    assert b.lines == [["صدر البيت", "عجز البيت"]]
    assert "<verse>" in b.tagged and "<hemistich>" in b.tagged


def test_align_carries_text_raw():
    toks = [Token(id="p1_b0_w0", text="قَالَ", text_raw="قال")]
    block = Block(key="b0", type="prose", tokens=toks)
    out = align_book(_book(block))
    assert out.pages[0].blocks[0].text_raw == "قال"


def test_align_footnote():
    meta = BookMetadata(openiti_id="t.1", title_ar="x", author_openiti_id="a")
    page = Page(page_number=1, content_blocks=[], footnotes=[
        Footnote(marker="1", tokens=_toks("fn", ["أخرجه", "البخاري"]))
    ])
    out = align_book(ParseResult(metadata=meta, pages=[page]))
    fn = out.pages[0].footnotes[0]
    assert fn.marker == "1"
    assert fn.text == "أخرجه البخاري"
