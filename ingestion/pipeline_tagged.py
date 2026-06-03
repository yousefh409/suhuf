"""New-format pipeline: parse -> detect -> align -> annotate(tagged) -> resolve.

Bridges the legacy parse + deterministic detector into the tagged format via the
aligner, then runs the tagged annotate and resolution passes. The legacy parse
and hadith stages are reused unchanged; only annotation moved to tagged text.
"""
from __future__ import annotations
import logging
from pathlib import Path

from ingestion.corpus import find_book_file
from ingestion.parse import parse_file
from ingestion.hadith import detect_hadith_structure
from ingestion.migrate_format import align_book
from ingestion.annotate_tagged import annotate_book_tagged
from ingestion.resolve_tagged import resolve_book
from ingestion import tagged_format as tf

logger = logging.getLogger(__name__)


def build_tagged_book(uri: str, corpus_path: str = "./RELEASE",
                      annotate: bool = True) -> tuple[tf.Book, dict]:
    path = find_book_file(uri, corpus_path=corpus_path)
    logger.info(f"Found file: {path.name}")
    result = parse_file(path, uri)
    logger.info(f"Parsed: {len(result.pages)} pages, {len(result.chapters)} chapters")
    detect_hadith_structure(result)
    book = align_book(result)

    stats: dict = {}
    if annotate:
        logger.info("Running tagged annotate pass...")
        stats["annotate"] = annotate_book_tagged(book)
        a = stats["annotate"]
        logger.info(f"Annotated: {a['entity_spans']} entity spans, "
                    f"{a['text_mismatch']} text-mismatch, {a['tag_errors']} tag-errors "
                    f"({a['input_tokens']} in / {a['output_tokens']} out tokens)")
    stats["resolve"] = resolve_book(book)
    logger.info(f"Resolved: {stats['resolve']['quran_refs']} quran refs")
    return book, stats
