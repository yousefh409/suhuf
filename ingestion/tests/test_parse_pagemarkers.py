"""Tests for embedded inline page marker handling in parse.py.

These tests verify that page markers embedded within content lines
(not already standalone) are correctly expanded into separate lines,
producing the same page-splitting behavior as standalone markers.
"""
from pathlib import Path
from ingestion.parse import parse_file


def _make_book(tmp_path: Path, body_lines: list[str]) -> Path:
    """Helper: write a minimal OpenITI mARkdown file with the given body lines."""
    src = tmp_path / "book.mARkdown"
    header = (
        "######OpenITI#\n"
        "#META# 020.BookTITLE\t:: كتاب اختبار\n"
        "#META# 00#VERS#LENGTH###\t:: 10\n"
        "#META#Header#End#\n"
    )
    src.write_text(header + "\n".join(body_lines) + "\n", encoding="utf-8")
    return src


def test_embedded_marker_in_continuation_splits_pages(tmp_path):
    """A continuation (~~) line ending with an embedded PageVxxPyyy marker
    produces separate pages, with content before the marker on page 1 and
    content after landing on page 2."""
    src = _make_book(tmp_path, [
        "# PageV01P001",
        "# هذا النص الأول",
        "~~استمرار النص قبل العلامة PageV01P002",
        "# النص بعد العلامة",
    ])
    result = parse_file(src, "0100Test.EmbeddedCont")

    page_numbers = [p.page_number for p in result.pages]
    assert 1 in page_numbers, f"Expected page 1, got pages: {page_numbers}"
    assert 2 in page_numbers, f"Expected page 2, got pages: {page_numbers}"

    page1 = next(p for p in result.pages if p.page_number == 1)
    page2 = next(p for p in result.pages if p.page_number == 2)

    all_tokens_p1 = [t.text for b in page1.content_blocks for t in b.tokens]
    all_tokens_p2 = [t.text for b in page2.content_blocks for t in b.tokens]

    # "استمرار" is before the marker, so it should land on page 1
    assert "استمرار" in all_tokens_p1, f"Before-text token not on page 1. Page 1 tokens: {all_tokens_p1}"
    # "النص" (from "النص بعد العلامة") should be on page 2
    assert "بعد" in all_tokens_p2, f"After-text not on page 2. Page 2 tokens: {all_tokens_p2}"

    # No block token should contain the substring "PageV"
    for page in result.pages:
        for block in page.content_blocks:
            for token in block.tokens:
                assert "PageV" not in token.text, f"PageV found in token: {token.text!r}"


def test_embedded_marker_mid_line_text_before_and_after(tmp_path):
    """A '# ' paragraph line with text on both sides of an embedded marker:
    before-text lands on the prior page, after-text lands on the new page."""
    src = _make_book(tmp_path, [
        "# PageV02P009",
        "# نص قبل PageV02P010 نص بعد",
    ])
    result = parse_file(src, "0100Test.MidLine")

    page_numbers = [p.page_number for p in result.pages]
    assert 9 in page_numbers, f"Expected page 9, got: {page_numbers}"
    assert 10 in page_numbers, f"Expected page 10, got: {page_numbers}"

    page9 = next(p for p in result.pages if p.page_number == 9)
    page10 = next(p for p in result.pages if p.page_number == 10)

    tokens_p9 = [t.text for b in page9.content_blocks for t in b.tokens]
    tokens_p10 = [t.text for b in page10.content_blocks for t in b.tokens]

    assert "قبل" in tokens_p9, f"Before-text not on page 9. Tokens: {tokens_p9}"
    assert "بعد" in tokens_p10, f"After-text not on page 10. Tokens: {tokens_p10}"

    # "PageV02P010" must NOT appear as a token in any block
    for page in result.pages:
        for block in page.content_blocks:
            for token in block.tokens:
                assert "PageV" not in token.text, f"PageV found in token: {token.text!r}"


def test_standalone_marker_still_works(tmp_path):
    """Regression: standalone page markers on their own line continue to work
    exactly as before."""
    src = _make_book(tmp_path, [
        "# PageV01P001",
        "# محتوى الصفحة الأولى",
        "# PageV01P002",
        "# محتوى الصفحة الثانية",
    ])
    result = parse_file(src, "0100Test.Standalone")

    page_numbers = [p.page_number for p in result.pages]
    assert page_numbers == [1, 2], f"Expected pages [1, 2], got: {page_numbers}"

    tokens_p1 = [t.text for b in result.pages[0].content_blocks for t in b.tokens]
    tokens_p2 = [t.text for b in result.pages[1].content_blocks for t in b.tokens]
    assert "الأولى" in tokens_p1
    assert "الثانية" in tokens_p2

    for page in result.pages:
        for block in page.content_blocks:
            for token in block.tokens:
                assert "PageV" not in token.text


def test_pagev00p000_inline_ignored(tmp_path):
    """An embedded PageV00P000 null marker must not create a spurious page,
    and any text around it should be handled without crashing."""
    src = _make_book(tmp_path, [
        "# PageV01P001",
        "# هذا النص PageV00P000 وهذا أيضاً",
        "# PageV01P002",
        "# محتوى آخر",
    ])
    result = parse_file(src, "0100Test.NullMarker")

    page_numbers = [p.page_number for p in result.pages]
    assert 0 not in page_numbers, f"Spurious page 0 created: {page_numbers}"

    # No block token text should contain PageV
    for page in result.pages:
        for block in page.content_blocks:
            for token in block.tokens:
                assert "PageV" not in token.text, f"PageV found in token: {token.text!r}"
