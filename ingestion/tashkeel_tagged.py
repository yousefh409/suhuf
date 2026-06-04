"""Diacritize a tagged-format book, remapping span offsets.

Tashkeel adds combining marks (harakat, dagger alef) without changing base
letters, so it is a pure character insertion. We diacritize each block's text
and shift the character-offset spans by the insertions. If the engine alters
base letters (so the de-diacritized result no longer equals the input), the
block is left undiacritized rather than risk corrupting offsets.

Runs as the final pipeline stage (after annotate/resolve) and standalone over a
dumped book. `text_raw` keeps the undiacritized text for the reader's diff.
"""
from __future__ import annotations
import logging
import re

from ingestion import tagged_format as tf
from ingestion.tags import render_tagged
from ingestion.tashkeel import has_diacritics

logger = logging.getLogger(__name__)

_MARKS = re.compile(r"[ً-ٰٟـ]")   # harakat, dagger alef, tatweel


def _strip(s: str) -> str:
    return _MARKS.sub("", s)


def _offset_map(raw: str, dia: str) -> dict[int, int]:
    """raw index -> dia index, aligning base chars (marks in dia are insertions)."""
    m: dict[int, int] = {}
    ri = 0
    for di, c in enumerate(dia):
        if not _MARKS.match(c):
            m[ri] = di
            ri += 1
    m[len(raw)] = len(dia)
    return m


def _remap(spans: list[tf.Span], omap: dict[int, int]) -> list[tf.Span]:
    out = []
    for s in spans:
        a, b = omap.get(s.start), omap.get(s.end)
        if a is not None and b is not None and a < b:
            out.append(tf.Span(start=a, end=b, label=s.label,
                               sub=s.sub, ref=s.ref, conf=s.conf))
    return out


def _batch(engine, texts: list[str], size: int = 32) -> list[str]:
    if not texts:
        return []
    if hasattr(engine, "diacritize_batch"):
        out: list[str] = []
        for i in range(0, len(texts), size):
            out.extend(engine.diacritize_batch(texts[i:i + size]))
        return out
    return [engine.diacritize(t) for t in texts]


def diacritize_tagged_book(book: tf.Book, engine) -> dict:
    """Diacritize every block in place (batched). Returns a stats dict."""
    stats = {"blocks": 0, "diacritized": 0, "skipped": 0}
    if engine is None:
        return stats

    prose, poetry = [], []
    for page in book.pages:
        for b in page.blocks:
            stats["blocks"] += 1
            if b.type == "poetry":
                if b.lines:
                    poetry.append(b)
            elif b.text.strip() and not has_diacritics(b.text):
                prose.append(b)

    # Prose: one batched pass over block texts.
    dias = _batch(engine, [b.text for b in prose])
    for b, dia in zip(prose, dias):
        raw = b.text
        if _strip(dia) != raw:               # engine altered base letters — bail
            stats["skipped"] += 1
            continue
        spans = _remap(b.spans, _offset_map(raw, dia))
        b.text_raw, b.text, b.spans = raw, dia, spans
        b.tagged = render_tagged(dia, spans, b.lines)
        stats["diacritized"] += 1

    # Poetry: batch all hemistichs flat, then regroup per block.
    flat = [h for b in poetry for verse in b.lines for h in verse]
    fdias = iter(_batch(engine, flat))
    for b in poetry:
        new = [[next(fdias) for _ in verse] for verse in b.lines]
        ok = all(_strip(h2) == h for verse, v2 in zip(b.lines, new)
                 for h, h2 in zip(verse, v2))
        if not ok:
            stats["skipped"] += 1
            continue
        b.text_raw = b.text
        b.lines = new
        b.text = " ".join(h for verse in new for h in verse)
        b.tagged = render_tagged(b.text, [], new)
        stats["diacritized"] += 1
    return stats
