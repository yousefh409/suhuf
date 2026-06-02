"""Tests for the annotate pass — frozen vocabulary enforcement."""
import json
from unittest.mock import MagicMock

from ingestion.annotate import (
    BLOCK_TYPES,
    SPAN_LABELS,
    _apply_block_annotation,
)
from ingestion.models import Block, Token


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_block(key: str = "b0", btype: str = "prose", n_tokens: int = 4) -> Block:
    tokens = [Token(id=f"p1_{key}_w{i}", text=f"كلمة{i}") for i in range(n_tokens)]
    return Block(key=key, type=btype, tokens=tokens)


# ---------------------------------------------------------------------------
# Constant-shape tests  (fail before implementation)
# ---------------------------------------------------------------------------

def test_span_labels_constant_is_frozen_set():
    assert set(SPAN_LABELS) == {"quran", "person", "place", "book_ref", "hadith_ref", "date_hijri"}


def test_block_types_constant_is_frozen_set():
    assert set(BLOCK_TYPES) == {"prose", "heading", "poetry", "isnad", "matn", "takhrij", "quran"}


# ---------------------------------------------------------------------------
# _apply_block_annotation — span acceptance / rejection
# ---------------------------------------------------------------------------

def test_apply_accepts_frozen_span_labels():
    block = _make_block(n_tokens=6)
    ann = {
        "key": "p1_b0",
        "type": "prose",
        "confidence": 0.5,
        "spans": [
            {"start": 0, "end": 0, "label": "person", "sub_label": "scholar", "confidence": 0.9},
            {"start": 1, "end": 1, "label": "quran", "ref": "2:255", "confidence": 0.95},
            {"start": 2, "end": 3, "label": "book_ref", "confidence": 0.8},
        ],
        "flags": [],
    }
    _apply_block_annotation(block, ann)
    stored_labels = {s.label for s in block.spans}
    assert "person" in stored_labels
    assert "quran" in stored_labels
    assert "book_ref" in stored_labels
    assert len(block.spans) == 3


def test_apply_rejects_old_span_labels():
    block = _make_block(n_tokens=4)
    ann = {
        "key": "p1_b0",
        "type": "prose",
        "confidence": 0.5,
        "spans": [
            # OLD label — must be filtered out
            {"start": 0, "end": 1, "label": "personal_name", "confidence": 0.9},
        ],
        "flags": [],
    }
    _apply_block_annotation(block, ann)
    assert len(block.spans) == 0


# ---------------------------------------------------------------------------
# _apply_block_annotation — block relabeling
# ---------------------------------------------------------------------------

def test_apply_accepts_frozen_block_relabel():
    block = _make_block(btype="prose")
    ann = {
        "key": "p1_b0",
        "type": "takhrij",
        "confidence": 0.9,
        "spans": [],
        "flags": [],
    }
    _apply_block_annotation(block, ann)
    assert block.type == "takhrij"
    assert block.parser_type == "prose"


def test_apply_rejects_cut_block_type():
    block = _make_block(btype="prose")
    ann = {
        "key": "p1_b0",
        "type": "biography",   # cut type — not in frozen set
        "confidence": 0.9,
        "spans": [],
        "flags": [],
    }
    _apply_block_annotation(block, ann)
    assert block.type == "prose"   # unchanged
