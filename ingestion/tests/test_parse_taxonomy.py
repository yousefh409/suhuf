"""Tests for heading-level propagation using the taxonomy fixture."""
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


def test_heading_levels():
    result = parse_file(FIXTURE, "0000Sample.Taxonomy")
    headings = _heading_blocks(result)
    assert len(headings) == 2, f"Expected 2 heading blocks, got {len(headings)}"

    level1 = headings[0]
    level2 = headings[1]

    assert level1.level == 1, f"Expected level 1, got {level1.level}"
    assert level2.level == 2, f"Expected level 2, got {level2.level}"
