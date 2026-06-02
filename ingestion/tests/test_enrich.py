"""Tests for AI metadata enrichment stage."""
import json
from unittest.mock import MagicMock
from ingestion.enrich import enrich_book_metadata, enrich_author_metadata, _build_book_prompt, _build_author_prompt, resolve_spans
from ingestion.models import Token, Block, Page, Chapter, BookMetadata, ParseResult, Span


def _make_result() -> ParseResult:
    tokens = [Token(id="p35_b0_w0", text="بسم"), Token(id="p35_b0_w1", text="الله")]
    block = Block(key="b0", type="prose", tokens=tokens)
    page = Page(page_number=35, volume=1, content_blocks=[block])
    chapter = Chapter(title="الحديث الأول", level=1, page_number=35, sort_order=1)
    meta = BookMetadata(
        openiti_id="0676Nawawi.ArbacunaNawawiyya",
        title_ar="الأربعون النووية",
        author_openiti_id="0676Nawawi",
    )
    return ParseResult(metadata=meta, pages=[page], chapters=[chapter])


def test_build_book_prompt_includes_title():
    result = _make_result()
    prompt = _build_book_prompt(result)
    assert "الأربعون النووية" in prompt


def test_build_book_prompt_includes_chapters():
    result = _make_result()
    prompt = _build_book_prompt(result)
    assert "الحديث الأول" in prompt


def test_build_book_prompt_includes_sample_content():
    result = _make_result()
    prompt = _build_book_prompt(result)
    assert "بسم" in prompt


def test_build_author_prompt_includes_author_id():
    prompt = _build_author_prompt("0676Nawawi", {"shuhra_lat": "al-Nawawi"})
    assert "0676Nawawi" in prompt
    assert "al-Nawawi" in prompt


def test_enrich_book_metadata_parses_response():
    result = _make_result()
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text=json.dumps({
        "title_en": "The Forty Hadiths of al-Nawawi",
        "description": "A collection of forty-two hadiths.",
        "genres": ["HADITH", "ETHICS"],
        "composition_date_ah": 670,
        "commentary_on": None,
        "abridgement_of": None,
    }))]

    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_response

    enriched = enrich_book_metadata(result, client=mock_client)
    assert enriched["title_en"] == "The Forty Hadiths of al-Nawawi"
    assert enriched["description"] == "A collection of forty-two hadiths."
    assert "HADITH" in enriched["genres"]
    assert enriched["composition_date_ah"] == 670


def test_enrich_book_metadata_handles_malformed_json():
    result = _make_result()
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text="not valid json {{{")]

    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_response

    enriched = enrich_book_metadata(result, client=mock_client)
    assert enriched == {}


def test_enrich_book_metadata_handles_api_error():
    result = _make_result()
    mock_client = MagicMock()
    mock_client.messages.create.side_effect = Exception("API error")

    enriched = enrich_book_metadata(result, client=mock_client)
    assert enriched == {}


def test_enrich_author_metadata_parses_response():
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text=json.dumps({
        "full_name_en": "Yahya ibn Sharaf al-Nawawi",
        "bio_en": "A renowned Shafi'i jurist and hadith scholar.",
        "birth_ah": 631,
        "death_ah": 676,
    }))]

    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_response

    enriched = enrich_author_metadata("0676Nawawi", {}, client=mock_client)
    assert enriched["full_name_en"] == "Yahya ibn Sharaf al-Nawawi"
    assert enriched["bio_en"] == "A renowned Shafi'i jurist and hadith scholar."


def test_enrich_author_metadata_handles_error():
    mock_client = MagicMock()
    mock_client.messages.create.side_effect = Exception("API error")

    enriched = enrich_author_metadata("0676Nawawi", {}, client=mock_client)
    assert enriched == {}


# ---------------------------------------------------------------------------
# resolve_spans tests
# ---------------------------------------------------------------------------

def _make_fatiha_result() -> tuple[ParseResult, Span]:
    """ParseResult with one quran block whose tokens spell the Fatiha ayah."""
    tokens = [
        Token(id="p1_b0_w0", text="\uFD3F\u0627\u0644\u062D\u0645\u062F"),  # ﴿الحمد
        Token(id="p1_b0_w1", text="\u0644\u0644\u0647"),                     # لله
        Token(id="p1_b0_w2", text="\u0631\u0628"),                           # رب
        Token(id="p1_b0_w3", text="\u0627\u0644\u0639\u0627\u0644\u0645\u064A\u0646\uFD3E"),  # العالمين﴾
    ]
    span = Span(start_token_id="p1_b0_w0", end_token_id="p1_b0_w3", label="quran", ref=None)
    block = Block(key="b0", type="quran", tokens=tokens, spans=[span])
    page = Page(page_number=1, volume=1, content_blocks=[block])
    meta = BookMetadata(
        openiti_id="test.book",
        title_ar="كتاب اختبار",
        author_openiti_id="0000Test",
    )
    return ParseResult(metadata=meta, pages=[page], chapters=[]), span


def test_resolve_spans_sets_quran_ref():
    result, span = _make_fatiha_result()
    count = resolve_spans(result)
    assert span.ref == "1:2"
    assert count == 1


def test_resolve_spans_overwrites_wrong_ref():
    result, span = _make_fatiha_result()
    span.ref = "99:99"
    count = resolve_spans(result)
    assert span.ref == "1:2"
    assert count == 1


def test_resolve_spans_passes_through_non_quran():
    tokens = [Token(id="p1_b0_w0", text="محمد"), Token(id="p1_b0_w1", text="النووي")]
    span = Span(start_token_id="p1_b0_w0", end_token_id="p1_b0_w1", label="person", ref=None)
    block = Block(key="b0", type="prose", tokens=tokens, spans=[span])
    page = Page(page_number=1, volume=1, content_blocks=[block])
    meta = BookMetadata(
        openiti_id="test.book",
        title_ar="كتاب اختبار",
        author_openiti_id="0000Test",
    )
    result = ParseResult(metadata=meta, pages=[page], chapters=[])
    count = resolve_spans(result)
    assert span.ref is None
    assert count == 0


def test_resolve_spans_no_match_leaves_ref():
    # Non-Quranic text — lookup will return None
    tokens = [Token(id="p1_b0_w0", text="كلام"), Token(id="p1_b0_w1", text="مجهول")]
    span = Span(start_token_id="p1_b0_w0", end_token_id="p1_b0_w1", label="quran", ref=None)
    block = Block(key="b0", type="quran", tokens=tokens, spans=[span])
    page = Page(page_number=1, volume=1, content_blocks=[block])
    meta = BookMetadata(
        openiti_id="test.book",
        title_ar="كتاب اختبار",
        author_openiti_id="0000Test",
    )
    result = ParseResult(metadata=meta, pages=[page], chapters=[])
    count = resolve_spans(result)
    assert span.ref is None
    assert count == 0


def test_resolve_spans_handles_poetry_block():
    # Poetry block: hemistichs = [[[token, token], [token, token]]]
    # The tokens together spell the Fatiha ayah
    t0 = Token(id="p1_b0_w0", text="\uFD3F\u0627\u0644\u062D\u0645\u062F")  # ﴿الحمد
    t1 = Token(id="p1_b0_w1", text="\u0644\u0644\u0647")                     # لله
    t2 = Token(id="p1_b0_w2", text="\u0631\u0628")                           # رب
    t3 = Token(id="p1_b0_w3", text="\u0627\u0644\u0639\u0627\u0644\u0645\u064A\u0646\uFD3E")  # العالمين﴾
    # One verse, two hemistichs: [t0, t1] and [t2, t3]
    span = Span(start_token_id="p1_b0_w0", end_token_id="p1_b0_w3", label="quran", ref=None)
    block = Block(key="b0", type="poetry", hemistichs=[[[t0, t1], [t2, t3]]], spans=[span])
    page = Page(page_number=1, volume=1, content_blocks=[block])
    meta = BookMetadata(
        openiti_id="test.book",
        title_ar="كتاب اختبار",
        author_openiti_id="0000Test",
    )
    result = ParseResult(metadata=meta, pages=[page], chapters=[])
    count = resolve_spans(result)
    assert span.ref == "1:2"
    assert count == 1


def test_resolve_spans_returns_count():
    result, span = _make_fatiha_result()
    count = resolve_spans(result)
    assert isinstance(count, int)
    assert count == 1
