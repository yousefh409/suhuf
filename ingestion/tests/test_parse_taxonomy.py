"""Tests for heading-level propagation and takhrij detection using the taxonomy fixture."""
from pathlib import Path

import pytest

from ingestion.parse import parse_file

FIXTURE = Path(__file__).parent / "fixtures" / "taxonomy_sample.mARkdown"


def _heading_blocks(result):
    blocks = []
    for page in result.pages:
        for block in page.content_blocks:
            if block.type == "heading":
                blocks.append(block)
    return blocks


def _isnad_blocks(result):
    blocks = []
    for page in result.pages:
        for block in page.content_blocks:
            if block.type == "isnad":
                blocks.append(block)
    return blocks


def test_heading_levels():
    result = parse_file(FIXTURE, "0000Sample.Taxonomy")
    headings = _heading_blocks(result)
    assert len(headings) == 2, f"Expected 2 heading blocks, got {len(headings)}"

    level1 = headings[0]
    level2 = headings[1]

    assert level1.level == 1, f"Expected level 1, got {level1.level}"
    assert level2.level == 2, f"Expected level 2, got {level2.level}"


def test_isnad_ordinal_extracted():
    """The leading ordinal '١ - ' must be extracted into block.number,
    not left as tokens."""
    result = parse_file(FIXTURE, "0000Sample.Taxonomy")
    isnads = _isnad_blocks(result)
    assert len(isnads) == 1, f"Expected 1 isnad block, got {len(isnads)}"
    isnad = isnads[0]
    assert isnad.number == "١", f"Expected number='١', got {isnad.number!r}"
    assert isnad.tokens[0].text == "عن", (
        f"Expected first token 'عن', got {isnad.tokens[0].text!r}"
    )


def _quran_blocks(result):
    blocks = []
    for page in result.pages:
        for block in page.content_blocks:
            if block.type == "quran":
                blocks.append(block)
    return blocks


def test_quran_block_detected():
    """A standalone ayah line wrapped in ﴿…﴾ must be classified as quran,
    not prose. The bracket glyphs stay in the token text."""
    result = parse_file(FIXTURE, "0000Sample.Taxonomy")
    quran_blocks = _quran_blocks(result)
    assert len(quran_blocks) >= 1, (
        f"Expected at least 1 quran block, got {len(quran_blocks)}; "
        f"all block types: {[b.type for p in result.pages for b in p.content_blocks]}"
    )
    block = quran_blocks[0]
    # In the fixture the line is stored as U+FD3F … U+FD3E (RTL text order).
    assert block.tokens[0].text.startswith("\uFD3F"), (
        f"First token should start with ﴿ (U+FD3F), got {block.tokens[0].text!r}"
    )
    assert block.tokens[-1].text.endswith("\uFD3E"), (
        f"Last token should end with ﴾ (U+FD3E), got {block.tokens[-1].text!r}"
    )


def _takhrij_blocks(result):
    blocks = []
    for page in result.pages:
        for block in page.content_blocks:
            if block.type == "takhrij":
                blocks.append(block)
    return blocks


def test_takhrij_detected():
    """Line starting with رواه after the matn must be classified as takhrij,
    not prose, and its first token must be the keyword itself."""
    result = parse_file(FIXTURE, "0000Sample.Taxonomy")
    takhrijat = _takhrij_blocks(result)
    assert len(takhrijat) >= 1, (
        f"Expected at least 1 takhrij block, got {len(takhrijat)}; "
        f"all block types: {[b.type for p in result.pages for b in p.content_blocks]}"
    )
    takhrij = takhrijat[0]
    assert takhrij.tokens[0].text == "رواه", (
        f"Expected first token 'رواه', got {takhrij.tokens[0].text!r}"
    )


def test_biography_marker_emits_prose_not_biography(tmp_path):
    """biography is a CUT block type. A $BIO_MAN$ marker line must produce a
    prose block (marker prefix stripped, name text preserved) — never biography."""
    src = tmp_path / "bio.mARkdown"
    src.write_text(
        "######OpenITI#\n"
        "#META# 020.BookTITLE\t:: اختبار\n"
        "#META# 00#VERS#LENGTH###\t:: 5\n"
        "#META#Header#End#\n"
        "# PageV01P001\n"
        "### $BIO_MAN$ محمد بن إسماعيل البخاري إمام\n",
        encoding="utf-8",
    )
    result = parse_file(src, "0100Test.BioBook")
    all_blocks = [block for page in result.pages for block in page.content_blocks]

    # No block may have type "biography"
    bio_blocks = [b for b in all_blocks if b.type == "biography"]
    assert bio_blocks == [], (
        f"Expected no biography blocks, got {len(bio_blocks)}: {bio_blocks}"
    )

    # The content must appear as a prose block
    prose_blocks = [b for b in all_blocks if b.type == "prose"]
    assert len(prose_blocks) >= 1, (
        f"Expected at least 1 prose block, got {len(prose_blocks)}; "
        f"all types: {[b.type for b in all_blocks]}"
    )

    all_tokens = [t.text for b in prose_blocks for t in b.tokens]
    # The name text is preserved
    assert "محمد" in all_tokens, (
        f"Expected 'محمد' in prose tokens, got {all_tokens}"
    )
    # The marker prefix is stripped (no $BIO_MAN$ or ### in any token)
    for tok in all_tokens:
        assert "$BIO_MAN$" not in tok, f"Marker prefix leaked into token: {tok!r}"
        assert tok != "###", f"Heading marker leaked into token: {tok!r}"
