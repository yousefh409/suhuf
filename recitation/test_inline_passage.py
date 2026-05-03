"""Unit tests for parse_ws_init — inline passage and passage_id forms."""
import pytest

# server transitively imports torch via engine. Skip cleanly under CI's
# slim env where torch isn't installed.
pytest.importorskip("torch")

from server import parse_ws_init


def test_inline_passage_returns_phrases():
    """Inline passage form returns the supplied phrases."""
    phrases, log_info = parse_ws_init(
        {"passage": {"id": "x", "phrases": ["a", "b"]}},
        load_passages_fn=lambda: {},
    )
    assert phrases == ["a", "b"]


def test_inline_passage_rejects_empty():
    """Inline passage with only blank strings raises ValueError."""
    with pytest.raises(ValueError, match="Inline passage has no phrases"):
        parse_ws_init(
            {"passage": {"id": "x", "phrases": ["", "  "]}},
            load_passages_fn=lambda: {},
        )


def test_inline_passage_filters_blank_phrases():
    """Blank entries mixed with real phrases are filtered out."""
    phrases, _ = parse_ws_init(
        {"passage": {"id": "x", "phrases": ["hello", "", "world", "  "]}},
        load_passages_fn=lambda: {},
    )
    assert phrases == ["hello", "world"]


def test_passage_id_form_still_works():
    """passage_id form looks up phrases from load_passages_fn."""
    def fake_load():
        return {"passages": [{"id": "x", "phrases": ["q"]}]}

    phrases, _ = parse_ws_init({"passage_id": "x"}, load_passages_fn=fake_load)
    assert phrases == ["q"]


def test_passage_id_not_found_errors():
    """Unknown passage_id raises ValueError."""
    with pytest.raises(ValueError, match="Passage not found"):
        parse_ws_init(
            {"passage_id": "missing"},
            load_passages_fn=lambda: {"passages": []},
        )


def test_init_without_either_field_errors():
    """Init dict with neither passage nor passage_id raises ValueError."""
    with pytest.raises(ValueError, match="must include"):
        parse_ws_init({}, load_passages_fn=lambda: {})


def test_inline_log_info_has_inline_id():
    """log_info exposes the inline passage id for session directory naming."""
    _, log_info = parse_ws_init(
        {"passage": {"id": "my-id", "phrases": ["text"]}},
        load_passages_fn=lambda: {},
    )
    assert log_info.get("log_label") == "my-id"
    assert log_info.get("passage_id") is None
    assert log_info.get("inline_id") == "my-id"


def test_passage_id_log_info():
    """log_info for passage_id form has passage_id set and inline_id None."""
    def fake_load():
        return {"passages": [{"id": "ajr", "phrases": ["x"]}]}

    _, log_info = parse_ws_init({"passage_id": "ajr"}, load_passages_fn=fake_load)
    assert log_info.get("log_label") == "ajr"
    assert log_info.get("passage_id") == "ajr"
    assert log_info.get("inline_id") is None
