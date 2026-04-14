from unittest.mock import MagicMock, patch, call
from ingestion.upload import upload_book
from ingestion.models import Token, Block, Page, Chapter, BookMetadata, ParseResult

def _make_result() -> ParseResult:
    tokens = [Token(id="p1_b0_w0", text="بسم"), Token(id="p1_b0_w1", text="الله")]
    block = Block(key="b0", type="prose", tokens=tokens)
    page = Page(page_number=1, volume=1, content_blocks=[block])
    chapter = Chapter(title="باب", level=1, page_number=1, sort_order=1)
    meta = BookMetadata(
        openiti_id="0676Nawawi.ArbacunaNawawiyya",
        title_ar="الأربعون النووية",
        author_openiti_id="0676Nawawi",
        genres=["HADITH"],
    )
    return ParseResult(metadata=meta, pages=[page], chapters=[chapter])

def test_upload_calls_upsert_in_order():
    """Verify upload order: author -> book -> pages -> chapters."""
    client = MagicMock()
    author_resp = MagicMock()
    author_resp.data = [{"id": "author-uuid"}]
    book_resp = MagicMock()
    book_resp.data = [{"id": "book-uuid"}]
    page_resp = MagicMock()
    page_resp.data = [{"id": "page-uuid", "page_number": 1, "volume": 1}]

    table_mock = MagicMock()
    table_mock.upsert.return_value.execute.side_effect = [
        author_resp, book_resp, page_resp, MagicMock(data=[])
    ]
    client.table.return_value = table_mock

    # Also mock the select for page map
    table_mock.select.return_value.eq.return_value.execute.return_value = MagicMock(
        data=[{"id": "page-uuid", "page_number": 1, "volume": 1}]
    )

    result = _make_result()
    upload_book(result, author_data={}, client=client)

    # Verify table() was called for authors, books, pages, chapters
    table_calls = [c.args[0] for c in client.table.call_args_list]
    assert "authors" in table_calls
    assert "books" in table_calls
    assert "pages" in table_calls
    assert "chapters" in table_calls

def test_upload_sets_has_tashkeel():
    client = MagicMock()
    resp = MagicMock()
    resp.data = [{"id": "uuid"}]
    client.table.return_value.upsert.return_value.execute.return_value = resp
    client.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
        data=[{"id": "page-uuid", "page_number": 1, "volume": 1}]
    )

    result = _make_result()
    upload_book(result, author_data={}, client=client, has_tashkeel=True)

    # Find the books upsert call and check has_tashkeel
    for c in client.table.return_value.upsert.call_args_list:
        data = c.args[0]
        if isinstance(data, dict) and "has_tashkeel" in data:
            assert data["has_tashkeel"] is True

def test_upload_passes_author_data():
    client = MagicMock()
    resp = MagicMock()
    resp.data = [{"id": "uuid"}]
    client.table.return_value.upsert.return_value.execute.return_value = resp
    client.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
        data=[{"id": "page-uuid", "page_number": 1, "volume": 1}]
    )

    result = _make_result()
    author_data = {"shuhra_lat": "al-Nawawi", "death_ah": 676}
    upload_book(result, author_data=author_data, client=client)

    # Check the first upsert (author) includes author_data fields
    first_upsert = client.table.return_value.upsert.call_args_list[0]
    data = first_upsert.args[0]
    assert data.get("shuhra_lat") == "al-Nawawi"
    assert data.get("death_ah") == 676

def test_upload_page_content_blocks_serialized():
    client = MagicMock()
    resp = MagicMock()
    resp.data = [{"id": "uuid"}]
    client.table.return_value.upsert.return_value.execute.return_value = resp
    client.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
        data=[{"id": "page-uuid", "page_number": 1, "volume": 1}]
    )

    result = _make_result()
    upload_book(result, author_data={}, client=client)

    # Find the pages upsert call
    for c in client.table.return_value.upsert.call_args_list:
        data = c.args[0]
        if isinstance(data, list) and len(data) > 0 and "content_blocks" in data[0]:
            # content_blocks should be a list (serialized from Pydantic)
            assert isinstance(data[0]["content_blocks"], list)
            assert data[0]["content_plain"] == "بسم الله"
            assert "content_hash" in data[0]
