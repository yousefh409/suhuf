"""Resolution passes for the tagged format: fill span metadata.

Each metadata field has one owner that attaches it to the compiled span, keyed
to span content so it survives a recompile. Today: quran `ref` via the
deterministic ayah index (ported from enrich.resolve_spans). The person `sub`
field is reserved; a classifier lands later (see spec, out of scope here).
"""
from __future__ import annotations

from ingestion import tagged_format as tf
from ingestion import quran as _quran
from ingestion.hadith import _norm


def _norm_phrase(text: str) -> str:
    return " ".join(_norm(w) for w in text.split())


# Hadith collections whose names, when they appear inside a takhrij, denote the
# source work rather than a narrator. Same name in an isnad stays a person.
_COLLECTION_NAMES = [
    "البخاري", "مسلم", "الترمذي", "أبو داود", "أبي داود", "النسائي",
    "ابن ماجه", "ابن ماجة", "أحمد", "مالك", "الدارمي", "الدارقطني",
    "البيهقي", "الحاكم", "الطبراني", "أبو يعلى", "أبي يعلى", "ابن حبان",
    "ابن خزيمة", "عبد الرزاق", "الشافعي",
]
_COLLECTIONS = {_norm_phrase(n) for n in _COLLECTION_NAMES}


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
                if hit is not None:
                    sura, ayah, kind = hit
                    if kind == "exact" or span.ref is None:
                        span.ref = f"{sura}:{ayah}"
                        resolved += 1
                    continue
                # Fallback: loose matcher tolerant of Uthmani-vs-standard spelling.
                if span.ref is None:
                    loose = _quran.loose_lookup(quote)
                    if loose is not None:
                        span.ref = f"{loose[0]}:{loose[1]}"
                        resolved += 1
    return resolved


def reclassify_takhrij_sources(book: tf.Book) -> int:
    """Relabel a person span to book_ref when its text is a hadith-collection
    name and it sits inside a takhrij span (the source work, not a narrator).
    Returns the count relabeled."""
    n = 0
    for page in book.pages:
        for block in page.blocks:
            takhrij = [s for s in block.spans if s.label == "takhrij"]
            if not takhrij:
                continue
            for s in block.spans:
                if s.label != "person":
                    continue
                inside = any(t.start <= s.start and s.end <= t.end for t in takhrij)
                if inside and _norm_phrase(block.text[s.start:s.end]) in _COLLECTIONS:
                    s.label = "book_ref"
                    n += 1
    return n


def resolve_book(book: tf.Book) -> dict:
    """Run all resolution passes over a tagged book in place."""
    return {
        "quran_refs": resolve_quran_refs(book),
        "takhrij_sources": reclassify_takhrij_sources(book),
    }
