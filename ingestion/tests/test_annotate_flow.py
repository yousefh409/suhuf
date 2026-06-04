"""Tests for the flow AI structure pass.

``annotate_flow`` sends each chunk's plain text to the model and expects the SAME
text back with ALL structure + entity tags added (attribute-free). Each returned
chunk is validated with ``compile_tagged``: a chunk that fails to compile, or
whose tags-stripped text differs from the input, falls back to the original
plain chunk (no tags) and is counted. Tests NEVER hit the real API — a mock
client is always supplied.
"""
import json

from ingestion.annotate_flow import annotate_flow
from ingestion.tags import compile_tagged


class _Resp:
    """Mimics an OpenAI-compatible (OpenRouter) chat completion response."""
    def __init__(self, text):
        msg = type("M", (), {"content": text})()
        self.choices = [type("Ch", (), {"message": msg})()]
        self.usage = type("U", (), {"prompt_tokens": 7, "completion_tokens": 9})()


class _MockClient:
    """Returns a scripted tagged string per chunk, keyed by the input text.

    ``script`` maps an input chunk's plain text -> the tagged string to return.
    Any chunk not in the script is echoed back unchanged (already valid plain).
    Exposes ``client.chat.completions.create`` like the OpenAI/OpenRouter SDK.
    """
    def __init__(self, script):
        self.script = script
        self.chat = self
        self.completions = self
        self.calls = 0

    def create(self, *, model, max_tokens, messages):
        self.calls += 1
        # messages = [system, user]; the chunk text is JSON-embedded in the user message.
        user = messages[1]["content"]
        payload = json.loads(user[user.find("{"):user.rfind("}") + 1])
        chunk = payload["text"]
        tagged = self.script.get(chunk, chunk)
        return _Resp(json.dumps({"tagged": tagged}, ensure_ascii=False))


def test_valid_tagged_output_is_kept():
    chunk = "عن زيد قال نعم"
    # the space between isnad and matn lives inside the matn so the tags-stripped
    # text is byte-identical to the input
    tagged = "<hadith><isnad>عن زيد</isnad><matn> قال نعم</matn></hadith>"
    client = _MockClient({chunk: tagged})
    out, stats = annotate_flow([chunk], client=client)
    assert out == [tagged]
    # round-trips: tags-stripped equals the input
    assert compile_tagged(out[0])[0] == chunk
    assert stats["fallbacks"] == 0
    assert stats["chunks"] == 1


def test_word_altering_output_falls_back_to_plain():
    chunk = "عن زيد قال نعم"
    # the model dropped a word -> tags-stripped != input
    bad = "<matn>عن زيد قال</matn>"
    client = _MockClient({chunk: bad})
    out, stats = annotate_flow([chunk], client=client)
    assert out == [chunk]            # fell back to the plain chunk
    assert stats["fallbacks"] == 1


def test_malformed_tags_fall_back_to_plain():
    chunk = "عن زيد"
    malformed = "<hadith><matn>عن زيد</hadith>"  # mismatched close
    client = _MockClient({chunk: malformed})
    out, stats = annotate_flow([chunk], client=client)
    assert out == [chunk]
    assert stats["fallbacks"] == 1


def test_multiple_chunks_mixed_outcomes():
    good_in = "عن أبي هريرة قال"
    good_out = "<hadith><isnad>عن أبي هريرة</isnad><matn> قال</matn></hadith>"
    bad_in = "متن ثان"
    bad_out = "<matn>متن مختلف</matn>"   # altered words
    client = _MockClient({good_in: good_out, bad_in: bad_out})
    out, stats = annotate_flow([good_in, bad_in], client=client)
    assert out == [good_out, bad_in]
    assert stats["fallbacks"] == 1
    assert stats["chunks"] == 2
    assert client.calls == 2


def test_no_client_returns_plain_chunks(monkeypatch):
    # No API key in the env -> no client is built and nothing hits the network.
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    chunks = ["نص أول", "نص ثان"]
    out, stats = annotate_flow(chunks, client=None)
    assert out == chunks
    assert stats["no_client"] is True
