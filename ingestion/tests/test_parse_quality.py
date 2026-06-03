"""Ingestion-quality fixes found during real OpenITI ingestion:

- ellipsis-separated verse detection (Alfiyya-style "hemistich1 ... hemistich2")
- ordinal-only "### | N -" headings are item numbers, not chapters (Bulugh-style)
"""
from pathlib import Path

from ingestion.parse import parse_file, _split_ellipsis_hemistichs


def _make_book(tmp_path: Path, lines: list[str]) -> Path:
    src = tmp_path / "quality.mARkdown"
    header = (
        "######OpenITI#\n"
        "#META# 020.BookTITLE\t:: اختبار\n"
        "#META# 00#VERS#LENGTH###\t:: 5\n"
        "#META#Header#End#\n"
        "# PageV01P001\n"
    )
    src.write_text(header + "\n".join(lines) + "\n", encoding="utf-8")
    return src


# ---------------------------------------------------------------------------
# _split_ellipsis_hemistichs (pure helper)
# ---------------------------------------------------------------------------

def test_split_balanced_bayt():
    assert _split_ellipsis_hemistichs("قال محمد هو ابن مالك ... أحمد ربي الله خير مالك") == [
        "قال محمد هو ابن مالك",
        "أحمد ربي الله خير مالك",
    ]


def test_split_rejects_attached_dots():
    # Dots glued to a word are an elision, not a standalone separator.
    assert _split_ellipsis_hemistichs("هذا كلام عادي ينتهي بنقاط متصلة...") is None


def test_split_rejects_short_side():
    # Right side has < 2 words → not a hemistich pair.
    assert _split_ellipsis_hemistichs("كلمات كثيرة جدا في هذا الموضع ... إلخ") is None


def test_split_rejects_lopsided():
    # Both sides ≥ 2 words but badly unbalanced (ratio < 0.4) → prose elision.
    assert _split_ellipsis_hemistichs(
        "فصل في بيان حكم هذه المسألة عند جمهور أهل العلم ... قولان مشهوران"
    ) is None


def test_split_rejects_two_separators():
    assert _split_ellipsis_hemistichs("ألف باء جيم ... دال هاء واو ... زاي حاء طاء") is None


# ---------------------------------------------------------------------------
# Through parse_file — ellipsis poetry
# ---------------------------------------------------------------------------

def test_ellipsis_verse_is_poetry_block(tmp_path):
    src = _make_book(tmp_path, ["# قال محمد هو ابن مالك ... أحمد ربي الله خير مالك"])
    page = parse_file(src, "0100Test.AlfiyyaLike").pages[0]
    poetry = [b for b in page.content_blocks if b.type == "poetry"]
    assert len(poetry) == 1
    verse = poetry[0].hemistichs[0]
    assert len(verse) == 2
    assert "محمد" in [t.text for t in verse[0]]
    assert "أحمد" in [t.text for t in verse[1]]
    # The ellipsis token is consumed, not kept as a word.
    allt = [t.text for h in verse for t in h]
    assert "..." not in allt and "…" not in allt


def test_prose_with_ellipsis_stays_prose(tmp_path):
    src = _make_book(tmp_path, ["# كلمات كثيرة جدا في هذا الموضع ... إلخ"])
    page = parse_file(src, "0100Test.ProseEllipsis").pages[0]
    assert [b for b in page.content_blocks if b.type == "poetry"] == []
    assert any(b.type == "prose" for b in page.content_blocks)


# ---------------------------------------------------------------------------
# Through parse_file — ordinal-only headings
# ---------------------------------------------------------------------------

def test_ordinal_only_heading_is_item_number_not_chapter(tmp_path):
    src = _make_book(tmp_path, [
        "### | كتاب الطهارة",
        "### | 1 - ",
        "# عن أبي هريرة قال قال رسول الله هو الطهور ماؤه الحل ميتته",
    ])
    result = parse_file(src, "0100Test.Numbered")
    page = result.pages[0]
    headings = [b for b in page.content_blocks if b.type == "heading"]
    assert len(headings) == 1
    assert "الطهارة" in " ".join(t.text for t in headings[0].tokens)
    assert len(result.chapters) == 1  # only the titled heading is a chapter
    prose = [b for b in page.content_blocks if b.type == "prose"]
    assert prose and prose[0].number == "1"  # ordinal attached to next block


def test_numbered_heading_with_title_stays_chapter(tmp_path):
    src = _make_book(tmp_path, ["### | 1 - كتاب الطهارة", "# نص هنا"])
    result = parse_file(src, "0100Test.NumTitle")
    headings = [b for b in result.pages[0].content_blocks if b.type == "heading"]
    assert len(headings) == 1
    assert len(result.chapters) == 1


def test_sheet_reference_heading_is_dropped(tmp_path):
    # "### | [ص: 6]" is editorial print-pagination, not a chapter.
    src = _make_book(tmp_path, [
        "### | كتاب الطهارة",
        "### | [ص: 6]",
        "# نص الحديث هنا",
    ])
    result = parse_file(src, "0100Test.SheetRef")
    page = result.pages[0]
    titles = [" ".join(t.text for t in b.tokens) for b in page.content_blocks if b.type == "heading"]
    assert titles == ["كتاب الطهارة"]      # sheet ref produced no heading
    assert len(result.chapters) == 1
    # The prose content is still present.
    assert any(b.type == "prose" for b in page.content_blocks)


def test_punctuation_prefixed_heading_becomes_prose(tmp_path):
    # "### | : «...»" and "### | «...»" are mistagged hadith fragments, not
    # chapters: preserve the text as prose, keep it out of the chapter list.
    src = _make_book(tmp_path, [
        "### | كتاب الطهارة",
        "### | : وعنه قال نهى رسول الله عن كذا",
        "### | «المؤذن أملك بالأذان والإمام أملك بالإقامة»",
    ])
    result = parse_file(src, "0100Test.Mistagged")
    page = result.pages[0]
    heading_titles = [" ".join(t.text for t in b.tokens) for b in page.content_blocks if b.type == "heading"]
    assert heading_titles == ["كتاب الطهارة"]   # only the real chapter
    assert len(result.chapters) == 1
    prose = [b for b in page.content_blocks if b.type == "prose"]
    assert len(prose) == 2                       # both fragments preserved
    # The leading ":" is stripped from the colon-fragment.
    assert prose[0].tokens[0].text == "وعنه"
