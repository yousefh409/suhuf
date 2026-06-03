"""Tests for inline-vs-block hadith parsing (issue #14)."""
from pathlib import Path

from ingestion.parse import parse_file


def _write(tmp_path, body: str) -> Path:
    src = tmp_path / "hadith.mARkdown"
    src.write_text(
        "######OpenITI#\n"
        "#META# 020.BookTITLE\t:: اختبار\n"
        "#META# 00#VERS#LENGTH###\t:: 5\n"
        "#META#Header#End#\n"
        "# PageV01P001\n"
        + body,
        encoding="utf-8",
    )
    return src


def _spans_by_label(block):
    return {s.label: s for s in block.spans}


def test_inline_matn_is_one_block_with_isnad_and_matn_spans(tmp_path):
    # $RWY$ isnad @MATN@ matn — all on one source line.
    src = _write(tmp_path, "# $RWY$ حدثنا عبد الله @MATN@ إنما الأعمال بالنيات\n")
    result = parse_file(src, "0100Test.HadithBook")
    blocks = result.pages[0].content_blocks

    # One block, not separate isnad/matn blocks.
    assert len(blocks) == 1
    block = blocks[0]
    assert block.type == "prose"

    # The @MATN@ marker is not a token.
    assert all("@MATN@" not in t.text for t in block.tokens)
    assert [t.text for t in block.tokens] == [
        "حدثنا", "عبد", "الله", "إنما", "الأعمال", "بالنيات",
    ]

    spans = _spans_by_label(block)
    assert "isnad" in spans and "matn" in spans

    texts = {t.id: t.text for t in block.tokens}
    # isnad span covers "حدثنا عبد الله"
    assert texts[spans["isnad"].start_token_id] == "حدثنا"
    assert texts[spans["isnad"].end_token_id] == "الله"
    # matn span covers "إنما الأعمال بالنيات"
    assert texts[spans["matn"].start_token_id] == "إنما"
    assert texts[spans["matn"].end_token_id] == "بالنيات"


def test_inline_matn_preserves_item_number(tmp_path):
    src = _write(tmp_path, "# $RWY$ ١ - حدثنا عبد الله @MATN@ إنما الأعمال\n")
    result = parse_file(src, "0100Test.HadithBook")
    block = result.pages[0].content_blocks[0]
    assert block.number == "١"
    assert all("@MATN@" not in t.text for t in block.tokens)
    assert "حدثنا" in [t.text for t in block.tokens]


def test_inline_takhrij_keyword_becomes_takhrij_span(tmp_path):
    src = _write(
        tmp_path,
        "# $RWY$ حدثنا فلان @MATN@ إنما الأعمال بالنيات رواه البخاري ومسلم\n",
    )
    result = parse_file(src, "0100Test.HadithBook")
    block = result.pages[0].content_blocks[0]
    spans = _spans_by_label(block)
    assert {"isnad", "matn", "takhrij"} <= set(spans)
    texts = {t.id: t.text for t in block.tokens}
    # matn ends before the takhrij keyword …
    assert texts[spans["matn"].end_token_id] == "بالنيات"
    # … and takhrij runs from "رواه" to the end.
    assert texts[spans["takhrij"].start_token_id] == "رواه"
    assert texts[spans["takhrij"].end_token_id] == "ومسلم"


def test_inline_embedded_ayah_keeps_quran_span(tmp_path):
    src = _write(
        tmp_path,
        "# $RWY$ حدثنا فلان @MATN@ قال تعالى {إنما الأعمال بالنيات} [البقرة: 2]\n",
    )
    result = parse_file(src, "0100Test.HadithBook")
    block = result.pages[0].content_blocks[0]
    spans = _spans_by_label(block)
    assert "isnad" in spans and "matn" in spans and "quran" in spans
    # Braces stripped from the rendered tokens.
    assert all("{" not in t.text and "}" not in t.text for t in block.tokens)
    # The quran span carries the citation-derived ref.
    quran = [s for s in block.spans if s.label == "quran"]
    assert len(quran) == 1 and quran[0].ref == "2:2"


def test_separate_line_matn_stays_two_blocks(tmp_path):
    # $RWY$ on one line, @MATN@ on a later line → separate isnad + matn blocks.
    src = _write(
        tmp_path,
        "# $RWY$ حدثنا عبد الله عن نافع\n"
        "# @MATN@ إنما الأعمال بالنيات\n",
    )
    result = parse_file(src, "0100Test.HadithBook")
    types = [b.type for b in result.pages[0].content_blocks]
    assert types == ["isnad", "matn"]
    # No inline isnad/matn spans in the separate-line shape.
    for b in result.pages[0].content_blocks:
        assert all(s.label not in ("isnad", "matn") for s in b.spans)
