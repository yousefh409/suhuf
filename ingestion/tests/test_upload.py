# ingestion/tests/test_upload.py
from unittest.mock import MagicMock
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


def _make_mock_client():
    """Create a mock Supabase client with chaining support."""
    client = MagicMock()

    # Each table call returns a fresh mock that supports .upsert().execute() and .select()...
    # We need to track calls per table
    author_resp = MagicMock()
    author_resp.data = [{"id": "author-uuid-123"}]

    book_resp = MagicMock()
    book_resp.data = [{"id": "book-uuid-456"}]

    page_resp = MagicMock()
    page_resp.data = [{"id": "page-uuid-789", "page_number": 1, "volume": 1}]

    chapter_resp = MagicMock()
    chapter_resp.data = [{"id": "chapter-uuid-abc"}]

    pages_select_resp = MagicMock()
    pages_select_resp.data = [{"id": "page-uuid-789", "page_number": 1, "volume": 1}]

    # Track which table is called and return appropriate mock
    table_mocks = {}

    def table_side_effect(name):
        if name not in table_mocks:
            table_mocks[name] = MagicMock()
        mock = table_mocks[name]

        if name == "authors":
            mock.upsert.return_value.execute.return_value = author_resp
        elif name == "books":
            mock.upsert.return_value.execute.return_value = book_resp
        elif name == "pages":
            mock.upsert.return_value.execute.return_value = page_resp
            mock.select.return_value.eq.return_value.execute.return_value = pages_select_resp
        elif name == "chapters":
            mock.upsert.return_value.execute.return_value = chapter_resp

        return mock

    client.table.side_effect = table_side_effect
    return client, table_mocks


def test_upload_calls_tables_in_order():
    """Verify upload order: author -> book -> pages -> chapters."""
    client, table_mocks = _make_mock_client()
    result = _make_result()
    upload_book(result, author_data={}, client=client)

    table_names = [c.args[0] for c in client.table.call_args_list]
    assert "authors" in table_names
    assert "books" in table_names
    assert "pages" in table_names
    assert "chapters" in table_names
    # Authors and books must come before pages and chapters
    authors_idx = table_names.index("authors")
    books_idx = table_names.index("books")
    pages_idx = table_names.index("pages")
    assert authors_idx < books_idx < pages_idx


def test_upload_upserts_author():
    client, table_mocks = _make_mock_client()
    result = _make_result()
    upload_book(result, author_data={"shuhra_lat": "al-Nawawi", "death_ah": 676}, client=client)

    # Check authors table was called with upsert
    authors_mock = table_mocks["authors"]
    upsert_data = authors_mock.upsert.call_args.args[0]
    assert upsert_data["openiti_id"] == "0676Nawawi"
    assert upsert_data["shuhra_ar"] == "al-Nawawi"  # falls back to shuhra_lat
    assert upsert_data["death_ah"] == 676


def test_upload_upserts_book_with_tashkeel_flag():
    client, table_mocks = _make_mock_client()
    result = _make_result()
    upload_book(result, author_data={}, client=client, has_tashkeel=True)

    books_mock = table_mocks["books"]
    upsert_data = books_mock.upsert.call_args.args[0]
    assert upsert_data["has_tashkeel"] is True
    assert upsert_data["openiti_id"] == "0676Nawawi.ArbacunaNawawiyya"
    assert upsert_data["title_ar"] == "الأربعون النووية"


def test_upload_upserts_pages_with_content():
    client, table_mocks = _make_mock_client()
    result = _make_result()
    upload_book(result, author_data={}, client=client)

    pages_mock = table_mocks["pages"]
    upsert_data = pages_mock.upsert.call_args.args[0]
    # Should be a list of page rows
    assert isinstance(upsert_data, list)
    assert len(upsert_data) == 1
    assert upsert_data[0]["page_number"] == 1
    assert upsert_data[0]["volume"] == 1
    assert "content_blocks" in upsert_data[0]
    assert upsert_data[0]["content_plain"] == "بسم الله"


def test_upload_upserts_chapters():
    client, table_mocks = _make_mock_client()
    result = _make_result()
    upload_book(result, author_data={}, client=client)

    chapters_mock = table_mocks["chapters"]
    upsert_data = chapters_mock.upsert.call_args.args[0]
    assert upsert_data["title"] == "باب"
    assert upsert_data["level"] == 1
    assert upsert_data["sort_order"] == 1


def test_upload_handles_empty_author_data():
    """When no author metadata, use author_openiti_id as shuhra_ar fallback."""
    client, table_mocks = _make_mock_client()
    result = _make_result()
    upload_book(result, author_data={}, client=client)

    authors_mock = table_mocks["authors"]
    upsert_data = authors_mock.upsert.call_args.args[0]
    assert upsert_data["shuhra_ar"] == "0676Nawawi"  # fallback to openiti_id
