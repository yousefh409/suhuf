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


def test_find_marker_action_verb():
    # action-verb introducer "نهى رسول الله" (prophetic prohibition report).
    # Normalize the input as real callers do (نهى → نهي).
    norm = [_norm(w) for w in ["عن", "ابن", "عمر", "نهى", "رسول", "الله"]]
    assert _find_prophetic_marker(norm) == 3


def test_find_marker_kana_nabi():
    assert _find_prophetic_marker(["كان", "النبي", "اذا"]) == 0


def test_find_marker_allah_omitted_variant():
    # "قال رسول [-] صلي الله …" — الله omitted after رسول; the empty string is the
    # normalized dash; the NORMALIZED blessing صلي (folded from صلى) confirms the
    # prophetic subject. Inputs to _find_prophetic_marker are already normalized.
    assert _find_prophetic_marker(["قال", "قال", "رسول", "", "صلي", "الله"]) == 1


def test_find_marker_rasul_fulan_is_not_prophetic():
    # "رسول فلان" (a generic messenger) must NOT be treated as the Prophet.
    assert _find_prophetic_marker(["ارسل", "رسول", "فلان", "الى"]) is None


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


def test_allah_omitted_variant_through_parse(tmp_path):
    # End-to-end through _norm: raw "صلى" (with الله omitted after رسول) must be
    # detected — this exercises the ى→ي fold that a pure-norm-list test misses.
    body = "# وعن ابي امامة رضي الله عنه قال قال رسول صلى الله عليه وسلم اتقوا الله\n"
    block = parse_file(_make_book(tmp_path, body), "0100Test.Variant").pages[0].content_blocks[0]
    detect_hadith_structure(_one(block))
    assert "matn" in _spans(block)


def test_quote_fallback_possessive_nabi(tmp_path):
    # Possessive "قدح النبي" gives no introducer+subject marker, but a
    # transmission opener (وعن) + «…» matn fires the low-confidence fallback.
    body = ("# وعن انس بن مالك رضي الله عنه ان قدح النبي صلى الله عليه وسلم انكسر "
            "فجعل مكانه «سلسلة من فضة» رواه البخاري\n")
    block = parse_file(_make_book(tmp_path, body), "0100Test.QFallback").pages[0].content_blocks[0]
    detect_hadith_structure(_one(block))
    sp = _spans(block)
    assert "matn" in sp and "takhrij" in sp
    texts = {t.id: t.text for t in block.tokens}
    assert "«" in texts[sp["matn"].start_token_id] and "»" in texts[sp["matn"].end_token_id]
    assert sp["matn"].confidence == LOW_CONF


def test_narrator_qal_fallback(tmp_path):
    # Companion action report, no prophetic subject, no «…»: "عن X أن Y …".
    body = "# وعن حمران ان عثمان رضي الله عنه دعا بوضوء فغسل كفيه ثلاث مرات ثم مضمض\n"
    block = parse_file(_make_book(tmp_path, body), "0100Test.NQ").pages[0].content_blocks[0]
    detect_hadith_structure(_one(block))
    sp = _spans(block)
    assert "isnad" in sp and "matn" in sp
    texts = {t.id: t.text for t in block.tokens}
    assert texts[sp["isnad"].start_token_id] == "وعن"   # isnad opens the block
    assert sp["matn"].confidence == LOW_CONF


def test_narrator_qal_requires_transmission_opener(tmp_path):
    # A non-hadith block that merely contains قال must not fire (no isnad opener).
    body = "# هذه مسالة فقهية قال فيها الجمهور بالجواز وخالف بعضهم\n"
    block = parse_file(_make_book(tmp_path, body), "0100Test.NotHadith").pages[0].content_blocks[0]
    detect_hadith_structure(_one(block))
    assert all(s.label not in ("isnad", "matn", "takhrij") for s in block.spans)


def test_crossref_quote_variant(tmp_path):
    # "وللبيهقي: «…»" — cross-collection variant: opener=takhrij, quote=matn.
    body = "# وللبيهقي «الماء طاهر الا ان تغير ريحه او طعمه او لونه بنجاسة»\n"
    block = parse_file(_make_book(tmp_path, body), "0100Test.CR").pages[0].content_blocks[0]
    detect_hadith_structure(_one(block))
    sp = _spans(block)
    assert "matn" in sp and "takhrij" in sp and "isnad" not in sp
    texts = {t.id: t.text for t in block.tokens}
    assert "«" in texts[sp["matn"].start_token_id]
    assert sp["takhrij"].start_token_id == block.tokens[0].id   # opener is the takhrij


def test_crossref_report_variant_splits_to_matn(tmp_path):
    # Fix #1: "ولمسلم: <report>" (no «…») → opener=takhrij, the report=matn.
    body = "# ولمسلم: لقد كنت افرك المني من ثوب رسول الله صلى الله عليه وسلم فيصلي فيه\n"
    block = parse_file(_make_book(tmp_path, body), "0100Test.RV").pages[0].content_blocks[0]
    detect_hadith_structure(_one(block))
    sp = _spans(block)
    assert "matn" in sp and "takhrij" in sp        # not takhrij-only
    texts = {t.id: t.text for t in block.tokens}
    assert "ولمسلم" in texts[sp["takhrij"].start_token_id]
    assert texts[sp["matn"].start_token_id] == "لقد"


def test_crossref_pure_note_stays_takhrij(tmp_path):
    # A note whose post-colon content is just attribution stays takhrij-only.
    body = "# وللترمذي: عن سعيد بن زيد رضي الله عنه\n"
    block = parse_file(_make_book(tmp_path, body), "0100Test.PN").pages[0].content_blocks[0]
    detect_hadith_structure(_one(block))
    sp = _spans(block)
    assert "takhrij" in sp and "matn" not in sp


def test_takhrij_capped_before_following_variant(tmp_path):
    # Fix #2: takhrij stops at the sentence end, not swallowing a trailing variant.
    body = ("# وعن ابي هريرة رضي الله عنه قال قال رسول الله صلى الله عليه وسلم «انما الاعمال» "
            "رواه البخاري. ولمسلم نحوه\n")
    block = parse_file(_make_book(tmp_path, body), "0100Test.Cap").pages[0].content_blocks[0]
    detect_hadith_structure(_one(block))
    sp = _spans(block)
    texts = {t.id: t.text for t in block.tokens}
    assert texts[sp["takhrij"].end_token_id].rstrip().endswith(".")   # ends at "البخاري."
    ids = [t.id for t in block.tokens]
    i0, i1 = ids.index(sp["takhrij"].start_token_id), ids.index(sp["takhrij"].end_token_id)
    takhrij_text = " ".join(block.tokens[i].text for i in range(i0, i1 + 1))
    assert "ولمسلم" not in takhrij_text


def test_crossref_source_note_is_takhrij(tmp_path):
    # "وأصله في الصحيحين …" — a pure source/grading note → whole block = takhrij.
    body = "# وأصله في الصحيحين من حديث عبد الله بن زيد بن عاصم المازني\n"
    block = parse_file(_make_book(tmp_path, body), "0100Test.Note").pages[0].content_blocks[0]
    detect_hadith_structure(_one(block))
    sp = _spans(block)
    assert "takhrij" in sp and "matn" not in sp and "isnad" not in sp


def test_quote_without_transmission_no_fallback(tmp_path):
    # A «…» with no transmission opener (a fiqh definition) must NOT fire.
    body = "# الماء «الطهور» هو الباقي على اصل خلقته وهذا قول الجمهور\n"
    block = parse_file(_make_book(tmp_path, body), "0100Test.NoFall").pages[0].content_blocks[0]
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


def test_full_parse_then_detect_adds_structure(tmp_path):
    # Two hadith on separate lines; both should get matn spans after detect.
    body = (
        "# وعن ابي هريرة قال قال رسول الله صلى الله عليه وسلم «انما الاعمال بالنيات» رواه البخاري\n"
        "# وعن عائشة قالت قال رسول الله صلى الله عليه وسلم «من احدث في امرنا» متفق عليه\n"
    )
    result = parse_file(_make_book(tmp_path, body), "0100Test.Two")
    stats = detect_hadith_structure(result)
    assert stats["matn"] == 2 and stats["takhrij"] == 2


from ingestion.hadith import _group_hadith_units, _is_hadith_start, _is_real_chapter
from ingestion.models import Block, Token


def _blk(key, type, text, number=None):
    toks = [Token(id=f"p1_{key}_w{i}", text=w) for i, w in enumerate(text.split())]
    return Block(key=key, type=type, tokens=toks, number=number)


def test_group_absorbs_open_quote_fragment():
    # b3 opens « but never closes; b4 (a heading) closes it → same unit.
    b3 = _blk("b3", "prose", "وعن ابي سعيد قال قال رسول الله «ان", number="2")
    b4 = _blk("b4", "heading", "الماء طهور لا ينجسه شيء».")
    b5 = _blk("b5", "takhrij", "اخرجه الثلاثة")
    units = _group_hadith_units([(1, 0, b3), (1, 1, b4), (1, 2, b5)])
    assert len(units) == 1
    assert [t[2].key for t in units[0]] == ["b3", "b4", "b5"]


def test_real_chapter_heading_ends_unit():
    b1 = _blk("b1", "prose", "وعن انس قال قال رسول الله صلى الله عليه وسلم كذا", number="1")
    chap = _blk("b2", "heading", "كتاب الطهارة")
    b3 = _blk("b3", "prose", "وعن عمر قال قال رسول الله كذا", number="2")
    units = _group_hadith_units([(1, 0, b1), (1, 1, chap), (1, 2, b3)])
    assert len(units) == 2                 # chapter is not absorbed into either
    assert [t[2].key for t in units[0]] == ["b1"]
    assert [t[2].key for t in units[1]] == ["b3"]


def test_real_chapter_vs_fragment_heading():
    assert _is_real_chapter(_blk("b0", "heading", "كتاب الطهارة")) is True
    assert _is_real_chapter(_blk("b0", "heading", "الماء طهور لا ينجسه شيء».")) is False  # ends »
    assert _is_real_chapter(_blk("b0", "prose", "كتاب")) is False                         # not a heading


def test_split_matn_spans_both_blocks(tmp_path):
    # A hadith whose matn quote opens in one block and closes in the next, with
    # the tail pulled into a ### | heading — must produce a matn span in BOTH,
    # the heading re-typed to prose, and dropped from chapters.
    src = tmp_path / "split.mARkdown"
    src.write_text(
        "######OpenITI#\n#META#Header#End#\n# PageV01P001\n"
        "### | 1 - \n"
        "# وعن ابي سعيد الخدري رضي الله عنه قال قال رسول الله صلى الله عليه وسلم «ان\n"
        "### | الماء طهور لا ينجسه شيء».\n"
        "# اخرجه الثلاثة\n",
        encoding="utf-8",
    )
    from ingestion.parse import parse_file
    result = parse_file(src, "0100Test.Split")
    detect_hadith_structure(result)
    blocks = result.pages[0].content_blocks
    matn_blocks = [b for b in blocks if any(s.label == "matn" for s in b.spans)]
    assert len(matn_blocks) == 2                         # matn spans BOTH blocks
    frag = [b for b in blocks if "طهور" in " ".join(t.text for t in b.tokens)][0]
    assert frag.type == "prose"                          # re-typed from heading
    assert all("طهور" not in c.title for c in result.chapters)  # pruned from chapters


def test_single_block_hadith_unchanged(tmp_path):
    # Regression: a self-contained hadith still gets one isnad+matn+takhrij set.
    src = tmp_path / "one.mARkdown"
    src.write_text(
        "######OpenITI#\n#META#Header#End#\n# PageV01P001\n"
        "# وعن ابي هريرة رضي الله عنه قال قال رسول الله صلى الله عليه وسلم «انما الاعمال» رواه البخاري\n",
        encoding="utf-8",
    )
    from ingestion.parse import parse_file
    result = parse_file(src, "0100Test.One")
    detect_hadith_structure(result)
    b = result.pages[0].content_blocks[0]
    labels = {s.label for s in b.spans}
    assert {"isnad", "matn", "takhrij"} <= labels
