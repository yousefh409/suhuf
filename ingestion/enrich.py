"""AI metadata enrichment using Claude API."""
from __future__ import annotations
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from anthropic import Anthropic

from ingestion._client import create_client, parse_json_response
from ingestion import quran as _quran
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


def resolve_spans(result: ParseResult) -> int:
    """Resolve quran spans to sura:ayah refs. Mutates spans in-place.

    Walks every block in every page. For each block, builds a flat ordered
    token list (block.tokens for prose/heading/etc., flattened hemistichs for
    poetry) and an id-to-position map. For each span with label=='quran',
    reconstructs the quoted text by joining token texts from start to end
    (inclusive) and calls quran.lookup_match(). An exact match (the span is a
    whole ayah) overwrites any prior ref; a weaker containment match only fills
    a missing ref, so an authoritative ref from a citation marker is preserved.

    Non-quran spans are left completely untouched.

    Returns the count of spans that were successfully resolved.
    """
    resolved = 0
    for page in result.pages:
        for block in page.content_blocks:
            # Build flat token list
            if block.type == "poetry":
                flat = [
                    t
                    for verse in block.hemistichs
                    for hemistich in verse
                    for t in hemistich
                ]
            else:
                flat = list(block.tokens)

            if not flat:
                continue

            id_to_pos = {t.id: i for i, t in enumerate(flat)}

            for span in block.spans:
                if span.label != "quran":
                    continue

                start_pos = id_to_pos.get(span.start_token_id)
                end_pos = id_to_pos.get(span.end_token_id)
                if start_pos is None or end_pos is None:
                    continue

                quote = " ".join(t.text for t in flat[start_pos:end_pos + 1])
                hit = _quran.lookup_match(quote)
                if hit is None:
                    continue
                sura, ayah, kind = hit
                # Exact matches (the span IS a whole ayah) are authoritative and
                # override any prior ref. Containment matches are weaker — they
                # may only FILL a missing ref, never overwrite one. This guards
                # citation markers like "[آل عمران: ١٨٧]" whose span text reduces
                # to a sura name that coincidentally falls inside one ayah.
                if kind == "exact" or span.ref is None:
                    span.ref = f"{sura}:{ayah}"
                    resolved += 1

    return resolved
