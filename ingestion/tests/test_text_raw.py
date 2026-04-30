from ingestion.models import Token, Block, Page
from ingestion.tashkeel import diacritize_blocks


def test_token_text_raw_defaults_to_none():
    t = Token(id="p1_b0_w0", text="حدثنا")
    assert t.text_raw is None


def test_token_text_raw_set_explicitly():
    t = Token(id="p1_b0_w0", text="حَدَّثَنَا", text_raw="حدثنا")
    assert t.text_raw == "حدثنا"


def test_diacritize_populates_text_raw_when_changed():
    tokens = [
        Token(id="p1_b0_w0", text="حدثنا"),
        Token(id="p1_b0_w1", text="عبد"),
    ]
    block = Block(key="b0", type="prose", tokens=tokens)
    page = Page(page_number=1, volume=1, content_blocks=[block])

    class MockEngine:
        def diacritize(self, text: str) -> str:
            return "حَدَّثَنَا عَبْدُ"

    result = diacritize_blocks([page], engine=MockEngine())
    out = result[0].content_blocks[0].tokens
    assert out[0].text == "حَدَّثَنَا"
    assert out[0].text_raw == "حدثنا"
    assert out[1].text == "عَبْدُ"
    assert out[1].text_raw == "عبد"


def test_diacritize_does_not_set_text_raw_when_unchanged():
    tokens = [Token(id="p1_b0_w0", text="عبد")]
    block = Block(key="b0", type="prose", tokens=tokens)
    page = Page(page_number=1, volume=1, content_blocks=[block])

    class IdentityEngine:
        def diacritize(self, text: str) -> str:
            return text

    result = diacritize_blocks([page], engine=IdentityEngine())
    assert result[0].content_blocks[0].tokens[0].text_raw is None


def test_diacritize_populates_text_raw_in_poetry():
    h1 = [Token(id="p1_b0_w0", text="قفا"), Token(id="p1_b0_w1", text="نبك")]
    block = Block(key="b0", type="poetry", hemistichs=[[h1]])
    page = Page(page_number=1, volume=1, content_blocks=[block])

    class MockEngine:
        def diacritize(self, text: str) -> str:
            return "قِفَا نَبْكِ"

    result = diacritize_blocks([page], engine=MockEngine())
    out_h = result[0].content_blocks[0].hemistichs[0][0]
    assert out_h[0].text == "قِفَا"
    assert out_h[0].text_raw == "قفا"
    assert out_h[1].text == "نَبْكِ"
    assert out_h[1].text_raw == "نبك"
