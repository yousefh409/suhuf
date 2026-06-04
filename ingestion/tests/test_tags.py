"""Tests for the tag compiler: tagged <-> (text, spans, lines)."""
import pytest

from ingestion.tags import compile_tagged, render_tagged, TagError
from ingestion.tagged_format import Span


def _labels(spans):
    return [(s.start, s.end, s.label) for s in spans]


# ── compile: prose + inline spans ──────────────────────────────────────────

def test_compile_single_span():
    text, spans, lines = compile_tagged("<matn>سبعة</matn>")
    assert text == "سبعة"
    assert _labels(spans) == [(0, 4, "matn")]
    assert lines == []


def test_compile_plain_text_no_tags():
    text, spans, lines = compile_tagged("وعن أبي هريرة")
    assert text == "وعن أبي هريرة"
    assert spans == []
    assert lines == []


def test_compile_nested_spans():
    text, spans, lines = compile_tagged("<isnad>عن <person>أبي</person> قال</isnad>")
    assert text == "عن أبي قال"
    # isnad covers the whole 10-char string; person covers "أبي" at 3..6
    assert (0, 10, "isnad") in _labels(spans)
    assert (3, 6, "person") in _labels(spans)


def test_compile_sibling_spans_offsets():
    text, spans, lines = compile_tagged("<matn>«من»</matn> <takhrij>رواه</takhrij>")
    assert text == "«من» رواه"
    assert (0, 4, "matn") in _labels(spans)
    assert (5, 9, "takhrij") in _labels(spans)


# ── escaping ────────────────────────────────────────────────────────────────

def test_compile_unescapes_reserved():
    text, spans, lines = compile_tagged("<matn>a &lt; b &amp; c &gt; d</matn>")
    assert text == "a < b & c > d"
    assert _labels(spans) == [(0, 13, "matn")]


def test_render_escapes_reserved():
    tagged = render_tagged("a < b & c", [Span(start=0, end=9, label="matn")], [])
    assert tagged == "<matn>a &lt; b &amp; c</matn>"


# ── poetry: verse / hemistich -> lines ──────────────────────────────────────

def test_compile_poetry_to_lines():
    tagged = "<verse><hemistich>صدر</hemistich><hemistich>عجز</hemistich></verse>"
    text, spans, lines = compile_tagged(tagged)
    assert lines == [["صدر", "عجز"]]
    assert spans == []
    assert "صدر" in text and "عجز" in text


def test_compile_two_verses():
    tagged = ("<verse><hemistich>أ</hemistich><hemistich>ب</hemistich></verse>"
              "<verse><hemistich>ج</hemistich><hemistich>د</hemistich></verse>")
    _, _, lines = compile_tagged(tagged)
    assert lines == [["أ", "ب"], ["ج", "د"]]


# ── render: inverse ─────────────────────────────────────────────────────────

def test_render_single_span():
    assert render_tagged("سبعة", [Span(start=0, end=4, label="matn")], []) == "<matn>سبعة</matn>"


def test_render_poetry_from_lines():
    out = render_tagged("صدر عجز", [], [["صدر", "عجز"]])
    assert out == "<verse><hemistich>صدر</hemistich><hemistich>عجز</hemistich></verse>"


# ── round-trips ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("tagged", [
    "<matn>سبعة</matn>",
    "<isnad>عن <person>أبي</person> قال</isnad> <matn>«من»</matn> <takhrij>رواه</takhrij>",
    "<matn>a &lt; b</matn>",
    "<verse><hemistich>صدر</hemistich><hemistich>عجز</hemistich></verse>",
    "نص بدون أي وسوم",
])
def test_render_compile_roundtrip(tagged):
    text, spans, lines = compile_tagged(tagged)
    assert render_tagged(text, spans, lines) == tagged


# ── errors ──────────────────────────────────────────────────────────────────

def test_render_handles_crossing_spans():
    # Partially-overlapping spans (an entity straddling a structural boundary)
    # must still render as VALID markup — split via close-and-reopen, never
    # crossing tags. compile must accept the result and a re-render is stable.
    spans = [Span(start=0, end=6, label="isnad"), Span(start=3, end=10, label="person")]
    tagged = render_tagged("ابجد هوز حط", spans, [])
    text, sp, lines = compile_tagged(tagged)   # must not raise
    assert text == "ابجد هوز حط"
    assert render_tagged(text, sp, lines) == tagged   # stable round-trip


def test_unknown_tag_errors():
    with pytest.raises(TagError):
        compile_tagged("<foo>x</foo>")


def test_mismatched_nesting_errors():
    with pytest.raises(TagError):
        compile_tagged("<isnad><matn>x</isnad></matn>")


def test_unclosed_tag_errors():
    with pytest.raises(TagError):
        compile_tagged("<matn>x")
