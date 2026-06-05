"""Upload a flow-format book to Supabase.

Writes a :class:`~ingestion.flow_format.FlowBook` (authors -> books -> pages ->
chapters): each page stores its raw ``tagged`` fragment plus the ``open_tags``
stack open at its start, and a separate ``annotations`` layer is written keyed by
tag id. Flow pages leave ``content_blocks`` NULL — the ``tagged`` column is
canonical for this format.

(volume, page_number) is assumed unique across flow pages (the slicer emits one
slice per page), so no duplicate-page merge is needed.
"""
from __future__ import annotations
import hashlib
import logging
import re
import unicodedata
from typing import Any

from ingestion import flow_format as ff

logger = logging.getLogger(__name__)
PAGE_BATCH_SIZE = 50
ANNOTATION_BATCH_SIZE = 50


def _author_display(author_data: dict, openiti_id: str) -> str:
    """A readable author name: the yml shuhra unless it's the OpenITI placeholder
    (Ibn Fulān al-Fulānī), else derived from the id (0672IbnMalik -> Ibn Malik)."""
    shuhra = author_data.get("shuhra_lat")
    if shuhra and "Ful" not in shuhra:
        return shuhra
    name = re.sub(r"^\d+", "", openiti_id)            # strip leading death year
    return re.sub(r"(?<=[a-z])(?=[A-Z])", " ", name) or openiti_id


def _content_hash(plain: str) -> str:
    return hashlib.sha256(unicodedata.normalize("NFC", plain).encode()).hexdigest()


def upload_flow_book(book: ff.FlowBook, client: Any,
                     author_data: dict | None = None) -> dict:
    meta = book.metadata
    author_data = author_data or {}
    stats = {"pages": 0, "chapters": 0, "annotations": 0}

    # 1. Author
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
    pages = book.pages
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

    # 3. Pages (tagged + open_tags; content_blocks left NULL for flow pages)
    for i in range(0, len(pages), PAGE_BATCH_SIZE):
        batch = pages[i:i + PAGE_BATCH_SIZE]
        rows = []
        for page in batch:
            rows.append({
                "book_id": book_uuid,
                "page_number": page.page_number,
                "volume": page.volume,
                "tagged": page.tagged,
                "open_tags": [o.model_dump() for o in page.open_tags],
                "content_plain": page.text,
                "content_hash": _content_hash(page.text),
                "start_offset": page.start_offset,
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

    # 5. Annotations (resolved metadata layer, one row per tag id)
    anns = book.annotations
    for i in range(0, len(anns), ANNOTATION_BATCH_SIZE):
        batch = anns[i:i + ANNOTATION_BATCH_SIZE]
        rows = [{
            "book_id": book_uuid,
            "tag_id": a.id,
            "label": a.label,
            "start_offset": a.start,
            "end_offset": a.end,
            "meta": a.meta,
        } for a in batch]
        client.table("annotations").upsert(
            rows, on_conflict="book_id,tag_id").execute()
    stats["annotations"] = len(anns)
    logger.info(f"Upserted {len(anns)} annotations")
    return stats
