"""Deterministically wrap source headings in <heading> tags.

The AI structure pass leaves chapter/section titles untagged, but headings are
reliable source structure (### | in mARkdown). After the AI pass and id
numbering, this wraps each heading's plain-text range (from
:func:`ingestion.assemble.heading_ranges`) in ``<heading>...</heading>`` in the
continuous tagged document, so the reader can render headings as headings.

Headings sit at unit boundaries (top level, between hadith), so the inserted
tags do not interleave with the hadith/entity tags. Insertion is by plain-text
offset, mapped through the tag stream the same way the other passes walk it.
"""
from __future__ import annotations

from ingestion.tags import _TAG_SPLIT, _TAG


def tag_headings(tagged: str, ranges: list[tuple[int, int]]) -> str:
    """Insert ``<heading>``/``</heading>`` around each plain-text range. `ranges`
    are ``(start, end)`` offsets into the tagged document's plain text (tags
    stripped). Returns the tagged document with heading tags added; the
    tags-stripped text is unchanged."""
    if not ranges:
        return tagged

    # offset -> list of tag strings to emit there (closes before opens).
    events: dict[int, list[str]] = {}
    for s, e in ranges:
        events.setdefault(s, []).append("<heading>")
        events.setdefault(e, []).insert(0, "</heading>")  # closes first at a shared offset

    out: list[str] = []
    plain = 0

    def flush(pos: int) -> None:
        if pos in events:
            out.extend(events.pop(pos))

    for part in _TAG_SPLIT.split(tagged):
        if not part:
            continue
        if part.startswith("<") and _TAG.fullmatch(part):
            flush(plain)            # a heading boundary that lands at a tag position
            out.append(part)
        else:
            for ch in part:
                flush(plain)        # open/close due before this char
                out.append(ch)
                plain += 1
    flush(plain)                    # a close at the very end of the text
    return "".join(out)
