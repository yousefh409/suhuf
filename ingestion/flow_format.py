"""The continuous-tagged, page-sliced book format ("flow").

The book is one continuous tagged document. Structure and entity tags carry
stable ids (assigned by :mod:`ingestion.number_ids`); the document is then sliced
at page boundaries for storage. A tag may open on one page fragment and close on
a later one — the cross-page span IS the win this format buys.

This module holds the pydantic models and :func:`build_annotations`, which
parses the id-bearing tags out of the NUMBERED continuous tagged string and
records each id, label, and char range in the compiled plain text, filling
``meta`` per label. It is kept independently unit-testable: it takes a tagged
string (and optional hadith-number markers) and returns a flat annotation list.
"""
from __future__ import annotations

from pydantic import BaseModel

from ingestion.models import BookMetadata, Chapter
from ingestion.page_slice import OpenTag, _ID_ATTR
from ingestion.tags import TagError, _TAG_SPLIT, _TAG
from ingestion.tagged_format import INLINE_TAGS, STRUCT_TAGS
from ingestion.number_ids import ID_PREFIXES
from ingestion import quran as _quran


class Annotation(BaseModel):
    """One id-bearing span in the continuous document, with resolved meta.

    ``start``/``end`` are character offsets into the book-global compiled plain
    text (``start`` inclusive, ``end`` exclusive). ``meta`` carries the resolved
    payload for the label (quran -> ``{sura, ayah}``, hadith -> ``{number}``,
    etc.); it is ``{}`` when nothing resolves.
    """
    id: str
    label: str
    start: int
    end: int
    meta: dict = {}


class FlowPage(BaseModel):
    """One page: its raw tagged fragment plus the tags open at its start."""
    page_number: int
    volume: int = 1
    tagged: str
    open_tags: list[OpenTag] = []
    text: str = ""           # derived plain text of this page
    start_offset: int = 0    # offset of this page's first char in the book text


class FlowBook(BaseModel):
    metadata: BookMetadata
    pages: list[FlowPage] = []
    chapters: list[Chapter] = []
    annotations: list[Annotation] = []
    # Author yml fields (parsed from the corpus .yml), and AI catalog enrichment
    # shaped {"book": {...}, "author": {...}}. Both default empty so existing
    # round-trips and tests are unaffected.
    author_data: dict = {}
    enrichment: dict = {}


def _resolve_meta(label: str, quote: str,
                  hadith_numbers: list[tuple[int, str]],
                  start: int, end: int) -> dict:
    """Fill the ``meta`` payload for one id-bearing span.

    quran -> ``{sura, ayah}`` via the deterministic ayah index (exact first,
    then the Uthmani-tolerant loose matcher); hadith -> ``{number}`` from the
    first numbered unit whose start falls inside the hadith's range; every
    other label -> ``{}``.
    """
    if label == "quran":
        hit = _quran.lookup_match(quote)
        if hit is not None:
            return {"sura": hit[0], "ayah": hit[1]}
        loose = _quran.loose_lookup(quote)
        if loose is not None:
            return {"sura": loose[0], "ayah": loose[1]}
        return {}
    if label == "hadith":
        number = None
        for off, num in hadith_numbers:
            if start <= off < end:
                number = num
                break
        return {"number": number}
    return {}


def build_annotations(tagged: str,
                      hadith_numbers: list[tuple[int, str]] | None = None
                      ) -> list[Annotation]:
    """Build the flat annotation list from a NUMBERED continuous tagged string.

    Walks ``tagged`` in document order, tracking the plain-text offset and a
    stack of open id-bearing tags. When an id-bearing tag closes, its range
    ``[start, end)`` in the compiled plain text is known and an
    :class:`Annotation` is emitted (in close order, then sorted by start). Only
    labels in :data:`~ingestion.number_ids.ID_PREFIXES` produce annotations;
    structural tags (isnad/matn/takhrij/verse/...) are skipped. ``meta`` is
    resolved per label via :func:`_resolve_meta`.

    ``hadith_numbers`` is an optional ``(plain_offset, number)`` list used to
    stamp each hadith's source number; omit it to leave ``{"number": None}``.

    Raises :class:`~ingestion.tags.TagError` on an unknown or mismatched tag,
    agreeing with the rest of the tag toolchain.
    """
    hadith_numbers = hadith_numbers or []
    text = ""
    offset = 0
    # stack entries: (label, id, start_offset) for id-bearing opens only;
    # non-id-bearing tags push a sentinel so closes stay balanced.
    stack: list[tuple[str, str | None, int]] = []
    anns: list[Annotation] = []

    for part in _TAG_SPLIT.split(tagged):
        if not part:
            continue
        if not part.startswith("<"):
            text += part
            offset += len(part)
            continue
        m = _TAG.fullmatch(part)
        if not m:
            raise TagError(f"malformed tag: {part!r}")
        closing, name = m.group(1), m.group(2)
        if name not in INLINE_TAGS and name not in STRUCT_TAGS:
            raise TagError(f"unknown tag: {name!r}")
        if not closing:
            if name in ID_PREFIXES:
                id_m = _ID_ATTR.search(part)
                stack.append((name, id_m.group(1) if id_m else None, offset))
            else:
                stack.append((name, None, offset))
        else:
            if not stack or stack[-1][0] != name:
                raise TagError(f"mismatched closing tag: </{name}>")
            label, span_id, start = stack.pop()
            if label in ID_PREFIXES:
                anns.append(Annotation(
                    id=span_id or "",
                    label=label,
                    start=start,
                    end=offset,
                    meta=_resolve_meta(label, text[start:offset],
                                       hadith_numbers, start, offset),
                ))

    if stack:
        raise TagError(f"unclosed tag: <{stack[-1][0]}>")

    anns.sort(key=lambda a: (a.start, -a.end))
    return anns
