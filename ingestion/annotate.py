"""Claude pre-pass that relabels block types and adds inline spans + flags.

Pipeline stage between tashkeel and enrich. Reads a `ParseResult`, sends
its blocks to Claude in chunks, and mutates blocks in-place with:
  - `parser_type` + new `type` when the model is confident enough
  - `spans` for inline labels (Qur'an quotes, names, places, …)
  - `flags` for quality issues (parse_error, tashkeel_suspect, ocr_artifact)

The pass is opt-out via `--skip-annotate` and auto-skips when the parser
already emitted ≥ MIN_NATIVE_TAGS structural blocks.

Failure mode mirrors enrich.py: log warnings, leave blocks untouched.
"""
from __future__ import annotations
import json
import logging
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from anthropic import Anthropic

from ingestion.models import Block, Span, ParseResult, Token

logger = logging.getLogger(__name__)

# Haiku 4.5 — cheap labeling tool. Override via SUHUF_ANNOTATE_MODEL.
DEFAULT_MODEL = "claude-haiku-4-5-20251001"
PROMPT_VERSION = "annotate-v1.0"

# Block-type vocabulary v1. The model returns one of these or "keep" to
# leave the parser type unchanged.
BLOCK_TYPES = [
    "prose",
    "isnad",
    "matn",
    "takhrij",
    "hadith_grading",
    "biography",
    "commentary",
    "quoted_text",
    "editor_note",
    "heading",
    "poetry",
    "hadith",
]

# Span-label vocabulary v2.
SPAN_LABELS = [
    "qur_quote",
    "hadith_quote",
    "book_title",
    "personal_name",
    "place_name",
    "date_hijri",
]

# Quality-flag vocabulary.
QUALITY_FLAGS = [
    "parse_error",
    "tashkeel_suspect",
    "ocr_artifact",
]

# Minimum confidence to accept a structural relabel. Below this we keep
# the parser's type and log the model's suggestion as a metadata hint.
MIN_RELABEL_CONFIDENCE = 0.7

# If the parser already produced >= this many isnad/matn/biography blocks
# the source is already annotated; skip the structural relabel pass.
MIN_NATIVE_TAGS = 10

# Send blocks to the model in chunks of this size. Keeps output well under
# Haiku's per-call cap and bounds error blast radius.
CHUNK_SIZE = 60


def _build_system_prompt() -> str:
    return f"""You are an expert in classical Arabic and Islamic literature (hadith, fiqh, tafsir, sira, tabaqat).

You will be given an array of consecutive text blocks from a classical Arabic book. Each block has:
- "key": its identifier
- "type": the parser's tentative type (often just "prose" because the source was un-annotated)
- "tokens": ordered list of tokens with positions, format [[i, "text"], ...]

For each block, return a JSON object with:
- "key": the block's key (echoed back)
- "type": one of {BLOCK_TYPES} — prefer the parser's type unless you're confident a different type fits better; never invent new types
- "confidence": 0.0–1.0 — your confidence in the type choice
- "spans": array of inline labels, each {{"start": <int>, "end": <int>, "label": <str>, "sub_label"?: <str>, "ref"?: <str>, "confidence": <float>}}, where start/end are token indices (inclusive) and label is one of {SPAN_LABELS}
- "flags": subset of {QUALITY_FLAGS}, empty array if none

Block-type definitions:
- "isnad": chain of transmitters, e.g. "حدثنا/أخبرنا … عن … عن …" leading into a hadith
- "matn": the actual reported text of a hadith, often (but not always) wrapped in « » or "..."
- "takhrij": source attribution after the matn naming which collections recorded it, e.g. "رواه البخاري في صحيحه"
- "hadith_grading": authenticity verdict, e.g. "قال الشيخ الألباني: صحيح" — values reflected in confidence; sub-label optional
- "biography": one entry in a tabaqat/rijal work — a scholar's profile
- "commentary": exegesis/explanation in a sharḥ work
- "quoted_text": the matn or verse the commentary is unpacking (only meaningful inside a sharḥ)
- "editor_note": modern editor's brackets/footnotes mixed into the text
- "heading", "poetry", "prose": leave as-is when the parser already chose them correctly
- "hadith": fallback when the block is clearly hadith-related but you can't split isnad/matn

Span-label definitions:
- "qur_quote": embedded Qur'anic verse. Provide "ref" as "sura:ayah" when confident, e.g. "51:56"
- "hadith_quote": a hadith quoted inline in a non-hadith book
- "book_title": referenced classical work, e.g. "صحيح البخاري", "رياض الصالحين"
- "personal_name": companion / tabii / scholar / prophet name. Use "sub_label" with one of: companion, tabii, scholar, prophet
- "place_name": geographical reference
- "date_hijri": explicit Hijri date in the text

Quality flags:
- "parse_error": block looks malformed (broken nesting, suspicious whitespace, zero-content)
- "tashkeel_suspect": diacritization is obviously wrong on at least one token
- "ocr_artifact": stray non-Arabic characters or mojibake mid-word

Output ONLY a JSON object of the form {{"blocks": [...]}} with one entry per input block, in the same order. No markdown, no explanation."""


def _global_key(page_number: int, block: Block) -> str:
    """Block.key (`b0`, `b1`, …) resets per page, so we synthesize a globally
    unique handle for the model: `p<page>_<key>`. Decoded back to the right
    block on apply."""
    return f"p{page_number}_{block.key}"


def _serialize_block(page_number: int, block: Block) -> dict:
    """Compact wire format: tokens as [index, text] pairs to keep input cheap."""
    if block.type == "poetry":
        # Flatten poetry hemistichs to a single token list for the prompt
        # — model rarely needs to relabel poetry; we just want spans on it.
        flat: list[Token] = [t for verse in block.hemistichs for h in verse for t in h]
    else:
        flat = block.tokens
    return {
        "key": _global_key(page_number, block),
        "type": block.type,
        "tokens": [[i, t.text] for i, t in enumerate(flat)],
    }


def _resolve_token_id(block: Block, idx: int) -> str | None:
    """Translate an in-block token index back to its global token id."""
    if block.type == "poetry":
        flat = [t for verse in block.hemistichs for h in verse for t in h]
    else:
        flat = block.tokens
    if 0 <= idx < len(flat):
        return flat[idx].id
    return None


def _has_native_tags(parse_result: ParseResult) -> bool:
    """True iff the parser already produced enough structural blocks
    that we don't need a relabel pass."""
    n = 0
    for page in parse_result.pages:
        for block in page.content_blocks:
            if block.type in ("isnad", "matn", "biography"):
                n += 1
                if n >= MIN_NATIVE_TAGS:
                    return True
    return False


def _all_blocks(parse_result: ParseResult) -> list[tuple[int, Block]]:
    """Walk every block across pages in document order, paired with its
    page number so we can build globally unique keys."""
    return [(p.page_number, b) for p in parse_result.pages for b in p.content_blocks]


def _chunk(items: list, size: int) -> list[list]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def _parse_response(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        lines = [l for l in text.split("\n") if not l.strip().startswith("```")]
        text = "\n".join(lines)
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        logger.warning(f"Annotation JSON parse failed: {e}; first 200 chars: {text[:200]}")
        return {}


def _apply_block_annotation(block: Block, ann: dict) -> tuple[bool, int, int]:
    """Mutate block in place from one annotation dict.

    Returns (relabeled, span_count, flag_count) for accounting.
    """
    relabeled = False
    span_count = 0
    flag_count = 0

    new_type = ann.get("type")
    conf = ann.get("confidence", 1.0)
    if (
        isinstance(new_type, str)
        and new_type in BLOCK_TYPES
        and new_type != block.type
        and conf is not None
        and conf >= MIN_RELABEL_CONFIDENCE
    ):
        # Preserve the *original* parser type across multiple apply passes —
        # only stash it the first time we mutate the block.
        if block.parser_type is None:
            block.parser_type = block.type
        block.type = new_type
        relabeled = True

    spans_raw = ann.get("spans") or []
    spans: list[Span] = []
    for s in spans_raw:
        try:
            label = s.get("label")
            if label not in SPAN_LABELS:
                continue
            start_idx = int(s["start"])
            end_idx = int(s["end"])
            start_id = _resolve_token_id(block, start_idx)
            end_id = _resolve_token_id(block, end_idx)
            if not start_id or not end_id:
                continue
            spans.append(
                Span(
                    start_token_id=start_id,
                    end_token_id=end_id,
                    label=label,
                    sub_label=s.get("sub_label"),
                    ref=s.get("ref"),
                    confidence=s.get("confidence"),
                )
            )
        except (KeyError, ValueError, TypeError):
            continue
    block.spans = spans
    span_count = len(spans)

    flags_raw = ann.get("flags") or []
    block.flags = [f for f in flags_raw if f in QUALITY_FLAGS]
    flag_count = len(block.flags)

    return relabeled, span_count, flag_count


def create_client() -> "Anthropic":
    from anthropic import Anthropic
    return Anthropic()


def annotate_book(
    parse_result: ParseResult,
    client: "Anthropic | None" = None,
    force: bool = False,
) -> dict:
    """Run the annotation pass on a parsed book, mutating blocks in-place.

    Returns a stats dict for logging.
    """
    stats = {
        "model": os.environ.get("SUHUF_ANNOTATE_MODEL", DEFAULT_MODEL),
        "prompt_version": PROMPT_VERSION,
        "chunks": 0,
        "blocks_seen": 0,
        "relabeled": 0,
        "spans_total": 0,
        "flags_total": 0,
        "errors": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "skipped_native_tags": False,
    }

    if not force and _has_native_tags(parse_result):
        logger.info("Source already has native tags — skipping annotate pass.")
        stats["skipped_native_tags"] = True
        return stats

    if client is None:
        try:
            client = create_client()
        except Exception as e:
            logger.warning(f"Could not create Anthropic client for annotate: {e}")
            return stats

    blocks = _all_blocks(parse_result)
    by_key = {_global_key(pn, b): b for pn, b in blocks}
    stats["blocks_seen"] = len(blocks)

    system = _build_system_prompt()
    model = stats["model"]

    for chunk in _chunk(blocks, CHUNK_SIZE):
        stats["chunks"] += 1
        chunk_keys = {_global_key(pn, b) for pn, b in chunk}
        payload = [_serialize_block(pn, b) for pn, b in chunk]
        user = "Annotate these blocks:\n\n" + json.dumps(payload, ensure_ascii=False)

        try:
            response = client.messages.create(
                model=model,
                max_tokens=8192,
                system=system,
                messages=[{"role": "user", "content": user}],
            )
        except Exception as e:
            logger.warning(f"Annotate API call failed: {e}")
            stats["errors"] += 1
            continue

        try:
            stats["input_tokens"] += response.usage.input_tokens
            stats["output_tokens"] += response.usage.output_tokens
        except AttributeError:
            pass

        body = response.content[0].text if response.content else ""
        parsed = _parse_response(body)
        annotations = parsed.get("blocks") or []

        applied_keys: set[str] = set()
        for ann in annotations:
            key = ann.get("key")
            # Ignore annotations for keys outside the current chunk and skip
            # duplicate annotations for the same key — the model occasionally
            # repeats keys, and re-applying would double-mutate the block.
            if not key or key not in chunk_keys or key not in by_key:
                continue
            if key in applied_keys:
                continue
            applied_keys.add(key)
            relabeled, sc, fc = _apply_block_annotation(by_key[key], ann)
            if relabeled:
                stats["relabeled"] += 1
            stats["spans_total"] += sc
            stats["flags_total"] += fc

    return stats
