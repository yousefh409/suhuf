"""Upload a tagged-format book to Supabase.

Mirrors the legacy upload (authors/books/pages/chapters) but takes a
tagged_format.Book whose page blocks are the new shape (tagged/text/spans/lines).
Blocks go into pages.content_blocks JSONB as-is; the reader's newFormat converter
reconstructs the in-memory shape. Pages sharing (volume, page_number) are merged
(some sources reprint a marker) so the UNIQUE(book_id, volume, page_number)
constraint holds without data loss.
"""
from __future__ import annotations
import hashlib
import logging
import re
import unicodedata
from typing import Any

from ingestion import tagged_format as tf

logger = logging.getLogger(__name__)
PAGE_BATCH_SIZE = 50


def _author_display(author_data: dict, openiti_id: str) -> str:
    """A readable author name: the yml shuhra unless it's the OpenITI placeholder
    (Ibn Fulān al-Fulānī), else derived from the id (0672IbnMalik -> Ibn Malik)."""
    shuhra = author_data.get("shuhra_lat")
    if shuhra and "Ful" not in shuhra:
        return shuhra
    name = re.sub(r"^\d+", "", openiti_id)            # strip leading death year
    return re.sub(r"(?<=[a-z])(?=[A-Z])", " ", name) or openiti_id


def _page_plain(page: tf.Page) -> str:
    words: list[str] = []
    for b in page.blocks:
        if b.type == "poetry":
            words.extend(h for verse in b.lines for h in verse)
        elif b.text:
            words.append(b.text)
    return " ".join(words)


def _content_hash(plain: str) -> str:
    return hashlib.sha256(unicodedata.normalize("NFC", plain).encode()).hexdigest()


def _merge_duplicate_pages(pages: list[tf.Page]) -> list[tf.Page]:
    """Merge pages that share (volume, page_number), concatenating blocks in
    document order, so the unique constraint holds and no content is lost."""
    out: list[tf.Page] = []
    index: dict[tuple[int, int], tf.Page] = {}
    merged_keys: set[tuple[int, int]] = set()
    for p in pages:
        key = (p.volume, p.page_number)
        if key in index:
            index[key].blocks.extend(p.blocks)
            index[key].footnotes.extend(p.footnotes)
            merged_keys.add(key)
        else:
            merged = tf.Page(page_number=p.page_number, volume=p.volume,
                             blocks=list(p.blocks), footnotes=list(p.footnotes))
            index[key] = merged
            out.append(merged)
    # Re-key blocks of merged pages: each source page numbers blocks b0..bN, so a
    # merge produces colliding keys; renumber so they are unique within the page.
    for p in out:
        if (p.volume, p.page_number) in merged_keys:
            for i, b in enumerate(p.blocks):
                b.key = f"b{i}"
    if merged_keys:
        logger.info(f"Merged + re-keyed {len(merged_keys)} duplicate page(s)")
    return out


def upload_tagged_book(book: tf.Book, client: Any, author_data: dict | None = None) -> dict:
    meta = book.metadata
    author_data = author_data or {}
    stats = {"pages": 0, "chapters": 0}

    # 1. Author — populated from the OpenITI author yml when available so the
    # catalog shows a real name rather than the openiti id. (shuhra_ar is NOT
    # NULL; fall back to the latin shuhra, then the id.)
    display = _author_display(author_data, meta.author_openiti_id)
    author_row = {
        "openiti_id": meta.author_openiti_id,
        "shuhra_ar": display,
        "shuhra_lat": display,
        "ism_ar": author_data.get("ism_lat"),
        "nasab_ar": author_data.get("nasab_lat"),
        "kunya_ar": author_data.get("kunya_lat"),
        "laqab_ar": author_data.get("laqab_lat"),
        "nisba_ar": author_data.get("nisba_lat"),
        "birth_ah": author_data.get("birth_ah"),
        "death_ah": author_data.get("death_ah"),
    }
    author_row = {k: v for k, v in author_row.items() if v is not None}
    resp = client.table("authors").upsert(author_row, on_conflict="openiti_id").execute()
    author_uuid = resp.data[0]["id"]

    # 2. Book
    pages = _merge_duplicate_pages(book.pages)
    book_row = {
        "openiti_id": meta.openiti_id,
        "author_id": author_uuid,
        "title_ar": meta.title_ar,
        "genres": list(meta.genres) if meta.genres else [],
        "total_pages": len(pages),
        "total_volumes": max((p.volume for p in pages), default=1),
        "language": getattr(meta, "language", "ara") or "ara",
    }
    resp = client.table("books").upsert(book_row, on_conflict="openiti_id").execute()
    book_uuid = resp.data[0]["id"]
    logger.info(f"Upserted book {meta.openiti_id} -> {book_uuid}")

    # 3. Pages (content_blocks = new-format blocks, JSONB)
    for i in range(0, len(pages), PAGE_BATCH_SIZE):
        batch = pages[i:i + PAGE_BATCH_SIZE]
        rows = []
        for page in batch:
            plain = _page_plain(page)
            rows.append({
                "book_id": book_uuid,
                "page_number": page.page_number,
                "volume": page.volume,
                "content_blocks": [b.model_dump() for b in page.blocks],
                "content_plain": plain,
                "content_hash": _content_hash(plain),
            })
        client.table("pages").upsert(
            rows, on_conflict="book_id,volume,page_number").execute()
        stats["pages"] += len(batch)
        logger.info(f"Upserted pages {i+1}-{i+len(batch)} / {len(pages)}")

    # 4. Chapters (link to page rows by (volume, page_number))
    page_resp = client.table("pages").select("id,page_number,volume").eq(
        "book_id", book_uuid).execute()
    page_map = {(r["volume"], r["page_number"]): r["id"] for r in page_resp.data}
    for ch in book.chapters:
        row = {
            "book_id": book_uuid,
            "title": ch.title,
            "level": ch.level,
            "page_id": page_map.get((1, ch.page_number)),
            "sort_order": ch.sort_order,
        }
        row = {k: v for k, v in row.items() if v is not None}
        client.table("chapters").upsert(row, on_conflict="book_id,sort_order").execute()
    stats["chapters"] = len(book.chapters)
    logger.info(f"Upserted {len(book.chapters)} chapters")
    return stats
