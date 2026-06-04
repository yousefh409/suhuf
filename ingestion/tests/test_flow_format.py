"""Tests for the flow-format models and the annotations builder.

The flow format stores the book as one continuous tagged document, sliced into
pages. The annotations builder parses the id-bearing tags out of the NUMBERED
continuous tagged string (post ``assign_ids``) and records each id, label, and
its char range in the compiled plain text, filling ``meta`` per label.
"""
from ingestion.flow_format import (
    Annotation,
    FlowPage,
    FlowBook,
    build_annotations,
)
from ingestion.models import BookMetadata
from ingestion.number_ids import assign_ids
from ingestion.page_slice import OpenTag


def _meta():
    return BookMetadata(openiti_id="t.1", title_ar="x", author_openiti_id="a")


# ── models ───────────────────────────────────────────────────────────────────

def test_flowpage_defaults():
    p = FlowPage(page_number=3, tagged="<hadith>x</hadith>")
    assert p.page_number == 3
    assert p.volume == 1
    assert p.open_tags == []
    assert p.text == ""
    assert p.start_offset == 0


def test_flowbook_defaults():
    b = FlowBook(metadata=_meta())
    assert b.pages == []
    assert b.chapters == []
    assert b.annotations == []


def test_annotation_meta_default():
    a = Annotation(id="h1", label="hadith", start=0, end=5)
    assert a.meta == {}


def test_flowpage_open_tags_roundtrip():
    p = FlowPage(page_number=2, tagged="</matn></hadith>",
                 open_tags=[OpenTag(name="hadith", id="h1"), OpenTag(name="matn")])
    assert p.open_tags[0].name == "hadith"
    assert p.open_tags[0].id == "h1"
    assert p.open_tags[1].name == "matn"


# ── annotations builder ──────────────────────────────────────────────────────

def test_build_annotations_records_ids_and_ranges():
    doc = assign_ids(
        "<hadith><isnad><person>زيد</person></isnad>"
        "<matn>قال نعم</matn></hadith>"
    )
    anns = build_annotations(doc)
    by_id = {a.id: a for a in anns}
    # the hadith and person are id-bearing; isnad/matn are not
    assert "h1" in by_id and "p1" in by_id
    assert all(a.label != "isnad" and a.label != "matn" for a in anns)
    h = by_id["h1"]
    assert h.label == "hadith"
    # hadith spans the whole compiled plain text (tags are adjacent, no space
    # between "زيد" and "قال": compiled plain is "زيدقال نعم").
    assert h.start == 0
    assert h.end == len("زيدقال نعم")
    # person range covers exactly "زيد"
    p = by_id["p1"]
    assert p.label == "person"
    assert p.start == 0
    assert p.end == len("زيد")


def test_build_annotations_quran_meta_resolved():
    text = "قال تعالى الحمد لله رب العالمين بعد"
    quote = "الحمد لله رب العالمين"
    doc = assign_ids(text.replace(quote, f"<quran>{quote}</quran>"))
    anns = build_annotations(doc)
    q = next(a for a in anns if a.label == "quran")
    assert q.meta == {"sura": 1, "ayah": 2}


def test_build_annotations_hadith_source_number():
    doc = assign_ids("<hadith><matn>متن الحديث</matn></hadith>")
    # the numbered unit "2" starts within the hadith's range
    anns = build_annotations(doc, hadith_numbers=[(0, "2")])
    h = next(a for a in anns if a.label == "hadith")
    assert h.meta == {"number": "2"}


def test_build_annotations_unresolved_person_has_empty_meta():
    doc = assign_ids("<person>فلان</person>")
    anns = build_annotations(doc)
    p = next(a for a in anns if a.label == "person")
    assert p.id == "p1"
    assert p.meta == {}


def test_build_annotations_hadith_without_number_has_null_meta():
    doc = assign_ids("<hadith><matn>نص</matn></hadith>")
    anns = build_annotations(doc)  # no hadith_numbers supplied
    h = next(a for a in anns if a.label == "hadith")
    assert h.meta.get("number") is None
