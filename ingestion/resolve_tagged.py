"""Resolution passes for the tagged format: fill span metadata.

Each metadata field has one owner that attaches it to the compiled span, keyed
to span content so it survives a recompile. Today: quran `ref` via the
deterministic ayah index (ported from enrich.resolve_spans). The person `sub`
field is reserved; a classifier lands later (see spec, out of scope here).
"""
from __future__ import annotations

from ingestion import tagged_format as tf
from ingestion import quran as _quran


def resolve_quran_refs(book: tf.Book) -> int:
    """Set `ref` (sura:ayah) on every resolvable quran span. Returns the count.

    An exact match (the span is a whole ayah) is authoritative and overrides;
    a weaker containment match only fills a missing ref.
    """
    resolved = 0
    for page in book.pages:
        for block in page.blocks:
            for span in block.spans:
                if span.label != "quran":
                    continue
                quote = block.text[span.start:span.end]
                hit = _quran.lookup_match(quote)
                if hit is None:
                    continue
                sura, ayah, kind = hit
                if kind == "exact" or span.ref is None:
                    span.ref = f"{sura}:{ayah}"
                    resolved += 1
    return resolved


def resolve_book(book: tf.Book) -> dict:
    """Run all resolution passes over a tagged book in place."""
    return {"quran_refs": resolve_quran_refs(book)}
