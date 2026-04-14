from __future__ import annotations

import re

from ingestion.corpus import parse_uri
from ingestion.models import BookMetadata

_MISSING = {"NODATA", "NOTGIVEN", "NOCODE"}

_HEADER_END = "#META#Header#End#"

# Keys that map to BookMetadata fields
_TITLE_KEYS = {"020.BookTITLE", "10#BOOK#TITLEA#AR"}
_WORD_COUNT_KEY = "00#VERS#LENGTH###"
_CHAR_COUNT_KEY = "00#VERS#CLENGTH##"
_GENRE_KEY = "40#BOOK#GENRE####"


def _is_missing(value: str) -> bool:
    return value.strip() in _MISSING


def parse_file_header(lines: list[str], openiti_uri: str) -> BookMetadata:
    """Parse the #META# header block from a .mARkdown file.

    Reads lines until #META#Header#End# and extracts structured metadata.
    Returns a BookMetadata instance.
    """
    author_id, book_id = parse_uri(openiti_uri)
    openiti_id = openiti_uri

    title_ar: str | None = None
    word_count: int | None = None
    char_count: int | None = None
    genres: list[str] = []

    for line in lines:
        if _HEADER_END in line:
            break

        # Each metadata line looks like: #META# key\t:: value
        if not line.startswith("#META#"):
            continue

        # Strip the "#META# " prefix (7 chars including trailing space)
        body = line[len("#META# "):]

        # Split on tab + "::" separator
        if "\t:: " in body:
            key, _, raw_value = body.partition("\t:: ")
        elif "\t::" in body:
            key, _, raw_value = body.partition("\t::")
        else:
            continue

        key = key.strip()
        value = raw_value.strip()

        if _is_missing(value):
            continue

        if key in _TITLE_KEYS:
            if title_ar is None:
                title_ar = value

        elif key == _WORD_COUNT_KEY:
            try:
                word_count = int(value)
            except ValueError:
                pass

        elif key == _CHAR_COUNT_KEY:
            try:
                char_count = int(value)
            except ValueError:
                pass

        elif key == _GENRE_KEY:
            parts = [p.strip() for p in value.split("::")]
            genres = [p for p in parts if p and p not in _MISSING]

    return BookMetadata(
        openiti_id=openiti_id,
        title_ar=title_ar or openiti_uri,
        author_openiti_id=author_id,
        word_count=word_count,
        char_count=char_count,
        genres=genres,
    )


# Author YML field mapping
_AUTH_FIELD_MAP = {
    "10#AUTH#SHUHRA#AR": "shuhra_lat",
    "10#AUTH#ISM####AR": "ism_lat",
    "10#AUTH#NASAB##AR": "nasab_lat",
    "10#AUTH#KUNYA##AR": "kunya_lat",
    "10#AUTH#LAQAB##AR": "laqab_lat",
    "10#AUTH#NISBA##AR": "nisba_lat",
    "30#AUTH#BORN###AH": "birth_ah",
    "30#AUTH#DIED###AH": "death_ah",
}

_DATE_INT_KEYS = {"birth_ah", "death_ah"}


def _extract_leading_int(value: str) -> int | None:
    """Return the leading digit sequence from a value like "0631-MUH-XX" -> 631."""
    m = re.match(r"(\d+)", value.strip())
    if m:
        return int(m.group(1))
    return None


def parse_author_yml(lines: list[str]) -> dict:
    """Parse an OpenITI author .yml file (custom key: value format, not real YAML).

    Returns a plain dict with mapped field names as keys. All expected keys are
    always present; missing or NODATA values are represented as None.
    """
    result: dict = {field: None for field in _AUTH_FIELD_MAP.values()}

    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        if ": " in line:
            key, _, raw_value = line.partition(": ")
        elif line.endswith(":"):
            key = line[:-1]
            raw_value = ""
        else:
            continue

        key = key.strip()
        value = raw_value.strip()

        field = _AUTH_FIELD_MAP.get(key)
        if field is None:
            continue

        if _is_missing(value) or value == "":
            continue

        if field in _DATE_INT_KEYS:
            parsed = _extract_leading_int(value)
            if parsed is not None:
                result[field] = parsed
        else:
            result[field] = value

    return result
