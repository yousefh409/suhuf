"""Deterministic id-assignment pass for the continuous tagged document.

The AI emits boundary tags WITHOUT ids. This pass walks the merged document in
document order and gives each addressable (id-bearing) opening tag a short,
stable, sequential id — ``{prefix}{n}`` with an independent per-label counter
starting at 1 (first ``<hadith>`` is ``h1``, second ``h2``; first ``<person>``
is ``p1``; etc.). Run on the whole merged document BEFORE it is sliced into
pages, so ids are globally unique by construction; metadata and citations then
key off the id.

Only the id-bearing labels in :data:`ID_PREFIXES` are numbered. The purely
structural tags (``isnad``, ``matn``, ``takhrij``, ``verse``, ``hemistich``,
``footnote``) carry no per-span metadata — they are rendered/derived from the
tag tree — so they get no id and are passed through unchanged, as are all
closing tags.

Idempotency: only id-less id-bearing opening tags are assigned. An opening tag
that already has an ``id="..."`` is left verbatim and does not perturb any
counter — counters reflect assignment order, so re-running :func:`assign_ids` on
already-numbered output is a no-op, and a doc with some pre-existing ids keeps
those untouched while the rest are numbered. Consequently, stripping the
inserted ``id="..."`` attributes from the output yields the original input.
"""
from __future__ import annotations

from ingestion.tags import TagError, _TAG_SPLIT, _TAG
from ingestion.page_slice import _ID_ATTR
from ingestion.tagged_format import INLINE_TAGS, STRUCT_TAGS

# Id-bearing label -> id prefix. Module-level so it is easy to extend. Only
# these labels get ids; every other (structural) tag is intentionally absent.
ID_PREFIXES: dict[str, str] = {
    "hadith": "h",
    "person": "p",
    "place": "pl",
    "quran": "q",
    "book_ref": "b",
    "hadith_ref": "hr",
    "date_hijri": "d",
}


def assign_ids(tagged: str) -> str:
    """Assign sequential, per-label ids to id-bearing opening tags in order.

    Walks ``tagged`` in document order. For each OPENING tag whose label is in
    :data:`ID_PREFIXES` and which does NOT already carry an ``id="..."``, inserts
    ``id="{prefix}{n}"`` (per-label counter from 1). Everything else — the rest
    of each tag, surrounding text, closing tags, structural tags, and any
    pre-existing ids — is preserved EXACTLY, so the only change is the inserted
    ``id`` attributes. See the module docstring for the idempotency contract.

    Raises :class:`~ingestion.tags.TagError` on a tag name that is not in
    ``INLINE_TAGS`` ∪ ``STRUCT_TAGS`` (full nesting validation is
    ``compile_tagged``'s job, not this pass's).
    """
    counters: dict[str, int] = {}
    out: list[str] = []

    for part in _TAG_SPLIT.split(tagged):
        if not part:
            continue
        if not part.startswith("<"):
            out.append(part)
            continue

        m = _TAG.fullmatch(part)
        if not m:
            raise TagError(f"malformed tag: {part!r}")
        closing, name = m.group(1), m.group(2)
        if name not in INLINE_TAGS and name not in STRUCT_TAGS:
            raise TagError(f"unknown tag: {name!r}")

        # Closing tags, structural tags, non-id-bearing labels, and tags that
        # already carry an id are passed through verbatim.
        if (
            closing
            or name not in ID_PREFIXES
            or _ID_ATTR.search(part)
        ):
            out.append(part)
            continue

        n = counters.get(name, 0) + 1
        counters[name] = n
        new_id = f'{ID_PREFIXES[name]}{n}'
        # Insert ` id="..."` right after the tag name, splicing on the regex's
        # name-end so the rest of the tag is preserved byte-for-byte. Stripping
        # the inserted `\s+id="..."` then reproduces the input exactly.
        cut = m.end(2)
        out.append(f'{part[:cut]} id="{new_id}"{part[cut:]}')

    return "".join(out)
