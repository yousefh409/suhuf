import unicodedata
from ingestion.tashkeel import has_diacritics, diacritize_blocks
from ingestion.models import Token, Block, Page

ARABIC_DIACRITICS = set("\u064B\u064C\u064D\u064E\u064F\u0650\u0651\u0652")

def test_has_diacritics_true():
    assert has_diacritics("حَدَّثَنَا") is True

def test_has_diacritics_false():
    assert has_diacritics("حدثنا") is False

def test_has_diacritics_partial():
    # Ratio below threshold -> not considered diacritized
    assert has_diacritics("حَدثنا عبد الله") is False

def test_has_diacritics_empty():
    assert has_diacritics("") is False

def test_diacritize_blocks_skips_already_vocalized():
    """Blocks with sufficient diacritics should be left unchanged."""
    vocalized = "حَدَّثَنَا عَبْدُ اللَّهِ"
    tokens = [Token(id=f"p1_b0_w{i}", text=w) for i, w in enumerate(vocalized.split())]
    block = Block(key="b0", type="prose", tokens=tokens)
    page = Page(page_number=1, volume=1, content_blocks=[block])

    # Use None engine (should not be called since block is already vocalized)
    result = diacritize_blocks([page], engine=None)
    assert result[0].content_blocks[0].tokens[0].text == "حَدَّثَنَا"

def test_diacritize_blocks_processes_unvocalized():
    """Unvocalized blocks should be sent to the engine."""
    tokens = [Token(id="p1_b0_w0", text="حدثنا"), Token(id="p1_b0_w1", text="عبد")]
    block = Block(key="b0", type="prose", tokens=tokens)
    page = Page(page_number=1, volume=1, content_blocks=[block])

    class MockEngine:
        def diacritize(self, text: str) -> str:
            return "حَدَّثَنَا عَبْدُ"

    result = diacritize_blocks([page], engine=MockEngine())
    assert any(
        c in ARABIC_DIACRITICS
        for c in result[0].content_blocks[0].tokens[0].text
    )

def test_diacritize_blocks_handles_token_count_mismatch():
    """If engine returns different word count, keep original text."""
    tokens = [Token(id="p1_b0_w0", text="حدثنا"), Token(id="p1_b0_w1", text="عبد")]
    block = Block(key="b0", type="prose", tokens=tokens)
    page = Page(page_number=1, volume=1, content_blocks=[block])

    class BadEngine:
        def diacritize(self, text: str) -> str:
            return "حَدَّثَنَا"  # Only 1 word instead of 2

    result = diacritize_blocks([page], engine=BadEngine())
    # Should keep original since count mismatched
    assert result[0].content_blocks[0].tokens[0].text == "حدثنا"

def test_diacritize_blocks_poetry():
    """Poetry blocks should have hemistichs diacritized."""
    h1 = [Token(id="p1_b0_w0", text="قفا"), Token(id="p1_b0_w1", text="نبك")]
    h2 = [Token(id="p1_b0_w2", text="من"), Token(id="p1_b0_w3", text="ذكرى")]
    block = Block(key="b0", type="poetry", hemistichs=[[h1, h2]])
    page = Page(page_number=1, volume=1, content_blocks=[block])

    class MockEngine:
        def diacritize(self, text: str) -> str:
            return "قِفَا نَبْكِ مِنْ ذِكْرَى"

    result = diacritize_blocks([page], engine=MockEngine())
    assert result[0].content_blocks[0].hemistichs[0][0][0].text == "قِفَا"

def test_diacritize_blocks_engine_exception():
    """If engine raises, keep original text."""
    tokens = [Token(id="p1_b0_w0", text="حدثنا")]
    block = Block(key="b0", type="prose", tokens=tokens)
    page = Page(page_number=1, volume=1, content_blocks=[block])

    class FailingEngine:
        def diacritize(self, text: str) -> str:
            raise RuntimeError("Model crashed")

    result = diacritize_blocks([page], engine=FailingEngine())
    assert result[0].content_blocks[0].tokens[0].text == "حدثنا"

def test_diacritize_blocks_preserves_token_ids():
    """Token IDs must be preserved after diacritization."""
    tokens = [Token(id="p5_b2_w0", text="حدثنا"), Token(id="p5_b2_w1", text="عبد")]
    block = Block(key="b2", type="isnad", tokens=tokens)
    page = Page(page_number=5, volume=1, content_blocks=[block])

    class MockEngine:
        def diacritize(self, text: str) -> str:
            return "حَدَّثَنَا عَبْدُ"

    result = diacritize_blocks([page], engine=MockEngine())
    assert result[0].content_blocks[0].tokens[0].id == "p5_b2_w0"
    assert result[0].content_blocks[0].tokens[1].id == "p5_b2_w1"

def test_content_plain_updated_after_diacritize():
    """content_plain should reflect diacritized text since it's a computed field."""
    tokens = [Token(id="p1_b0_w0", text="حدثنا")]
    block = Block(key="b0", type="prose", tokens=tokens)
    page = Page(page_number=1, volume=1, content_blocks=[block])

    class MockEngine:
        def diacritize(self, text: str) -> str:
            return "حَدَّثَنَا"

    result = diacritize_blocks([page], engine=MockEngine())
    assert "حَدَّثَنَا" in result[0].content_plain
