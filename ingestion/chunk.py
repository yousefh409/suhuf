"""Unit-safe chunker for the continuous plain-text book.

The book is assembled into one continuous plain-text string. Before the AI tags
structure, the text is split into chunks under a size budget. The hard rule: a
chunk must never split a logical unit (a hadith). Cuts may only fall at unit
boundaries — the offsets where a printed hadith number or a chapter/section
heading begins. Page markers fall mid-unit and must never be cut points, so the
caller simply excludes them from ``boundaries``; this module stays generic.

Given the text and the allowed cut offsets, :func:`chunk_text` groups whole units
greedily into chunks under ``max_chars``. A single unit longer than the budget
becomes its own oversized chunk rather than being split. The chunks partition the
text exactly, and every cut falls on a normalized boundary.
"""
from __future__ import annotations

from pydantic import BaseModel


class Chunk(BaseModel):
    """A contiguous run of whole units, sliced from the book-global text."""
    text: str
    start: int   # offset of the chunk's first character in the book text


def chunk_text(text: str, boundaries: list[int], max_chars: int) -> list[Chunk]:
    """Group whole units into chunks under ``max_chars``, never splitting a unit.

    ``boundaries`` are plain-text offsets where a unit starts (the only allowed
    cut points). They are normalized internally: ``0`` and ``len(text)`` are
    added if absent, out-of-range and duplicate values are dropped, and the rest
    are sorted. The consecutive pairs define the units — unit ``i`` is
    ``text[b[i]:b[i + 1]]``.

    Units are grouped greedily: a chunk starts at a unit and keeps appending the
    next unit while the running length would stay ``<= max_chars``; then it
    closes and the next chunk begins. A single unit that already exceeds
    ``max_chars`` becomes its own (oversized) chunk — never split. The returned
    chunks partition ``text`` exactly and every cut lands on a normalized
    boundary.
    """
    if not text:
        return []

    bounds = sorted({b for b in boundaries if 0 <= b <= len(text)} | {0, len(text)})

    chunks: list[Chunk] = []
    start = bounds[0]          # start of the currently open chunk
    end = bounds[0]            # end of the units packed into it so far
    for nxt in bounds[1:]:
        if end == start:
            # Open chunk is empty: take this first unit unconditionally (it may
            # itself be oversized — that's allowed).
            end = nxt
        elif nxt - start <= max_chars:
            # Next whole unit still fits the budget: absorb it.
            end = nxt
        else:
            # Would overflow: close the open chunk and start a fresh one here.
            chunks.append(Chunk(text=text[start:end], start=start))
            start = end
            end = nxt
    chunks.append(Chunk(text=text[start:end], start=start))

    # Guarantee: every cut falls on a normalized boundary. `start`/`end` only
    # ever take values from `bounds` by construction, so this never fires — it
    # documents and enforces the contract.
    allowed = set(bounds)
    assert all(
        c.start in allowed and c.start + len(c.text) in allowed for c in chunks
    )
    return chunks
