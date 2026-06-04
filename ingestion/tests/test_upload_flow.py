# ingestion/tests/test_upload_flow.py
from unittest.mock import MagicMock

from ingestion.upload_flow import upload_flow_book
from ingestion.flow_format import FlowBook, FlowPage, Annotation
from ingestion.page_slice import OpenTag
from ingestion.models import BookMetadata, Chapter


def _make_book() -> FlowBook:
    meta = BookMetadata(
        openiti_id="0676Nawawi.ArbacunaNawawiyya",
        title_ar="الأربعون النووية",
        author_openiti_id="0676Nawawi",
        genres=["HADITH"],
    )
    page1 = FlowPage(
        page_number=1,
        volume=1,
        tagged="<hadith id=\"h1\">بسم الله",
        open_tags=[],
        text="بسم الله",
        start_offset=0,
    )
    page2 = FlowPage(
        page_number=2,
        volume=1,
        tagged="الرحمن الرحيم</hadith>",
        open_tags=[OpenTag(name="hadith", id="h1")],
        text="الرحمن الرحيم",
        start_offset=8,
    )
    chapter = Chapter(title="باب", level=1, page_number=1, sort_order=1)
    annotations = [
        Annotation(id="h1", label="hadith", start=0, end=21, meta={"number": "1"}),
        Annotation(id="q1", label="quran", start=0, end=8, meta={"sura": 1, "ayah": 1}),
    ]
    return FlowBook(
        metadata=meta,
        pages=[page1, page2],
        chapters=[chapter],
        annotations=annotations,
    )


def _make_mock_client():
    """Mock Supabase client with chaining for authors/books/pages/chapters/annotations."""
    client = MagicMock()

    author_resp = MagicMock()
    author_resp.data = [{"id": "author-uuid-123"}]

    book_resp = MagicMock()
    book_resp.data = [{"id": "book-uuid-456"}]

    page_resp = MagicMock()
    page_resp.data = [{"id": "page-uuid-789", "page_number": 1, "volume": 1}]

    chapter_resp = MagicMock()
    chapter_resp.data = [{"id": "chapter-uuid-abc"}]

    annotation_resp = MagicMock()
    annotation_resp.data = [{"id": "ann-uuid-def"}]

    pages_select_resp = MagicMock()
    pages_select_resp.data = [
        {"id": "page-uuid-1", "page_number": 1, "volume": 1},
        {"id": "page-uuid-2", "page_number": 2, "volume": 1},
    ]

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
        elif name == "annotations":
            mock.upsert.return_value.execute.return_value = annotation_resp

        return mock

    client.table.side_effect = table_side_effect
    return client, table_mocks


def test_upload_calls_tables_in_order():
    client, table_mocks = _make_mock_client()
    upload_flow_book(_make_book(), client)

    names = [c.args[0] for c in client.table.call_args_list]
    assert "authors" in names
    assert "books" in names
    assert "pages" in names
    assert "chapters" in names
    assert "annotations" in names
    assert names.index("authors") < names.index("books") < names.index("pages")


def test_upload_upserts_author():
    client, table_mocks = _make_mock_client()
    upload_flow_book(_make_book(), client,
                     author_data={"shuhra_lat": "al-Nawawi", "death_ah": 676})

    upsert_data = table_mocks["authors"].upsert.call_args.args[0]
    assert upsert_data["openiti_id"] == "0676Nawawi"
    assert upsert_data["shuhra_ar"] == "al-Nawawi"
    assert upsert_data["death_ah"] == 676


def test_upload_handles_empty_author_data():
    client, table_mocks = _make_mock_client()
    upload_flow_book(_make_book(), client, author_data=None)

    upsert_data = table_mocks["authors"].upsert.call_args.args[0]
    # _author_display strips the leading death year from the author id
    assert upsert_data["shuhra_ar"] == "Nawawi"


def test_upload_upserts_book():
    client, table_mocks = _make_mock_client()
    upload_flow_book(_make_book(), client)

    upsert_data = table_mocks["books"].upsert.call_args.args[0]
    assert upsert_data["openiti_id"] == "0676Nawawi.ArbacunaNawawiyya"
    assert upsert_data["title_ar"] == "الأربعون النووية"
    assert upsert_data["total_pages"] == 2
    assert upsert_data["total_volumes"] == 1


def test_upload_pages_carry_tagged_open_tags_and_offset():
    client, table_mocks = _make_mock_client()
    upload_flow_book(_make_book(), client)

    pages_call = table_mocks["pages"].upsert.call_args
    rows = pages_call.args[0]
    assert isinstance(rows, list)
    assert len(rows) == 2
    assert pages_call.kwargs["on_conflict"] == "book_id,volume,page_number"

    r0 = rows[0]
    assert r0["page_number"] == 1
    assert r0["volume"] == 1
    assert r0["tagged"] == "<hadith id=\"h1\">بسم الله"
    assert r0["open_tags"] == []
    assert r0["content_plain"] == "بسم الله"
    assert r0["start_offset"] == 0
    assert "content_hash" in r0

    r1 = rows[1]
    assert r1["tagged"] == "الرحمن الرحيم</hadith>"
    assert r1["open_tags"] == [{"name": "hadith", "id": "h1"}]
    assert r1["start_offset"] == 8


def test_upload_pages_do_not_set_content_blocks():
    client, table_mocks = _make_mock_client()
    upload_flow_book(_make_book(), client)

    rows = table_mocks["pages"].upsert.call_args.args[0]
    for r in rows:
        # content_blocks must be left NULL (flow pages carry `tagged`)
        assert r.get("content_blocks") is None


def test_upload_upserts_chapters():
    client, table_mocks = _make_mock_client()
    upload_flow_book(_make_book(), client)

    upsert_data = table_mocks["chapters"].upsert.call_args.args[0]
    assert upsert_data["title"] == "باب"
    assert upsert_data["level"] == 1
    assert upsert_data["sort_order"] == 1
    # linked to the page row via (volume=1, page_number=1)
    assert upsert_data["page_id"] == "page-uuid-1"


def test_upload_writes_annotations():
    client, table_mocks = _make_mock_client()
    stats = upload_flow_book(_make_book(), client)

    ann_call = table_mocks["annotations"].upsert.call_args
    rows = ann_call.args[0]
    assert ann_call.kwargs["on_conflict"] == "book_id,tag_id"
    assert len(rows) == 2

    r0 = rows[0]
    assert r0["tag_id"] == "h1"
    assert r0["label"] == "hadith"
    assert r0["start_offset"] == 0
    assert r0["end_offset"] == 21
    assert r0["meta"] == {"number": "1"}
    assert r0["book_id"] == "book-uuid-456"

    assert stats["annotations"] == 2
    assert stats["pages"] == 2
    assert stats["chapters"] == 1
