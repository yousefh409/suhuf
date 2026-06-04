"""Tests for the page-slice / reconstruct core (Phase 1).

The book is one continuous tagged document; pages are where it is sliced for
storage. A tag may open on one slice and close on a later one. These tests prove
slicing is lossless (reconstruct == original), that each slice records the
open-tag stack at its start, and that a single slice can be made independently
well-formed for isolated rendering.
"""
import pytest

from ingestion.tags import compile_tagged, TagError, _TAG_SPLIT
from ingestion.page_slice import (
    OpenTag,
    PageSlice,
    slice_tagged,
    reconstruct,
    close_fragment,
)


def _plain(tagged: str) -> str:
    return compile_tagged(tagged)[0]


def _strip_tags(fragment: str) -> str:
    """Plain text of a raw slice fragment (may carry dangling open/close tags
    that don't compile on their own), per the no-entities v1 assumption."""
    return "".join(p for p in _TAG_SPLIT.split(fragment)
                   if p and not p.startswith("<"))


def _breaks_at(tagged: str, *needles: str) -> list[int]:
    """Plain-text offsets where each needle begins (interior cut points)."""
    plain = _plain(tagged)
    out = []
    for n in needles:
        i = plain.index(n)
        assert i > 0, f"break must be interior, got {i} for {n!r}"
        out.append(i)
    return out


# ── round-trip: slicing then reconstruct returns the original exactly ────────

@pytest.mark.parametrize("tagged,needles", [
    # break lands INSIDE a tag's text
    ("<matn>أبجد هوز حطي</matn>", ("هوز",)),
    # break lands BETWEEN two sibling tags
    ("<isnad>عن فلان</isnad> <matn>قال كذا</matn>", ("قال",)),
    # break lands EXACTLY on a tag boundary (start of an inner tag's text)
    ("<isnad>عن <person id=\"p1\">زيد</person></isnad>", ("زيد",)),
    # plain text, no tags
    ("ابجد هوز حطي كلمن", ("حطي",)),
    # multiple breaks, nested tags
    ("<hadith id=\"h1\"><isnad>عن زيد</isnad> <matn>قال نعم لا ربما</matn></hadith>",
     ("قال", "ربما")),
])
def test_roundtrip(tagged, needles):
    breaks = _breaks_at(tagged, *needles)
    slices = slice_tagged(tagged, breaks)
    assert len(slices) == len(breaks) + 1
    assert reconstruct(slices) == tagged


def test_duplicate_breaks_no_empty_slice():
    # Coincident break offsets must collapse to one cut, not yield an empty
    # `tagged` slice between them; round-trip must still hold.
    tagged = "<matn>أبجد هوز حطي</matn>"
    b = _breaks_at(tagged, "هوز")[0]
    slices = slice_tagged(tagged, [b, b])
    assert all(s.tagged != "" for s in slices)
    assert reconstruct(slices) == tagged


def test_first_slice_open_tags_empty():
    tagged = "<matn>أبجد هوز حطي</matn>"
    slices = slice_tagged(tagged, _breaks_at(tagged, "هوز"))
    assert slices[0].open_tags == []


# ── open_tags capture ────────────────────────────────────────────────────────

def test_open_tags_snapshot_inside_matn_inside_hadith():
    tagged = "<hadith id=\"h2\"><matn>بينما نحن جلوس قال كذا</matn></hadith>"
    # break inside the matn (which is inside the hadith)
    slices = slice_tagged(tagged, _breaks_at(tagged, "قال"))
    assert slices[1].open_tags == [OpenTag(name="hadith", id="h2"),
                                   OpenTag(name="matn", id=None)]


# ── id preservation ──────────────────────────────────────────────────────────

def test_id_preserved_across_slice_and_reconstruct():
    tagged = "<hadith id=\"h2\"><matn>كلمة أولى وكلمة ثانية</matn></hadith>"
    slices = slice_tagged(tagged, _breaks_at(tagged, "وكلمة"))
    # the open hadith id survives into the next slice's snapshot
    assert OpenTag(name="hadith", id="h2") in slices[1].open_tags
    # and the literal id="h2" survives reconstruction
    assert reconstruct(slices) == tagged
    assert 'id="h2"' in reconstruct(slices)


# ── fragment isolation: close_fragment makes one slice compilable ────────────

def test_close_fragment_mid_matn_compiles_to_its_words():
    tagged = "<hadith id=\"h2\"><matn>بينما نحن جلوس عند رسول الله</matn></hadith>"
    # cut mid-matn so slice 1 is a bare continuation still inside hadith+matn
    slices = slice_tagged(tagged, _breaks_at(tagged, "عند"))
    frag = slices[1]
    assert frag.open_tags == [OpenTag(name="hadith", id="h2"),
                              OpenTag(name="matn", id=None)]
    closed = close_fragment(frag)
    text, spans, lines = compile_tagged(closed)   # must not raise
    # plain text equals exactly this fragment's words
    assert text == _strip_tags(frag.tagged)
    # a matn span covers the whole fragment's text
    assert any(s.label == "matn" and s.start == 0 and s.end == len(text)
               for s in spans)


# ── malformed input: over-closing raises a domain TagError ───────────────────

def test_slice_tagged_overclose_raises_tagerror():
    # `</hadith>` closes a tag that was never opened (stack empty) — a genuine
    # over-close. Must raise the domain TagError, not leak a bare IndexError.
    with pytest.raises(TagError):
        slice_tagged("<matn>x</matn></hadith>", [])


def test_slice_tagged_mismatched_close_raises_tagerror():
    # `</hadith>` while `<matn>` is on top of the stack — a mismatched close.
    with pytest.raises(TagError):
        slice_tagged("<matn>x</hadith>", [])


def test_close_fragment_balanced_via_open_tags_compiles():
    # A fragment that opens mid-context: its body starts by CLOSING `matn`,
    # which is legitimate because `open_tags` supplies the matching opener.
    # close_fragment must prepend that opener and compile cleanly.
    frag = PageSlice(
        tagged="جلوس</matn> <takhrij>رواه مسلم</takhrij>",
        open_tags=[OpenTag(name="hadith", id="h2"), OpenTag(name="matn")],
    )
    closed = close_fragment(frag)
    text, spans, _ = compile_tagged(closed)   # must not raise
    assert "جلوس" in text
    assert any(s.label == "takhrij" for s in spans)


def test_close_fragment_genuine_overclose_raises_tagerror():
    # Body closes `hadith` after `matn` has already balanced out — beyond what
    # the open_tags stack provides — so it is a genuine over-close.
    frag = PageSlice(
        tagged="جلوس</matn></hadith></qism>",
        open_tags=[OpenTag(name="hadith", id="h2"), OpenTag(name="matn")],
    )
    with pytest.raises(TagError):
        close_fragment(frag)


# ── Hadith of Jibril fixture: the canonical regression guard ─────────────────

JIBRIL = (
    "<hadith id=\"h2\"><isnad>«عن <person id=\"p7\">عمر</person> رضي الله "
    "تعالى عنه أيضا قال:</isnad> <matn>بينما نحن جلوس عند رسول الله صلى الله "
    "عليه وآله وسلم ذات يوم. فقال رسول الله: الإسلام أن تشهد أن لا إله إلا "
    "الله. قال: فأخبرني عن الساعة. ثم انطلق فلبثت مليا ثم قال: فإنه "
    "<person id=\"p8\">جبريل</person> أتاكم يعلمكم دينكم»</matn> "
    "<takhrij>رواه <person id=\"p9\">مسلم</person></takhrij></hadith>"
)


def test_jibril_three_page_split():
    # page 49 begins at "قال: فأخبرني عن الساعة"; page 50 at "ثم انطلق"
    breaks = _breaks_at(JIBRIL, "قال: فأخبرني عن الساعة", "ثم انطلق")
    slices = slice_tagged(JIBRIL, breaks)

    # 3 slices, lossless reconstruction
    assert len(slices) == 3
    assert reconstruct(slices) == JIBRIL

    # slices 2 and 3 are mid-matn, inside the still-open hadith
    expect = [OpenTag(name="hadith", id="h2"), OpenTag(name="matn", id=None)]
    assert slices[1].open_tags == expect
    assert slices[2].open_tags == expect

    # each slice, made independently well-formed, compiles in isolation
    for s in slices:
        compile_tagged(close_fragment(s))   # must not raise

    # concatenating the three (raw) fragments and compiling yields exactly one
    # matn span spanning the whole matn text — the matn is whole, not truncated
    # by the physical page splits. (Raw concatenation == reconstruct.)
    joined = reconstruct(slices)
    jtext, jspans, _ = compile_tagged(joined)
    jmatn = [s for s in jspans if s.label == "matn"]
    assert len(jmatn) == 1
    matn_text = jtext[jmatn[0].start:jmatn[0].end]
    # the matn runs from "بينما نحن جلوس" through the closing quote
    assert matn_text.startswith("بينما نحن جلوس")
    assert matn_text.endswith("دينكم»")
