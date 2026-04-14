from __future__ import annotations

from pathlib import Path

# Extensions to skip entirely - they are metadata/documentation, not text.
_SKIP_SUFFIXES = {".yml", ".md"}

# Quality tiers from best to worst. Files with no recognized suffix fall into
# tier 2 (raw). A higher tier index means lower quality.
_QUALITY_ORDER = [".mARkdown", ".completed"]


def parse_uri(openiti_uri: str) -> tuple[str, str]:
    """Split "AuthorID.BookID" into ("AuthorID", "BookID").

    Raises ValueError if the URI contains no dot.
    """
    if "." not in openiti_uri:
        raise ValueError(
            f"Invalid OpenITI URI '{openiti_uri}': expected 'AuthorID.BookID' format"
        )
    author_id, _, book_id = openiti_uri.partition(".")
    return author_id, book_id


def find_book_file(openiti_uri: str, corpus_path: str) -> Path:
    """Locate the best-quality text file for *openiti_uri* inside *corpus_path*.

    Directory layout expected::

        data/{AuthorID}/{AuthorID}.{BookID}/{AuthorID}.{BookID}.{Source}-ara{N}.<ext>

    Quality priority: .mARkdown > .completed > raw (no recognized extension).
    Files with .yml or .md suffixes are skipped entirely.

    Raises FileNotFoundError if no suitable file is found.
    """
    author_id, book_id = parse_uri(openiti_uri)
    book_dir = Path(corpus_path) / "data" / author_id / f"{author_id}.{book_id}"

    if not book_dir.is_dir():
        raise FileNotFoundError(
            f"Book directory not found: {book_dir}"
        )

    candidates: list[Path] = [
        p for p in book_dir.iterdir()
        if p.is_file() and p.suffix not in _SKIP_SUFFIXES
    ]

    if not candidates:
        raise FileNotFoundError(
            f"No text files found for '{openiti_uri}' in {book_dir}"
        )

    def _quality_key(p: Path) -> int:
        try:
            return _QUALITY_ORDER.index(p.suffix)
        except ValueError:
            # Raw file (no recognized suffix) gets the lowest priority tier.
            return len(_QUALITY_ORDER)

    best = min(candidates, key=_quality_key)
    return best


def find_author_metadata(author_id: str, corpus_path: str) -> Path | None:
    """Return the path to ``data/{author_id}/{author_id}.yml``, or None."""
    yml = Path(corpus_path) / "data" / author_id / f"{author_id}.yml"
    return yml if yml.is_file() else None
