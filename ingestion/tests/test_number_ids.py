"""Tests for the deterministic id-assignment pass (Phase 2).

The merged tagged document is numbered before slicing so ids are globally
unique by construction. Only id-bearing labels get a short, stable, sequential
id in document order; structural tags get none. Numbering must not change the
compiled result (the compiler ignores attributes) and must be idempotent.
"""
import re

import pytest

from ingestion.tags import compile_tagged, TagError
from ingestion.number_ids import assign_ids, ID_PREFIXES


# Strip the inserted `id="..."` attribute the same way page_slice reads it, so
# we can assert numbering round-trips back to the original input.
_ID_STRIP = re.compile(r'\s+id="[^"]*"')


def _strip_ids(s: str) -> str:
    return _ID_STRIP.sub("", s)


def test_ids_assigned_in_document_order():
    doc = (
        "<hadith><isnad>roots <person>A</person> from <person>B</person></isnad>"
        "<matn>said <person>C</person> see <quran>verse</quran></matn></hadith>"
        "<hadith><matn>second</matn></hadith>"
    )
    out = assign_ids(doc)
    assert 'id="h1"' in out and 'id="h2"' in out
    # persons strictly in document order
    persons = re.findall(r'<person id="([^"]*)">', out)
    assert persons == ["p1", "p2", "p3"]
    assert re.findall(r'<quran id="([^"]*)">', out) == ["q1"]
    # h1 precedes h2, p1<p2<p3, exact positions
    assert out.index('id="h1"') < out.index('id="h2"')
    assert out.index('id="p1"') < out.index('id="p2"') < out.index('id="p3"')


def test_structural_tags_get_no_id():
    doc = (
        "<hadith><isnad>a</isnad><matn>b <takhrij>c</takhrij></matn></hadith>"
    )
    out = assign_ids(doc)
    assert "<isnad>" in out
    assert "<matn>" in out
    assert "<takhrij>" in out
    # only the hadith was numbered
    assert out == doc.replace("<hadith>", '<hadith id="h1">')


def test_all_id_bearing_prefixes():
    doc = (
        "<person>a</person><place>b</place><quran>c</quran>"
        "<book_ref>d</book_ref><hadith_ref>e</hadith_ref>"
        "<date_hijri>f</date_hijri><hadith>g</hadith>"
    )
    out = assign_ids(doc)
    assert 'id="p1"' in out
    assert 'id="pl1"' in out
    assert 'id="q1"' in out
    assert 'id="b1"' in out
    assert 'id="hr1"' in out
    assert 'id="d1"' in out
    assert 'id="h1"' in out


def test_idempotent_on_numbered_output():
    doc = "<hadith><matn><person>A</person></matn></hadith><person>B</person>"
    once = assign_ids(doc)
    twice = assign_ids(once)
    assert once == twice


def test_preexisting_ids_left_untouched():
    # First person already has an id; the rest get numbered around it.
    doc = (
        '<person id="custom">A</person><person>B</person><person>C</person>'
    )
    out = assign_ids(doc)
    assert 'id="custom"' in out
    # The id-less ones get the next per-label counter values in order.
    persons = re.findall(r'<person id="([^"]*)">', out)
    assert persons == ["custom", "p1", "p2"]


def test_ids_strip_back_to_input():
    doc = (
        "<hadith><isnad><person>A</person></isnad>"
        "<matn>x <quran>q</quran> <book_ref>r</book_ref></matn></hadith>"
        "<person>B</person>"
    )
    out = assign_ids(doc)
    assert out != doc
    assert _strip_ids(out) == doc


def test_numbering_preserves_compiled_result():
    doc = (
        "<hadith><isnad>chain <person>A</person></isnad>"
        "<matn>body <quran>ayah</quran></matn></hadith>"
    )
    base_text, base_spans, base_lines = compile_tagged(doc)
    out_text, out_spans, out_lines = compile_tagged(assign_ids(doc))
    assert out_text == base_text
    assert out_spans == base_spans
    assert out_lines == base_lines


def test_global_numbering_across_merged_chunks():
    # Each chunk numbered independently would both be h1; numbering the MERGE
    # yields globally unique ids.
    chunk_a = "<hadith><matn>first</matn></hadith>"
    chunk_b = "<hadith><matn>second</matn></hadith>"
    out = assign_ids(chunk_a + chunk_b)
    hadiths = re.findall(r'<hadith id="([^"]*)">', out)
    assert hadiths == ["h1", "h2"]


def test_unknown_tag_raises():
    with pytest.raises(TagError):
        assign_ids("<hadith><bogus>x</bogus></hadith>")


def test_id_prefixes_is_module_constant():
    # Documented, extensible map: only id-bearing labels appear.
    assert ID_PREFIXES["hadith"] == "h"
    assert ID_PREFIXES["person"] == "p"
    assert ID_PREFIXES["place"] == "pl"
    assert ID_PREFIXES["quran"] == "q"
    assert ID_PREFIXES["book_ref"] == "b"
    assert ID_PREFIXES["hadith_ref"] == "hr"
    assert ID_PREFIXES["date_hijri"] == "d"
    # structural / pure-structure tags are NOT id-bearing
    for label in ("isnad", "matn", "takhrij", "verse", "hemistich", "footnote"):
        assert label not in ID_PREFIXES
