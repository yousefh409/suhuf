"""Tests for inline Quran detection: {ayah} [sura: ayah] within prose."""
from pathlib import Path

from ingestion.parse import parse_file, _extract_inline_quran


def _write(tmp_path, body: str) -> Path:
    src = tmp_path / "quran.mARkdown"
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


# ---------------------------------------------------------------------------
# _extract_inline_quran helper (pure, word-level)
# ---------------------------------------------------------------------------

def test_extract_single_quote_with_citation():
    words = "قال تعالى {لأنذركم به ومن بلغ} [الأنعام: 19] فمن".split()
    cleaned, spans = _extract_inline_quran(words)
    # Braces stripped from the ayah words.
    assert "{لأنذركم" not in cleaned and "لأنذركم" in cleaned
    assert "بلغ}" not in cleaned and "بلغ" in cleaned
    # One quran span with the citation-derived ref.
    assert len(spans) == 1
    start, end, ref = spans[0]
    assert ref == "6:19"
    assert cleaned[start] == "لأنذركم"
    assert cleaned[end] == "بلغ"
    # Citation words are preserved in the prose flow.
    assert "[الأنعام:" in cleaned and "19]" in cleaned


def test_extract_ayah_range_citation():
    words = "{فذرني ومن يكذب} [القلم: 44، 45] الآية".split()
    cleaned, spans = _extract_inline_quran(words)
    assert len(spans) == 1
    assert spans[0][2] == "68:44-45"


def test_extract_brace_without_citation_is_not_quran():
    # No [sura: ayah] citation follows — leave it as ordinary prose, braces kept.
    words = "هذا {نص بين أقواس} عادي".split()
    cleaned, spans = _extract_inline_quran(words)
    assert spans == []
    assert "{نص" in cleaned and "أقواس}" in cleaned


def test_extract_multiple_quotes_in_one_line():
    words = "{ومن يكفر به} [هود: 17] ثم {لا يأتيه الباطل} [فصلت: 42]".split()
    cleaned, spans = _extract_inline_quran(words)
    assert [s[2] for s in spans] == ["11:17", "41:42"]


def test_extract_no_braces_returns_input_unchanged():
    words = "نص عادي بلا قرآن".split()
    cleaned, spans = _extract_inline_quran(words)
    assert cleaned == words
    assert spans == []


# ---------------------------------------------------------------------------
# Through parse_file
# ---------------------------------------------------------------------------

def test_parse_file_emits_quran_span(tmp_path):
    src = _write(tmp_path, "# قال تعالى {لأنذركم به ومن بلغ} [الأنعام: 19]\n")
    result = parse_file(src, "0100Test.QuranBook")
    block = result.pages[0].content_blocks[0]
    quran_spans = [s for s in block.spans if s.label == "quran"]
    assert len(quran_spans) == 1
    span = quran_spans[0]
    assert span.ref == "6:19"
    # The span's start/end token ids must exist in the block and bound the ayah.
    ids = [t.id for t in block.tokens]
    assert span.start_token_id in ids and span.end_token_id in ids
    texts = {t.id: t.text for t in block.tokens}
    assert texts[span.start_token_id] == "لأنذركم"
    assert texts[span.end_token_id] == "بلغ"
    # Braces are gone from the rendered tokens.
    assert all("{" not in t.text and "}" not in t.text for t in block.tokens)


def test_parse_file_brace_without_citation_no_span(tmp_path):
    src = _write(tmp_path, "# هذا {كلام بين أقواس} ليس قرآنا\n")
    result = parse_file(src, "0100Test.QuranBook")
    block = result.pages[0].content_blocks[0]
    assert [s for s in block.spans if s.label == "quran"] == []
