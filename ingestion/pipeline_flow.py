"""Flow pipeline: parse -> assemble -> chunk -> AI structure -> number -> slice.

Produces the "continuous tagged, page-sliced" format. The book is assembled into
one plain-text string, chunked at unit boundaries, tagged whole-passage by the AI
(:mod:`ingestion.annotate_flow`), concatenated into one continuous tagged
document, numbered (:mod:`ingestion.number_ids`), and finally sliced at page
boundaries (:mod:`ingestion.page_slice`). Because structure is tagged on the
continuous document BEFORE slicing, a hadith stored across pages stays ONE
``<hadith>`` with ONE ``<matn>`` — the win the format buys.

Built alongside :mod:`ingestion.pipeline_tagged`; neither path touches the other.
"""
from __future__ import annotations
import logging

from ingestion.corpus import find_book_file
from ingestion.parse import parse_file
from ingestion.assemble import assemble, numbered_units
from ingestion.chunk import chunk_text
from ingestion.annotate_flow import annotate_flow
from ingestion.number_ids import assign_ids
from ingestion.page_slice import slice_tagged
from ingestion.flow_format import FlowBook, FlowPage, build_annotations
from ingestion.models import ParseResult

logger = logging.getLogger(__name__)

# Char budget per chunk for the AI structure pass. Large enough to keep whole
# hadiths together; the chunker never splits a unit regardless.
CHUNK_BUDGET = 8000


def flow_from_result(result: ParseResult, annotate: bool = True,
                     client=None, budget: int = CHUNK_BUDGET
                     ) -> tuple[FlowBook, dict]:
    """Build a :class:`FlowBook` from an already-parsed book.

    Split out from :func:`build_flow_book` so the post-parse plumbing is testable
    offline with a synthetic ``ParseResult`` and a mock ``client``. Returns the
    book and a stats dict (carrying the numbered continuous ``tagged`` for tests
    plus the annotate stats).
    """
    text, page_offsets, boundaries = assemble(result)
    stats: dict = {"pages": len(result.pages), "chunks": 0}

    if annotate:
        chunks = chunk_text(text, boundaries, budget)
        stats["chunks"] = len(chunks)
        tagged_chunks, a_stats = annotate_flow([c.text for c in chunks], client=client)
        stats["annotate"] = a_stats
        # Chunks partition `text` exactly (no separators), and each tagged chunk's
        # plain text equals its source chunk (validated, else fell back to plain),
        # so concatenation reproduces a continuous tagged document whose plain
        # text equals `text`.
        continuous = "".join(tagged_chunks)
    else:
        # No AI pass: the assembled plain text IS the tagged document (no tags).
        continuous = text

    numbered = assign_ids(continuous)
    stats["tagged"] = numbered

    annotations = build_annotations(numbered, hadith_numbers=numbered_units(result))

    # Page breaks are the interior page start offsets (exclude the first page's 0).
    breaks = [off for (_pn, _vol, off) in page_offsets[1:]]
    slices = slice_tagged(numbered, breaks)
    # Defense-in-depth: slice_tagged drops a break that is strictly past the text
    # length, which would silently lose trailing pages in the zip below. The
    # assembler never emits such an offset, so this asserts that invariant.
    assert len(slices) == len(page_offsets), (len(slices), len(page_offsets))

    pages: list[FlowPage] = []
    for (page_number, volume, start_offset), sl in zip(page_offsets, slices):
        # Plain text of this page: the assembled text between this page's start
        # and the next page's start (book end for the last page).
        nxt = next((o for (_p, _v, o) in page_offsets if o > start_offset), len(text))
        pages.append(FlowPage(
            page_number=page_number,
            volume=volume,
            tagged=sl.tagged,
            open_tags=sl.open_tags,
            text=text[start_offset:nxt],
            start_offset=start_offset,
        ))

    book = FlowBook(metadata=result.metadata, pages=pages,
                    chapters=list(result.chapters), annotations=annotations)
    return book, stats


def build_flow_book(uri: str, corpus_path: str = "./RELEASE",
                    annotate: bool = True, client=None) -> tuple[FlowBook, dict]:
    """Parse a book from the corpus and build its :class:`FlowBook`."""
    path = find_book_file(uri, corpus_path=corpus_path)
    logger.info(f"Found file: {path.name}")
    result = parse_file(path, uri)
    logger.info(f"Parsed: {len(result.pages)} pages, {len(result.chapters)} chapters")
    # No deterministic hadith pass here: the flow AI pass tags structure from the
    # assembled plain text, which ignores detector spans.
    book, stats = flow_from_result(result, annotate=annotate, client=client)
    if annotate:
        a = stats.get("annotate", {})
        logger.info(f"Flow annotate: {stats['chunks']} chunks, "
                    f"{a.get('fallbacks', 0)} fallbacks "
                    f"({a.get('input_tokens', 0)} in / {a.get('output_tokens', 0)} out tokens)")
    logger.info(f"Flow: {len(book.annotations)} annotations over {len(book.pages)} pages")
    return book, stats
