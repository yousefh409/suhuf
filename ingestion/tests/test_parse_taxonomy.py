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
