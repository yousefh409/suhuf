"""Page-slice / reconstruct core for the continuous tagged book format.

The book is one continuous tagged document (HTML-style boundary tags with stable
ids, e.g. ``<hadith id="h2"><matn>…</matn></hadith>``). Pages are only where that
document is sliced for storage and download — a tag may open on one slice and
close on a later one. This module is the pure-function core that proves slicing
is lossless and records the open-tag stack at each slice's start.

Each :class:`PageSlice` stores its **raw tagged fragment** plus an ``open_tags``
list (the tag stack open at its START). Tags are left genuinely unclosed across
slices; :func:`reconstruct` is plain string concatenation.

Assumption (v1): the text contains no ``&lt;``/``&gt;``/``&amp;`` entities — per
the tag-grammar note that they effectively never occur in classical Arabic — so a
plain-text offset equals a raw-substring offset. We therefore split raw tagged
text directly at plain-text break offsets without any entity remapping.
"""
from __future__ import annotations
import re

from pydantic import BaseModel

from ingestion.tags import _TAG_SPLIT, _TAG

# `_TAG` captures (closing-slash, name) but drops attributes. Pull the optional
# `id="…"` out separately; every other attribute stays ignored.
_ID_ATTR = re.compile(r'\bid\s*=\s*"([^"]*)"')


class OpenTag(BaseModel):
    """A tag open at a slice boundary: its name plus optional stable id."""
    name: str
    id: str | None = None


class PageSlice(BaseModel):
    """One page's raw tagged fragment and the tag stack open at its start."""
    tagged: str
    open_tags: list[OpenTag] = []


def slice_tagged(tagged: str, breaks: list[int]) -> list[PageSlice]:
    """Slice a continuous tagged document at plain-text ``breaks``.

    ``breaks`` are offsets into the PLAIN text (tags stripped) where a new page
    begins — interior cut points, in ascending order, not including 0. Produces
    ``len(breaks) + 1`` slices in document order.

    Walks the tag stream tracking the plain-text offset and the open-tag stack.
    When the plain offset reaches a break, the current fragment is finalized and
    a new one started whose ``open_tags`` is a snapshot of the stack at that
    point. A break may land inside a tag's text, exactly on a tag boundary, or
    between two tags. The first slice's ``open_tags`` is always empty.
    """
    pending = sorted(b for b in breaks if b > 0)

    slices: list[PageSlice] = []
    stack: list[OpenTag] = []        # tags open at the current position
    cur = ""                         # raw text accumulated for the current slice
    cur_open: list[OpenTag] = []     # snapshot for the current slice's start
    offset = 0                       # plain-text offset consumed so far

    def cut() -> None:
        nonlocal cur, cur_open
        slices.append(PageSlice(tagged=cur, open_tags=list(cur_open)))
        cur = ""
        cur_open = [t.model_copy() for t in stack]

    for part in _TAG_SPLIT.split(tagged):
        if not part:
            continue
        if part.startswith("<"):
            m = _TAG.fullmatch(part)
            if m:
                closing, name = m.group(1), m.group(2)
                if closing:
                    stack.pop()
                else:
                    id_m = _ID_ATTR.search(part)
                    stack.append(OpenTag(name=name, id=id_m.group(1) if id_m else None))
            # Tags are zero-width in plain text; emit verbatim into this slice.
            cur += part
        else:
            # Text part: may span one or more breaks. Emit up to each pending
            # break that falls within this part, cutting exactly at the offset.
            i = 0
            while pending and pending[0] <= offset + (len(part) - i):
                seg = part[i:i + (pending[0] - offset)]
                cur += seg
                offset += len(seg)
                i += len(seg)
                pending.pop(0)
                cut()
            rest = part[i:]
            cur += rest
            offset += len(rest)

    slices.append(PageSlice(tagged=cur, open_tags=list(cur_open)))
    return slices


def reconstruct(slices: list[PageSlice]) -> str:
    """Inverse of :func:`slice_tagged`: concatenate the slices' raw fragments."""
    return "".join(s.tagged for s in slices)


def close_fragment(slice: PageSlice) -> str:
    """Make one slice independently well-formed for isolated compile/render.

    Prepends the ``open_tags`` as opening tags (re-emitting each ``id`` if
    present) and appends closing tags for any tags still open at the fragment's
    end, in correct nesting order. The result parses with ``compile_tagged``
    without raising.
    """
    opener = "".join(_open_tag(t) for t in slice.open_tags)
    body = slice.tagged

    # Compute the tags still open at the fragment's end: start from the open
    # stack, then replay this fragment's own opens/closes.
    stack: list[OpenTag] = list(slice.open_tags)
    for part in _TAG_SPLIT.split(body):
        if not part or not part.startswith("<"):
            continue
        m = _TAG.fullmatch(part)
        if not m:
            continue
        closing, name = m.group(1), m.group(2)
        if closing:
            if stack:
                stack.pop()
        else:
            stack.append(OpenTag(name=name))

    closer = "".join(f"</{t.name}>" for t in reversed(stack))
    return opener + body + closer


def _open_tag(t: OpenTag) -> str:
    return f'<{t.name} id="{t.id}">' if t.id is not None else f"<{t.name}>"
