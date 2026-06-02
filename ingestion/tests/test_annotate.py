"""Tests for the annotate pass — frozen vocabulary enforcement."""
import json
from unittest.mock import MagicMock

from ingestion.annotate import (
    BLOCK_TYPES,
    MIN_NATIVE_TAGS,
    SPAN_LABELS,
    _apply_block_annotation,
    annotate_book,
)
from ingestion.models import Block, BookMetadata, Page, ParseResult, Token


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
    _apply_block_annotation(block, ann, allow_relabel=True)
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


# ---------------------------------------------------------------------------
# annotate_book — native-tags / relabel decoupling
# ---------------------------------------------------------------------------

def _make_parse_result(blocks_spec: list[tuple[str, str]]) -> ParseResult:
    """Build a minimal ParseResult from a list of (key, type) tuples.

    All blocks land on page 1. Each block gets 4 tokens so span resolution works.
    """
    meta = BookMetadata(
        openiti_id="test.001",
        title_ar="كتاب",
        author_openiti_id="0000Author",
    )
    content_blocks = []
    for key, btype in blocks_spec:
        tokens = [Token(id=f"p1_{key}_w{i}", text=f"كلمة{i}") for i in range(4)]
        content_blocks.append(Block(key=key, type=btype, tokens=tokens))
    page = Page(page_number=1, content_blocks=content_blocks)
    return ParseResult(metadata=meta, pages=[page])


def _make_mock_client(key_to_ann: dict) -> MagicMock:
    """Return a mock Anthropic client whose messages.create returns a fixed
    response containing the supplied annotations keyed by global key."""
    annotations = list(key_to_ann.values())
    body = json.dumps({"blocks": annotations})
    msg = MagicMock()
    msg.content = [MagicMock(text=body)]
    msg.usage.input_tokens = 10
    msg.usage.output_tokens = 20
    client = MagicMock()
    client.messages.create.return_value = msg
    return client


def test_spans_detected_even_with_native_tags():
    """Spans must be attached even when native tags are present (force=False).

    The relabel suggestion (matn -> prose) must be SUPPRESSED because native
    tags are present and force is False. But the span must appear.
    """
    # Build MIN_NATIVE_TAGS isnad/matn blocks to trip _has_native_tags
    specs: list[tuple[str, str]] = [(f"b{i}", "isnad") for i in range(MIN_NATIVE_TAGS)]
    # Add one extra matn block that the model will try to relabel to prose
    specs.append(("btarget", "matn"))
    result = _make_parse_result(specs)

    # The model suggests relabeling btarget (matn -> prose) AND adds a person span
    annotations = {
        "p1_btarget": {
            "key": "p1_btarget",
            "type": "prose",         # relabel suggestion — should be suppressed
            "confidence": 0.9,
            "spans": [
                {"start": 0, "end": 0, "label": "person", "sub_label": "scholar", "confidence": 0.9}
            ],
            "flags": [],
        }
    }
    mock_client = _make_mock_client(annotations)

    stats = annotate_book(result, client=mock_client)

    # The Claude pass ran — client was called
    assert mock_client.messages.create.called

    target_block = result.pages[0].content_blocks[-1]
    # Relabel must be suppressed (native tags present, force=False)
    assert target_block.type == "matn"
    # Span must be attached
    assert len(target_block.spans) == 1
    assert target_block.spans[0].label == "person"

    # Stats
    assert stats["relabeled"] == 0
    assert stats["spans_total"] == 1
    assert stats.get("relabel_allowed") is False


def test_relabel_applied_when_no_native_tags():
    """Relabel and spans both apply when there are no native tags."""
    # Only prose blocks — below native-tags threshold
    specs = [(f"b{i}", "prose") for i in range(5)]
    result = _make_parse_result(specs)

    annotations = {
        "p1_b0": {
            "key": "p1_b0",
            "type": "takhrij",
            "confidence": 0.9,
            "spans": [
                {"start": 1, "end": 1, "label": "book_ref", "confidence": 0.85}
            ],
            "flags": [],
        }
    }
    mock_client = _make_mock_client(annotations)

    stats = annotate_book(result, client=mock_client)

    b0 = result.pages[0].content_blocks[0]
    assert b0.type == "takhrij"
    assert b0.parser_type == "prose"
    assert len(b0.spans) == 1
    assert b0.spans[0].label == "book_ref"

    assert stats["relabeled"] == 1
    assert stats["spans_total"] == 1
    assert stats.get("relabel_allowed") is True


def test_force_allows_relabel_even_with_native_tags():
    """With force=True, relabels apply even when native tags are present."""
    specs: list[tuple[str, str]] = [(f"b{i}", "isnad") for i in range(MIN_NATIVE_TAGS)]
    specs.append(("btarget", "matn"))
    result = _make_parse_result(specs)

    annotations = {
        "p1_btarget": {
            "key": "p1_btarget",
            "type": "prose",
            "confidence": 0.9,
            "spans": [
                {"start": 0, "end": 0, "label": "person", "confidence": 0.9}
            ],
            "flags": [],
        }
    }
    mock_client = _make_mock_client(annotations)

    stats = annotate_book(result, client=mock_client, force=True)

    target_block = result.pages[0].content_blocks[-1]
    # force=True overrides native-tags gate — relabel must apply
    assert target_block.type == "prose"
    assert target_block.parser_type == "matn"
    assert len(target_block.spans) == 1

    assert stats["relabeled"] == 1
    assert stats.get("relabel_allowed") is True
