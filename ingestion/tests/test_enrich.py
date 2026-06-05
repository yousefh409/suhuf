# ingestion/tests/test_enrich.py
"""Offline tests for AI catalog enrichment.

Both functions take an injected client so no test touches the network; the
client=None + no-key path must return {} gracefully.
"""
from ingestion.enrich import enrich_book_metadata, enrich_author_metadata
from ingestion.models import BookMetadata, Page, Block, Token, ParseResult


class _Resp:
    """Anthropic-style response: .content[0].text holds the body string."""
    def __init__(self, text):
        self.content = [type("B", (), {"text": text})()]


class _MockClient:
    """Records the create() call and returns a fixed JSON body."""
    def __init__(self, body):
        self._body = body
        self.calls = []
        self.messages = self

    def create(self, *, model, max_tokens, messages):
        self.calls.append({"model": model, "max_tokens": max_tokens, "messages": messages})
        return _Resp(self._body)


def _fixture() -> ParseResult:
    meta = BookMetadata(
        openiti_id="0676Nawawi.ArbacunaNawawiyya",
        title_ar="الأربعون النووية",
        author_openiti_id="0676Nawawi",
    )
    page = Page(page_number=1, content_blocks=[
        Block(key="b0", type="prose",
              tokens=[Token(id="p1_b0_w0", text="بسم"), Token(id="p1_b0_w1", text="الله")]),
    ])
    return ParseResult(metadata=meta, pages=[page], chapters=[])


def test_enrich_book_parses_json():
    body = (
        '{"title_en": "The Forty Hadith", '
        '"description": "A famous collection.", '
        '"genres": ["HADITH"], '
        '"composition_date_ah": 670, '
        '"commentary_on": null, "abridgement_of": null}'
    )
    client = _MockClient(body)
    out = enrich_book_metadata(_fixture(), client=client)
    assert out["title_en"] == "The Forty Hadith"
    assert out["genres"] == ["HADITH"]
    assert out["composition_date_ah"] == 670
    assert client.calls[0]["model"] == "anthropic/claude-sonnet-4.5"


def test_enrich_book_tolerates_markdown_fences():
    body = '```json\n{"title_en": "Fenced"}\n```'
    out = enrich_book_metadata(_fixture(), client=_MockClient(body))
    assert out["title_en"] == "Fenced"


def test_enrich_author_parses_json():
    body = (
        '{"full_name_en": "Yahya al-Nawawi", '
        '"bio_en": "A Shafi\'i scholar.", '
        '"birth_ah": 631, "death_ah": 676, '
        '"primary_fields": ["HADITH", "FIQH"]}'
    )
    client = _MockClient(body)
    out = enrich_author_metadata("0676Nawawi", {"shuhra_lat": "al-Nawawi"}, client=client)
    assert out["full_name_en"] == "Yahya al-Nawawi"
    assert out["birth_ah"] == 631
    assert out["death_ah"] == 676
    assert "0676Nawawi" in client.calls[0]["messages"][0]["content"]


def test_enrich_book_no_client_no_key_returns_empty(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    assert enrich_book_metadata(_fixture(), client=None) == {}


def test_enrich_author_no_client_no_key_returns_empty(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    assert enrich_author_metadata("0676Nawawi", {}, client=None) == {}
