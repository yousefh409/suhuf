"""Tests for the unit-safe chunker.

The book is one continuous plain-text string. Before the AI tags structure, the
text is split into chunks under a size budget. The hard rule: a chunk must never
split a logical unit (a hadith). Cuts may only fall on a value from the supplied
boundary list (the offsets where a printed hadith number / heading begins). Page
markers fall mid-unit and are simply excluded by the caller, so this module stays
generic: given the text and the allowed cut offsets, it groups whole units into
chunks greedily under ``max_chars``.

ASCII fixtures keep offsets easy to reason about; the real Arabic case is
mechanically identical. A text like ``"AA|BBBB|CC"`` has unit boundaries at the
``|`` positions, computed with ``str.index``.
"""
import random

import pytest

from ingestion.chunk import Chunk, chunk_text


def _boundaries_at(text: str, *units: str) -> list[int]:
    """Offsets where each unit begins, found in order with ``str.index``."""
    out = []
    pos = 0
    for u in units:
        i = text.index(u, pos)
        out.append(i)
        pos = i + len(u)
    return out


def _normalized(text: str, boundaries: list[int]) -> list[int]:
    """The boundary set the module is specified to normalize to."""
    return sorted({b for b in boundaries if 0 <= b <= len(text)} | {0, len(text)})


def _assert_partition(text: str, chunks: list[Chunk]) -> None:
    """Chunks partition the text exactly with correct, contiguous starts."""
    assert "".join(c.text for c in chunks) == text
    if not text:
        assert chunks == []
        return
    assert chunks[0].start == 0
    for prev, cur in zip(chunks, chunks[1:]):
        assert cur.start == prev.start + len(prev.text)
    last = chunks[-1]
    assert last.start + len(last.text) == len(text)


# ── greedy grouping under budget ─────────────────────────────────────────────

def test_greedy_groups_units_under_budget():
    # three units: "AA" (2), "BBBB" (4), "CC" (2). Boundaries at each unit start.
    text = "AABBBBCC"
    boundaries = _boundaries_at(text, "AA", "BBBB", "CC")  # [0, 2, 6]
    # max_chars=6 fits AA+BBBB (6) but not all three (8); CC starts a new chunk.
    chunks = chunk_text(text, boundaries, max_chars=6)
    assert [c.text for c in chunks] == ["AABBBB", "CC"]
    assert [c.start for c in chunks] == [0, 6]
    _assert_partition(text, chunks)


def test_greedy_does_not_overfill():
    # max_chars=2 only ever fits one of these 2-char units per chunk.
    text = "AABBCC"
    boundaries = _boundaries_at(text, "AA", "BB", "CC")
    chunks = chunk_text(text, boundaries, max_chars=2)
    assert [c.text for c in chunks] == ["AA", "BB", "CC"]
    assert [c.start for c in chunks] == [0, 2, 4]
    _assert_partition(text, chunks)


# ── boundaries are the only cut points ───────────────────────────────────────

def test_cuts_only_fall_on_normalized_boundaries():
    text = "AABBBBCC"
    boundaries = _boundaries_at(text, "AA", "BBBB", "CC")
    chunks = chunk_text(text, boundaries, max_chars=6)
    allowed = set(_normalized(text, boundaries))
    starts = {c.start for c in chunks}
    ends = {c.start + len(c.text) for c in chunks}
    assert starts <= allowed
    assert ends <= allowed


def test_interior_offset_is_never_a_cut_pagemarker_case():
    # Model a page marker: a long unit "BBBBBBBB" whose interior offsets are NOT
    # in `boundaries`. Even though it is far longer than its neighbors, it stays
    # whole — no cut lands inside it.
    text = "ABBBBBBBBC"
    boundaries = _boundaries_at(text, "A", "BBBBBBBB", "C")  # [0, 1, 9]
    chunks = chunk_text(text, boundaries, max_chars=4)
    # The long unit can't merge with neighbors under the budget, so it is alone.
    assert "BBBBBBBB" in [c.text for c in chunks]
    # No chunk boundary lands at an interior offset of the long unit (2..8).
    interior = set(range(2, 9))
    starts = {c.start for c in chunks}
    ends = {c.start + len(c.text) for c in chunks}
    assert not (starts & interior)
    assert not (ends & interior)
    _assert_partition(text, chunks)


# ── oversized single unit stays whole ────────────────────────────────────────

def test_oversized_single_unit_is_its_own_chunk():
    # Middle unit (8 chars) exceeds max_chars=3 and must not be split; the small
    # units around it still chunk normally.
    text = "AAXXXXXXXXBB"
    boundaries = _boundaries_at(text, "AA", "XXXXXXXX", "BB")  # [0, 2, 10]
    chunks = chunk_text(text, boundaries, max_chars=3)
    assert [c.text for c in chunks] == ["AA", "XXXXXXXX", "BB"]
    assert [c.start for c in chunks] == [0, 2, 10]
    # the oversized unit is exactly one chunk, undivided
    assert sum(c.text == "XXXXXXXX" for c in chunks) == 1
    _assert_partition(text, chunks)


# ── normalization: add 0/len, drop out-of-range/dupes, sort ──────────────────

def test_normalization_invariance():
    text = "AABBBBCC"
    canonical = [0, 2, 6, len(text)]
    # same set, but: missing 0 and len, a duplicate, out-of-range values, unsorted
    messy = [6, 2, 2, -5, 100, len(text) + 3]
    a = chunk_text(text, canonical, max_chars=6)
    b = chunk_text(text, messy, max_chars=6)
    assert [(c.text, c.start) for c in a] == [(c.text, c.start) for c in b]
    # and it matches the explicit expected grouping
    assert [(c.text, c.start) for c in a] == [("AABBBB", 0), ("CC", 6)]


def test_normalization_handles_only_zero_and_len_given():
    # No interior boundaries → whole text is one unit → one chunk.
    text = "HELLOWORLD"
    chunks = chunk_text(text, [], max_chars=100)
    assert [c.text for c in chunks] == ["HELLOWORLD"]
    assert chunks[0].start == 0
    _assert_partition(text, chunks)


# ── whole-partition round-trip over random combos ────────────────────────────

def test_random_partition_round_trip():
    rng = random.Random(1234)
    for _ in range(200):
        n = rng.randint(1, 40)
        text = "".join(rng.choice("ABCDE") for _ in range(n))
        # pick a random subset of interior offsets as boundaries (with noise)
        interior = rng.sample(range(1, n), k=rng.randint(0, max(0, n - 1)))
        noise = [rng.randint(-3, n + 3) for _ in range(rng.randint(0, 4))]
        boundaries = interior + noise
        max_chars = rng.randint(1, 12)

        chunks = chunk_text(text, boundaries, max_chars=max_chars)

        # exact partition with contiguous, correct starts
        _assert_partition(text, chunks)
        # cuts only ever fall on normalized boundaries
        allowed = set(_normalized(text, boundaries))
        for c in chunks:
            assert c.start in allowed
            assert c.start + len(c.text) in allowed
        # every chunk is a contiguous run of whole units (each internal seam is a
        # boundary), and no chunk is empty
        for c in chunks:
            assert c.text != ""


def test_random_respects_budget_when_possible():
    # When a chunk holds 2+ units, its length must be <= max_chars; a chunk over
    # budget is only allowed when it is a single (oversized) unit.
    rng = random.Random(99)
    for _ in range(200):
        n = rng.randint(2, 40)
        text = "".join(rng.choice("ABCDE") for _ in range(n))
        interior = sorted(set(rng.sample(range(1, n), k=rng.randint(0, n - 1))))
        max_chars = rng.randint(1, 12)
        norm = _normalized(text, interior)
        unit_lengths = [norm[i + 1] - norm[i] for i in range(len(norm) - 1)]

        chunks = chunk_text(text, interior, max_chars=max_chars)

        for c in chunks:
            if len(c.text) > max_chars:
                # must be a single oversized unit, i.e. its length equals one of
                # the unit lengths and it starts on a boundary
                assert c.start in set(norm)
                assert len(c.text) in unit_lengths


# ── edges ────────────────────────────────────────────────────────────────────

def test_empty_text_returns_empty_list():
    assert chunk_text("", [], max_chars=10) == []
    assert chunk_text("", [0, 3, 7], max_chars=10) == []


def test_no_interior_boundaries_single_chunk():
    text = "ABCDE"
    chunks = chunk_text(text, [], max_chars=100)
    assert len(chunks) == 1
    assert chunks[0].text == text
    assert chunks[0].start == 0


def test_no_interior_boundaries_oversized_single_chunk():
    # Whole text is one unit and exceeds the budget → still a single chunk.
    text = "ABCDEFGHIJ"
    chunks = chunk_text(text, [], max_chars=3)
    assert len(chunks) == 1
    assert chunks[0].text == text
    assert chunks[0].start == 0
