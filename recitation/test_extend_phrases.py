"""Unit tests for StreamingSession.extend_phrases and the append_phrases WS routing."""
import json

# ---------------------------------------------------------------------------
# Minimal fake engine — no model load required
# ---------------------------------------------------------------------------

class _FakeEngine:
    """Stub engine that satisfies StreamingSession without loading any model."""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_session(phrases):
    """Create a StreamingSession with a fake engine."""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent))
    from engine import StreamingSession
    return StreamingSession(_FakeEngine(), phrases)


# ---------------------------------------------------------------------------
# extend_phrases tests
# ---------------------------------------------------------------------------

def test_extend_appends_new_phrases():
    """extend_phrases adds new phrases to self.phrases."""
    session = _make_session(["الْحَمْدُ لِلَّهِ", "رَبِّ الْعَالَمِينَ"])
    session.extend_phrases(["الرَّحْمَنِ الرَّحِيمِ"])
    assert session.phrases == [
        "الْحَمْدُ لِلَّهِ",
        "رَبِّ الْعَالَمِينَ",
        "الرَّحْمَنِ الرَّحِيمِ",
    ]


def test_extend_preserves_cursor_and_watermarks():
    """Appending phrases does not reset cursor_phrase or _best_spoken."""
    session = _make_session(["phrase one", "phrase two"])
    # Simulate progress
    session.cursor_phrase = 1
    session._best_spoken[0] = 2
    session._best_spoken[1] = 1

    session.extend_phrases(["phrase three"])

    assert session.cursor_phrase == 1
    assert session._best_spoken[0] == 2
    assert session._best_spoken[1] == 1


def test_extend_preserves_scored_words():
    """extend_phrases does not clear accumulated word scores."""
    session = _make_session(["phrase one"])
    session.scored_words[0] = {"effective_score": -0.5, "word_idx": 0}

    session.extend_phrases(["phrase two"])

    assert 0 in session.scored_words


def test_extend_filters_empty_and_whitespace():
    """Empty strings and whitespace-only entries are ignored."""
    session = _make_session(["first phrase"])
    session.extend_phrases(["", "  ", "\t", "real phrase"])
    assert session.phrases == ["first phrase", "real phrase"]


def test_extend_filters_non_strings():
    """Non-string entries are silently ignored."""
    session = _make_session(["first phrase"])
    session.extend_phrases([None, 42, True, "valid phrase"])
    assert session.phrases == ["first phrase", "valid phrase"]


def test_extend_updates_phrase_word_offsets():
    """phrase_word_offsets grows to cover the new phrases."""
    session = _make_session(["word1 word2"])  # offset 0 → 2 words
    session.extend_phrases(["word3 word4 word5"])  # should get offset 2
    assert len(session.phrase_word_offsets) == 2
    assert session.phrase_word_offsets[1] == 2  # starts after the first two words


def test_extend_updates_all_words():
    """all_words list is extended with words from new phrases."""
    session = _make_session(["hello world"])
    session.extend_phrases(["foo bar baz"])
    assert session.all_words == ["hello", "world", "foo", "bar", "baz"]


def test_extend_updates_stripped_phrases():
    """_stripped_phrases is extended so position tracking still works."""
    session = _make_session(["مَرْحَبًا"])
    session.extend_phrases(["بِسْمِ اللَّهِ"])
    assert len(session._stripped_phrases) == 2


def test_extend_no_phrases_is_noop():
    """Calling extend_phrases([]) changes nothing."""
    session = _make_session(["only phrase"])
    before_phrases = list(session.phrases)
    before_offsets = list(session.phrase_word_offsets)
    session.extend_phrases([])
    assert session.phrases == before_phrases
    assert session.phrase_word_offsets == before_offsets


def test_extend_audio_state_untouched():
    """Audio ring buffer and total_audio_bytes are not touched."""
    session = _make_session(["phrase one"])
    session.audio_ring = bytearray(b"\x00" * 64)
    session.total_audio_bytes = 64

    session.extend_phrases(["phrase two"])

    assert len(session.audio_ring) == 64
    assert session.total_audio_bytes == 64


# ---------------------------------------------------------------------------
# WS routing — test the JSON-routing logic extracted from ws_score
# ---------------------------------------------------------------------------

def _route_text_message(text, session, handled):
    """
    Mirror the routing logic from the ws_score receive loop.

    Returns True if the message was consumed (continue), False if it
    fell through to the next branch (e.g. `not raw` skip).

    `handled` is a list — append a string so the caller can assert.
    """
    if text == "done":
        handled.append("done")
        return True
    try:
        msg = json.loads(text)
    except (ValueError, TypeError):
        return False
    if isinstance(msg, dict) and msg.get("type") == "append_phrases":
        new_phrases = msg.get("phrases", [])
        if isinstance(new_phrases, list):
            session.extend_phrases(new_phrases)
            handled.append("append_phrases")
            return True
    return False


def test_ws_routing_done_signal():
    """'done' text message is consumed without touching the session."""
    session = _make_session(["phrase one"])
    handled = []
    assert _route_text_message("done", session, handled) is True
    assert handled == ["done"]
    assert session.phrases == ["phrase one"]  # untouched


def test_ws_routing_append_phrases():
    """JSON append_phrases message extends the session and is consumed."""
    session = _make_session(["phrase one"])
    msg = json.dumps({"type": "append_phrases", "phrases": ["phrase two"]})
    handled = []
    assert _route_text_message(msg, session, handled) is True
    assert handled == ["append_phrases"]
    assert "phrase two" in session.phrases


def test_ws_routing_append_phrases_filters_blanks():
    """Blank entries in the WS payload are filtered by extend_phrases."""
    session = _make_session(["phrase one"])
    msg = json.dumps({"type": "append_phrases", "phrases": ["", "phrase two", "  "]})
    _route_text_message(msg, session, [])
    assert session.phrases == ["phrase one", "phrase two"]


def test_ws_routing_unknown_type_not_consumed():
    """Unknown JSON type falls through (returns False)."""
    session = _make_session(["phrase one"])
    msg = json.dumps({"type": "unknown_event"})
    handled = []
    assert _route_text_message(msg, session, handled) is False
    assert handled == []


def test_ws_routing_plain_text_not_consumed():
    """Plain text that is not 'done' and not valid JSON is not consumed."""
    session = _make_session(["phrase one"])
    handled = []
    assert _route_text_message("hello", session, handled) is False
    assert handled == []
