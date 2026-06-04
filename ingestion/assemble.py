"""Assemble a parsed book into one continuous plain-text string.

The flow pipeline tags structure over a book-global plain-text string rather than
per block. :func:`assemble` concatenates each page's plain text — using the SAME
derivation as :attr:`~ingestion.models.Page.content_plain` — in document order,
joined by a single space (the separator counts toward offsets). It returns:

* ``text`` — the continuous plain text.
* ``page_offsets`` — ``(page_number, volume, start_offset)`` per page, the offset
  of each page's first character. Page offsets may land mid-unit; they are NOT
  chunk cut points.
* ``boundaries`` — the start offset of every heading block (hadith numbers and
  chapter titles are both heading blocks). These are the ONLY allowed chunk cut
  points for :func:`ingestion.chunk.chunk_text`.
"""
from __future__ import annotations

from ingestion.models import Block, Page, ParseResult

# Single-space separator between pages. Chosen to match the intra-page token
# join in `content_plain`; the char counts toward offsets.
_PAGE_SEP = " "


def _block_words(block: Block) -> list[str]:
    """Words of one block, matching ``Page.content_plain``'s derivation."""
    if block.type == "poetry":
        return [t.text for verse in block.hemistichs
                for hemistich in verse for t in hemistich]
    return [t.text for t in block.tokens]


def _page_plain(page: Page) -> str:
    """Plain text of a page, identical to ``Page.content_plain``."""
    words: list[str] = []
    for block in page.content_blocks:
        words.extend(_block_words(block))
    return " ".join(words)


def numbered_units(result: ParseResult) -> list[tuple[int, str]]:
    """Return ``(start_offset, number)`` for every block carrying a printed item
    number, in document order.

    Used to stamp each hadith annotation with its source number. Offsets are
    computed with the same page-join / word-join convention as :func:`assemble`,
    so they line up with the continuous text.
    """
    out: list[tuple[int, str]] = []
    offset = 0
    for pi, page in enumerate(result.pages):
        if pi:
            offset += len(_PAGE_SEP)
        col = 0
        for block in page.content_blocks:
            words = _block_words(block)
            if not words:
                continue
            if col:
                col += 1
            if block.number is not None:
                out.append((offset + col, block.number))
            col += len(" ".join(words))
        offset += len(_page_plain(page))
    return out


def assemble(result: ParseResult
             ) -> tuple[str, list[tuple[int, int, int]], list[int]]:
    """Return ``(text, page_offsets, boundaries)`` for a parsed book."""
    parts: list[str] = []
    page_offsets: list[tuple[int, int, int]] = []
    boundaries: list[int] = []
    offset = 0

    for pi, page in enumerate(result.pages):
        if pi:
            # Page separator precedes every page after the first.
            parts.append(_PAGE_SEP)
            offset += len(_PAGE_SEP)
        page_offsets.append((page.page_number, page.volume, offset))

        # Record each heading block's start offset by replaying the page's
        # word-join, exactly as `content_plain` builds it: words join with one
        # space, so the first word of a block (after the first) is preceded by a
        # single separator space.
        col = 0  # char column within this page's plain text
        for block in page.content_blocks:
            words = _block_words(block)
            if not words:
                continue
            if col:
                col += 1  # the join space before this block's first word
            if block.type == "heading":
                boundaries.append(offset + col)
            col += len(" ".join(words))

        page_text = _page_plain(page)
        parts.append(page_text)
        offset += len(page_text)

    return "".join(parts), page_offsets, boundaries
