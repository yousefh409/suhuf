from __future__ import annotations
import json
import logging
from supabase import Client
from ingestion.models import ParseResult

logger = logging.getLogger(__name__)
PAGE_BATCH_SIZE = 100


def upload_book(
    result: ParseResult,
    author_data: dict,
    client: Client,
    has_tashkeel: bool = False,
) -> None:
    """Upload a parsed book to Supabase. All operations are upserts."""
    meta = result.metadata
    author_id = meta.author_openiti_id

    # 1. Upsert author
    author_row = {
        "openiti_id": author_id,
        "shuhra_ar": author_data.get("shuhra_lat", author_id),  # fallback to ID
        "shuhra_lat": author_data.get("shuhra_lat"),
        "ism_ar": author_data.get("ism_lat"),
        "nasab_ar": author_data.get("nasab_lat"),
        "kunya_ar": author_data.get("kunya_lat"),
        "laqab_ar": author_data.get("laqab_lat"),
        "nisba_ar": author_data.get("nisba_lat"),
        "birth_ah": author_data.get("birth_ah"),
        "death_ah": author_data.get("death_ah"),
    }
    # Remove None values
    author_row = {k: v for k, v in author_row.items() if v is not None}
    resp = client.table("authors").upsert(author_row, on_conflict="openiti_id").execute()
    author_uuid = resp.data[0]["id"]
    logger.info(f"Upserted author: {author_id} -> {author_uuid}")

    # 2. Upsert book
    book_row = {
        "openiti_id": meta.openiti_id,
        "author_id": author_uuid,
        "title_ar": meta.title_ar,
        "title_lat": meta.title_lat,
        "genres": meta.genres,
        "word_count": meta.word_count,
        "char_count": meta.char_count,
        "total_pages": len(result.pages),
        "total_volumes": max((p.volume for p in result.pages), default=1),
        "version_status": meta.version_status,
        "language": meta.language,
        "has_tashkeel": has_tashkeel,
    }
    book_row = {k: v for k, v in book_row.items() if v is not None}
    resp = client.table("books").upsert(book_row, on_conflict="openiti_id").execute()
    book_uuid = resp.data[0]["id"]
    logger.info(f"Upserted book: {meta.openiti_id} -> {book_uuid}")

    # 3. Upsert pages in batches
    for i in range(0, len(result.pages), PAGE_BATCH_SIZE):
        batch = result.pages[i:i + PAGE_BATCH_SIZE]
        page_rows = []
        for page in batch:
            blocks_data = [b.model_dump() for b in page.content_blocks]
            page_rows.append({
                "book_id": book_uuid,
                "page_number": page.page_number,
                "volume": page.volume,
                "content_blocks": blocks_data,
                "content_plain": page.content_plain,
                "content_hash": page.content_hash,
            })
        resp = client.table("pages").upsert(
            page_rows, on_conflict="book_id,volume,page_number"
        ).execute()
        logger.info(f"Upserted pages {i+1}-{i+len(batch)} / {len(result.pages)}")

    # 4. Upsert chapters
    # Get page UUIDs for linking
    page_resp = client.table("pages").select("id,page_number,volume").eq(
        "book_id", book_uuid
    ).execute()
    page_map = {(r["volume"], r["page_number"]): r["id"] for r in page_resp.data}

    for chapter in result.chapters:
        page_uuid = page_map.get((1, chapter.page_number))  # Default volume 1
        chapter_row = {
            "book_id": book_uuid,
            "title": chapter.title,
            "level": chapter.level,
            "page_id": page_uuid,
            "sort_order": chapter.sort_order,
        }
        chapter_row = {k: v for k, v in chapter_row.items() if v is not None}
        client.table("chapters").upsert(chapter_row, on_conflict="book_id,sort_order").execute()

    logger.info(f"Upserted {len(result.chapters)} chapters")
