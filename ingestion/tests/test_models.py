from ingestion.models import Token, Block, Page, Chapter, BookMetadata, ParseResult


def test_token_creation():
    t = Token(id="p1_b0_w0", text="حدثنا")
    assert t.id == "p1_b0_w0"
    assert t.text == "حدثنا"


def test_block_with_tokens():
    tokens = [Token(id="p1_b0_w0", text="حدثنا"), Token(id="p1_b0_w1", text="عبد")]
    b = Block(key="b0", type="isnad", tokens=tokens)
    assert b.type == "isnad"
    assert len(b.tokens) == 2
    assert b.hemistichs == []
    assert b.metadata is None


def test_poetry_block_with_hemistichs():
    h1 = [Token(id="p1_b0_w0", text="قفا"), Token(id="p1_b0_w1", text="نبك")]
    h2 = [Token(id="p1_b0_w2", text="بسقط"), Token(id="p1_b0_w3", text="اللوى")]
    b = Block(key="b0", type="poetry", tokens=[], hemistichs=[[h1, h2]])
    assert len(b.hemistichs) == 1
    assert len(b.hemistichs[0]) == 2


def test_page_content_plain_and_hash():
    tokens = [Token(id="p1_b0_w0", text="بسم"), Token(id="p1_b0_w1", text="الله")]
    b = Block(key="b0", type="prose", tokens=tokens)
    p = Page(page_number=1, volume=1, content_blocks=[b])
    assert p.content_plain == "بسم الله"
    assert len(p.content_hash) == 64  # SHA-256 hex


def test_page_content_plain_includes_poetry():
    h1 = [Token(id="p1_b0_w0", text="قفا"), Token(id="p1_b0_w1", text="نبك")]
    h2 = [Token(id="p1_b0_w2", text="بسقط")]
    b = Block(key="b0", type="poetry", hemistichs=[[h1, h2]])
    p = Page(page_number=1, volume=1, content_blocks=[b])
    assert p.content_plain == "قفا نبك بسقط"


def test_page_empty():
    p = Page(page_number=1, volume=1, content_blocks=[])
    assert p.content_plain == ""
    assert len(p.content_hash) == 64


def test_chapter_defaults():
    c = Chapter(title="باب النية", level=1, page_number=42, sort_order=1)
    assert c.parent_index is None


def test_book_metadata_defaults():
    meta = BookMetadata(
        openiti_id="0676Nawawi.ArbacunaNawawiyya",
        title_ar="الأربعون النووية",
        author_openiti_id="0676Nawawi",
    )
    assert meta.language == "ara"
    assert meta.genres == []
    assert meta.word_count is None


def test_parse_result():
    meta = BookMetadata(
        openiti_id="0676Nawawi.ArbacunaNawawiyya",
        title_ar="الأربعون النووية",
        author_openiti_id="0676Nawawi",
        genres=["HADITH"],
    )
    result = ParseResult(metadata=meta, pages=[], chapters=[])
    assert result.metadata.language == "ara"
    assert len(result.pages) == 0
