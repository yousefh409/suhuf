"""Tests for deterministic hadith-structure detection."""
from pathlib import Path

from ingestion.hadith import _norm, _find_prophetic_marker, detect_hadith_structure, HIGH_CONF, LOW_CONF
from ingestion.parse import parse_file


def test_norm_strips_tashkeel_and_normalizes_variants():
    assert _norm("قَالَ") == "قال"
    assert _norm("النَّبِيِّ") == "النبي"
    assert _norm("أنّ") == "ان"          # hamza-alef → bare alef
    assert _norm("الله:") == "الله"       # punctuation dropped


def test_find_marker_returns_phrase_start():
    norm = ["عن", "ابي", "هريره", "قال", "قال", "رسول", "الله"]
    # the SECOND "قال" starts "قال رسول الله"
    assert _find_prophetic_marker(norm) == 4


def test_find_marker_none_when_absent():
    assert _find_prophetic_marker(["عن", "ابي", "هريره", "قال", "كذا"]) is None


def test_find_marker_an_nabi_variant():
    norm = ["عن", "انس", "عن", "النبي", "انه", "قال"]
    assert _find_prophetic_marker(norm) == 2   # "عن النبي"


def _make_book(tmp_path, body: str) -> Path:
    src = tmp_path / "h.mARkdown"
    src.write_text(
        "######OpenITI#\n#META#Header#End#\n# PageV01P001\n" + body,
        encoding="utf-8",
    )
    return src


def _spans(block):
    return {s.label: s for s in block.spans}


def test_bukhari_shape_full_isnad_no_quote(tmp_path):
    # full isnad, no «…», no takhrij → isnad + matn, boundary at the marker
    body = "# حدثنا عبد الله عن نافع عن ابن عمر قال رسول الله صلى الله عليه وسلم بني الاسلام على خمس\n"
    block = parse_file(_make_book(tmp_path, body), "0100Test.Bukhari").pages[0].content_blocks[0]
    detect_hadith_structure(_one(block))
    sp = _spans(block)
    assert "isnad" in sp and "matn" in sp and "takhrij" not in sp
    texts = {t.id: t.text for t in block.tokens}
    assert texts[sp["isnad"].start_token_id] == "حدثنا"
    assert texts[sp["matn"].start_token_id] == "قال"          # marker is in matn
    assert sp["matn"].confidence == LOW_CONF                   # marker only


def test_bulugh_shape_quote_and_takhrij(tmp_path):
    body = "# وعن ابي هريرة رضي الله عنه قال قال رسول الله صلى الله عليه وسلم «هو الطهور ماؤه» رواه ابو داود\n"
    block = parse_file(_make_book(tmp_path, body), "0100Test.Bulugh").pages[0].content_blocks[0]
    detect_hadith_structure(_one(block))
    sp = _spans(block)
    assert {"isnad", "matn", "takhrij"} <= set(sp)
    texts = {t.id: t.text for t in block.tokens}
    assert texts[sp["takhrij"].start_token_id] == "رواه"
    assert "»" in texts[sp["matn"].end_token_id]               # matn ends at the quote close
    assert sp["matn"].confidence == HIGH_CONF                  # marker + quote + takhrij


def test_negative_fiqh_quote_without_marker_is_not_hadith(tmp_path):
    body = "# الماء «الطهور» هو الباقي على اصل خلقته وهذا مذهب الجمهور\n"
    block = parse_file(_make_book(tmp_path, body), "0100Test.Fiqh").pages[0].content_blocks[0]
    detect_hadith_structure(_one(block))
    assert all(s.label not in ("isnad", "matn", "takhrij") for s in block.spans)


def test_marker_at_start_no_isnad(tmp_path):
    body = "# قال رسول الله صلى الله عليه وسلم انما الاعمال بالنيات\n"
    block = parse_file(_make_book(tmp_path, body), "0100Test.NoIsnad").pages[0].content_blocks[0]
    detect_hadith_structure(_one(block))
    sp = _spans(block)
    assert "isnad" not in sp and "matn" in sp


def _one(block):
    """Wrap a single block in a minimal ParseResult for detect_hadith_structure."""
    from ingestion.models import BookMetadata, Page, ParseResult
    meta = BookMetadata(openiti_id="t.1", title_ar="x", author_openiti_id="a")
    return ParseResult(metadata=meta, pages=[Page(page_number=1, content_blocks=[block])])
