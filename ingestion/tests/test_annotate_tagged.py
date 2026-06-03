"""Tests for the tagged annotate pass: the gated merge over offset spans."""
from ingestion.tagged_format import Span
from ingestion.annotate_tagged import merge_spans


def test_entity_nests_inside_locked_structural():
    # The bug the new format fixes: a person inside a high-conf isnad must
    # survive, not be dropped for overlapping a locked span.
    detector = [Span(start=0, end=40, label="isnad", conf=0.95)]
    ai = [Span(start=0, end=40, label="isnad"), Span(start=3, end=14, label="person")]
    out = merge_spans(detector, ai)
    assert any(s.label == "person" and s.start == 3 for s in out)
    assert any(s.label == "isnad" and s.end == 40 for s in out)


def test_locked_structural_boundary_wins():
    # AI tries to move a high-conf isnad boundary; the detector's wins.
    detector = [Span(start=0, end=40, label="isnad", conf=0.95)]
    ai = [Span(start=0, end=20, label="isnad")]
    out = merge_spans(detector, ai)
    isnads = [s for s in out if s.label == "isnad"]
    assert len(isnads) == 1 and isnads[0].end == 40


def test_low_confidence_structural_can_be_corrected():
    # A low-conf detector boundary is replaceable by the AI's.
    detector = [Span(start=0, end=30, label="matn", conf=0.70)]
    ai = [Span(start=0, end=25, label="matn")]
    out = merge_spans(detector, ai)
    matns = [s for s in out if s.label == "matn"]
    assert len(matns) == 1 and matns[0].end == 25


def test_locked_conf_is_preserved_on_output():
    detector = [Span(start=0, end=40, label="isnad", conf=0.95)]
    out = merge_spans(detector, [Span(start=0, end=40, label="isnad")])
    assert next(s for s in out if s.label == "isnad").conf == 0.95
