"""AI metadata enrichment using Claude API."""
from __future__ import annotations
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from anthropic import Anthropic

from ingestion._client import create_client, parse_json_response
from ingestion.models import ParseResult

logger = logging.getLogger(__name__)

MODEL = "claude-sonnet-4-20250514"
MAX_SAMPLE_CHARS = 4000


def _build_book_prompt(result: ParseResult) -> str:
    """Build a prompt for book metadata enrichment."""
    meta = result.metadata

    # Collect chapter titles
    chapter_titles = [ch.title for ch in result.chapters[:50]]

    # Sample content from first few pages
    sample = ""
    for page in result.pages[:5]:
        sample += page.content_plain + "\n"
        if len(sample) > MAX_SAMPLE_CHARS:
            break
    sample = sample[:MAX_SAMPLE_CHARS]

    return f"""You are an expert in classical Islamic literature and Arabic texts.

Given the following information about a classical Arabic book, provide metadata in JSON format.

**Book info:**
- OpenITI ID: {meta.openiti_id}
- Arabic title: {meta.title_ar}
- Author ID: {meta.author_openiti_id}
- Total pages: {len(result.pages)}
- Total chapters: {len(result.chapters)}

**Chapter titles (first 50):**
{chr(10).join(f"- {t}" for t in chapter_titles)}

**Sample content (first pages):**
{sample}

**Return ONLY a JSON object with these fields:**
- "title_en": English translation of the book title (string)
- "description": 2-3 sentence English description of the book's content, significance, and audience (string)
- "genres": array of genre tags from this list: HADITH, FIQH, TAFSIR, TARIKH, TABAQAT, ADAB, LUGHA, NAHW, SARF, BALAGHA, USUL, AQIDA, TASAWWUF, TIBB, FALSAFA, MANTIQ, SIRA, GEOGRAPHY, POETRY, OTHER
- "composition_date_ah": approximate Hijri year of composition (integer or null if unknown)
- "commentary_on": if this is a commentary, the OpenITI URI of the original work (string or null)
- "abridgement_of": if this is an abridgement, the OpenITI URI of the original work (string or null)

Return ONLY valid JSON, no markdown fences, no explanation."""


def _build_author_prompt(author_id: str, existing_data: dict) -> str:
    """Build a prompt for author metadata enrichment."""
    existing_info = "\n".join(f"- {k}: {v}" for k, v in existing_data.items() if v)

    return f"""You are an expert in classical Islamic biography and scholarship.

Given the following author identifier and any existing metadata, provide enriched metadata in JSON format.

**Author ID:** {author_id}
(The numeric prefix is the Hijri death year, e.g. 0676 = died 676 AH)

**Existing metadata:**
{existing_info or "None available"}

**Return ONLY a JSON object with these fields:**
- "full_name_en": full English transliteration of the author's name (string)
- "bio_en": 2-3 sentence English biography covering their era, school of thought, major works, and significance (string)
- "birth_ah": Hijri birth year (integer or null if unknown)
- "death_ah": Hijri death year (integer or null if unknown)
- "primary_fields": array of their main scholarly fields from: HADITH, FIQH, TAFSIR, TARIKH, ADAB, LUGHA, TASAWWUF, AQIDA, FALSAFA, OTHER

Return ONLY valid JSON, no markdown fences, no explanation."""


def enrich_book_metadata(
    result: ParseResult,
    client: "Anthropic | None" = None,
) -> dict:
    """Use Claude to enrich book metadata. Returns dict of enriched fields."""
    if client is None:
        try:
            client = create_client()
        except Exception as e:
            logger.warning(f"Could not create Anthropic client: {e}")
            return {}

    prompt = _build_book_prompt(result)

    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        return parse_json_response(response.content[0].text)
    except Exception as e:
        logger.warning(f"Book enrichment failed: {e}")
        return {}


def enrich_author_metadata(
    author_id: str,
    existing_data: dict,
    client: "Anthropic | None" = None,
) -> dict:
    """Use Claude to enrich author metadata. Returns dict of enriched fields."""
    if client is None:
        try:
            client = create_client()
        except Exception as e:
            logger.warning(f"Could not create Anthropic client: {e}")
            return {}

    prompt = _build_author_prompt(author_id, existing_data)

    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        return parse_json_response(response.content[0].text)
    except Exception as e:
        logger.warning(f"Author enrichment failed: {e}")
        return {}
