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

from ingestion._client import create_client, parse_json_response
from ingestion.models import Block, Span, ParseResult, Token

logger = logging.getLogger(__name__)

# Haiku 4.5 — cheap labeling tool. Override via SUHUF_ANNOTATE_MODEL.
DEFAULT_MODEL = "claude-haiku-4-5-20251001"
PROMPT_VERSION = "annotate-v1.0"

# Block-type frozen vocabulary (7 types). The model returns one of these or
# "keep" to leave the parser type unchanged.
BLOCK_TYPES = [
    "prose",
    "heading",
    "poetry",
    "isnad",
    "matn",
    "takhrij",
    "quran",
]

# Span-label frozen vocabulary. The last three structure a running-line hadith
# inline (one block, parts as spans) for books without native @MATN@ tags.
SPAN_LABELS = [
    "quran",
    "person",
    "place",
    "book_ref",
    "hadith_ref",
    "date_hijri",
    "isnad",
    "matn",
    "takhrij",
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

# If the parser already produced >= this many isnad/matn blocks
# the source is already annotated; skip the structural relabel sub-pass
# (spans and flags still apply).
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
- "spans": structural spans already detected, format [[start, end, label, confidence], ...]. isnad/matn/takhrij spans here are PRE-DETECTED — do NOT re-add them. For a block with NO structural spans you may add them. You MAY correct a structural span only if its confidence is below 0.9; never touch one at 0.9 or above. Always add entity spans (person/place/quran/book_ref/hadith_ref/date_hijri) regardless.

For each block, return a JSON object with:
- "key": the block's key (echoed back)
- "type": one of {BLOCK_TYPES} — prefer the parser's type unless you're confident a different type fits better; never invent new types
- "confidence": 0.0–1.0 — your confidence in the type choice
- "spans": array of inline labels, each {{"start": <int>, "end": <int>, "label": <str>, "sub_label"?: <str>, "ref"?: <str>, "confidence": <float>}}, where start/end are token indices (inclusive) and label is one of {SPAN_LABELS}
- "flags": subset of {QUALITY_FLAGS}, empty array if none

Block-type definitions:
- "prose": general running text (default when no more specific type applies)
- "heading": section or chapter heading
- "poetry": verse in metered form; hemistichs separated by a caesura. Poetry is detected upstream and is parser-owned: never relabel a block TO poetry, and never relabel a block whose type is already poetry to something else — leave poetry blocks' type unchanged (you may still add spans to them)
- "isnad": chain of transmitters, e.g. "حدثنا/أخبرنا … عن … عن …" leading into a hadith
- "matn": the actual reported text of a hadith, often (but not always) wrapped in « » or "..."
- "takhrij": source attribution after the matn naming which collections recorded it, e.g. "رواه البخاري في صحيحه"
- "quran": a block whose primary content is a Qur'anic verse or multi-verse passage (not an inline citation inside prose — use the quran span label for those)

Span-label definitions:
- "quran": embedded Qur'anic citation within a prose or matn block. Provide "ref" as "sura:ayah" when you can — this is your best guess and will be overridden by a deterministic verification pass later
- "person": a named individual. Use "sub_label" with one of: companion, tabii, scholar, prophet, caliph
- "place": geographical reference (city, region, land)
- "book_ref": referenced classical work, e.g. "صحيح البخاري", "رياض الصالحين"
- "hadith_ref": a hadith quoted inline in a non-hadith context
- "date_hijri": explicit Hijri date in the text
- "isnad": the chain-of-transmission portion of a hadith that sits inline within a single running block (use this span, not a block relabel, when isnad and matn share one line/paragraph)
- "matn": the reported-text portion of a hadith that sits inline within a single running block
- "takhrij": the source-attribution tail (e.g. "رواه البخاري") of a hadith that sits inline within a single running block

For a hadith laid out across SEPARATE lines (separate blocks), prefer relabeling each block's "type" to isnad/matn/takhrij. For a hadith on ONE running line, emit these as spans on a single block — do not do both.

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
    idmap = {t.id: i for i, t in enumerate(flat)}
    spans = []
    for s in block.spans:
        a, b = idmap.get(s.start_token_id), idmap.get(s.end_token_id)
        if a is not None and b is not None:
            spans.append([min(a, b), max(a, b), s.label, s.confidence])
    return {
        "key": _global_key(page_number, block),
        "type": block.type,
        "tokens": [[i, t.text] for i, t in enumerate(flat)],
        "spans": spans,
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


def _token_index_map(block: Block) -> dict[str, int]:
    """Map each token id in *block* to its flat position."""
    if block.type == "poetry":
        flat = [t for verse in block.hemistichs for h in verse for t in h]
    else:
        flat = block.tokens
    return {t.id: i for i, t in enumerate(flat)}


def _span_range(span: Span, idmap: dict[str, int]) -> tuple[int, int] | None:
    """Return a span's (low, high) token index range, or None if unmappable."""
    a = idmap.get(span.start_token_id)
    b = idmap.get(span.end_token_id)
    if a is None or b is None:
        return None
    return (min(a, b), max(a, b))


def _ranges_overlap(a: tuple[int, int], b: tuple[int, int]) -> bool:
    return a[0] <= b[1] and b[0] <= a[1]


def _has_native_tags(parse_result: ParseResult) -> bool:
    """True iff the parser already produced enough structural blocks
    that we should skip the structural relabel sub-pass (spans and flags still apply)."""
    n = 0
    for page in parse_result.pages:
        for block in page.content_blocks:
            if block.type in ("isnad", "matn"):
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


def _apply_block_annotation(
    block: Block, ann: dict, allow_relabel: bool = False
) -> tuple[bool, int, int]:
    """Mutate block in place from one annotation dict.

    Returns (relabeled, span_count, flag_count) for accounting.
    """
    relabeled = False
    span_count = 0
    flag_count = 0

    new_type = ann.get("type")
    conf = ann.get("confidence", 1.0)
    if (
        allow_relabel
        and isinstance(new_type, str)
        and new_type in BLOCK_TYPES
        and new_type != block.type
        # Poetry is parser-owned in BOTH directions: its content lives in
        # `hemistichs`, not `tokens`. Relabeling TO poetry (no hemistichs to
        # build) or FROM poetry (orphans the hemistichs under a tokens-based
        # renderer) renders blank. Never relabel across the poetry boundary.
        and new_type != "poetry"
        and block.type != "poetry"
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
    # Merge with spans parse already emitted (citation-anchored Qur'an,
    # footnotes). Those are deterministic and authoritative, so the model's
    # spans must not clobber them: drop any model span that overlaps a parse
    # span, and — where parse already found a cited ayah — drop the model's
    # Qur'an spans entirely (they would otherwise duplicate onto the trailing
    # citation bracket). The model still owns every other label.
    preserved = list(block.spans)
    idmap = _token_index_map(block)
    preserved_ranges = [r for r in (_span_range(s, idmap) for s in preserved) if r]
    preserved_has_quran = any(s.label == "quran" for s in preserved)

    kept: list[Span] = []
    for cs in spans:
        rng = _span_range(cs, idmap)
        if rng and any(_ranges_overlap(rng, pr) for pr in preserved_ranges):
            continue
        if cs.label == "quran" and preserved_has_quran:
            continue
        kept.append(cs)

    block.spans = preserved + kept
    span_count = len(kept)

    flags_raw = ann.get("flags") or []
    block.flags = [f for f in flags_raw if f in QUALITY_FLAGS]
    flag_count = len(block.flags)

    return relabeled, span_count, flag_count


def annotate_book(
    parse_result: ParseResult,
    client: "Anthropic | None" = None,
    force: bool = False,
) -> dict:
    """Run the annotation pass on a parsed book, mutating blocks in-place.

    When the parser already produced >= MIN_NATIVE_TAGS structural blocks and
    force is False, relabel_allowed is False and block types are left unchanged,
    but spans and flags are still detected and written.

    Returns a stats dict for logging.
    """
    allow_relabel = force or not _has_native_tags(parse_result)

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
        "relabel_allowed": allow_relabel,
    }

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
        parsed = parse_json_response(body)
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
            relabeled, sc, fc = _apply_block_annotation(by_key[key], ann, allow_relabel=allow_relabel)
            if relabeled:
                stats["relabeled"] += 1
            stats["spans_total"] += sc
            stats["flags_total"] += fc

    return stats
