from pathlib import Path
from ingestion.parse import parse_file

FIXTURE = Path(__file__).parent / "fixtures" / "sample.mARkdown"

def test_parse_page_count():
    result = parse_file(FIXTURE, "0100Test.TestBook")
    # Pages: V01P001, V01P002, V01P003. PageV00P000 is skipped.
    assert len(result.pages) == 3

def test_parse_page_numbers():
    result = parse_file(FIXTURE, "0100Test.TestBook")
    assert [p.page_number for p in result.pages] == [1, 2, 3]

def test_parse_volumes():
    result = parse_file(FIXTURE, "0100Test.TestBook")
    assert all(p.volume == 1 for p in result.pages)

def test_parse_heading_block():
    result = parse_file(FIXTURE, "0100Test.TestBook")
    page1 = result.pages[0]
    heading = page1.content_blocks[0]
    assert heading.type == "heading"
    assert heading.tokens[0].text == "باب"
    assert heading.tokens[1].text == "الأول"

def test_parse_prose_with_continuation():
    result = parse_file(FIXTURE, "0100Test.TestBook")
    page1 = result.pages[0]
    # Second block should be prose with continuation joined
    prose = page1.content_blocks[1]
    assert prose.type == "prose"
    texts = [t.text for t in prose.tokens]
    assert "بسم" in texts
    assert "العالمين" in texts  # From continuation line
    assert "رب" in texts

def test_parse_hadith_isnad_matn_split():
    result = parse_file(FIXTURE, "0100Test.TestBook")
    page2 = result.pages[1]
    types = [b.type for b in page2.content_blocks]
    assert "isnad" in types
    assert "matn" in types

def test_parse_isnad_tokens():
    result = parse_file(FIXTURE, "0100Test.TestBook")
    page2 = result.pages[1]
    isnad = [b for b in page2.content_blocks if b.type == "isnad"][0]
    texts = [t.text for t in isnad.tokens]
    assert "حدثنا" in texts
    assert "نافع" in texts  # From continuation

def test_parse_matn_tokens():
    result = parse_file(FIXTURE, "0100Test.TestBook")
    page2 = result.pages[1]
    matn = [b for b in page2.content_blocks if b.type == "matn"][0]
    texts = [t.text for t in matn.tokens]
    assert "الأعمال" in texts
    assert "بالنيات" in texts

def test_parse_poetry_hemistichs():
    result = parse_file(FIXTURE, "0100Test.TestBook")
    page3 = result.pages[2]
    poetry = [b for b in page3.content_blocks if b.type == "poetry"]
    assert len(poetry) == 1
    verse = poetry[0]
    assert len(verse.hemistichs) == 1
    assert len(verse.hemistichs[0]) == 2  # two hemistichs
    h1_texts = [t.text for t in verse.hemistichs[0][0]]
    assert "قفا" in h1_texts
    assert "نبك" in h1_texts
    h2_texts = [t.text for t in verse.hemistichs[0][1]]
    assert "بسقط" in h2_texts

def test_parse_token_id_format():
    result = parse_file(FIXTURE, "0100Test.TestBook")
    page1 = result.pages[0]
    first_token = page1.content_blocks[0].tokens[0]
    assert first_token.id == "p1_b0_w0"

def test_parse_token_ids_are_page_relative():
    """Token IDs use actual page number, not sequential index."""
    result = parse_file(FIXTURE, "0100Test.TestBook")
    page2 = result.pages[1]
    first_block = page2.content_blocks[0]
    assert first_block.tokens[0].id.startswith("p2_b0_w")

def test_parse_chapters():
    result = parse_file(FIXTURE, "0100Test.TestBook")
    assert len(result.chapters) == 2
    assert result.chapters[0].title == "باب الأول"
    assert result.chapters[0].level == 1
    assert result.chapters[0].page_number == 1
    assert result.chapters[1].title == "فصل في الشعر"
    assert result.chapters[1].level == 2
    assert result.chapters[1].page_number == 3

def test_parse_skips_pagev00p000():
    result = parse_file(FIXTURE, "0100Test.TestBook")
    page_numbers = [p.page_number for p in result.pages]
    assert 0 not in page_numbers

def test_parse_prose_after_null_page():
    """Content after PageV00P000 goes to the current page (page 3)."""
    result = parse_file(FIXTURE, "0100Test.TestBook")
    page3 = result.pages[2]
    prose_blocks = [b for b in page3.content_blocks if b.type == "prose"]
    assert len(prose_blocks) >= 1
    texts = [t.text for b in prose_blocks for t in b.tokens]
    assert "عادي" in texts

def test_parse_content_plain_nonempty():
    result = parse_file(FIXTURE, "0100Test.TestBook")
    for page in result.pages:
        assert len(page.content_plain) > 0
        assert len(page.content_hash) == 64

def test_parse_metadata():
    result = parse_file(FIXTURE, "0100Test.TestBook")
    assert result.metadata.title_ar == "كتاب تجريبي"
    assert result.metadata.word_count == 50
