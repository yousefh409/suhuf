"""Tagged annotate pass: the AI authors boundary tags over compact tagged text.

Replaces the token-index annotate for the new format. The model receives each
block's `tagged` text and returns it with entity tags added (nesting inside the
structural tags) and low-confidence boundaries optionally corrected. A
deterministic gated merge over offset spans locks high-confidence detector
boundaries. Output is compact, so it does not hit the token-array truncation,
and entity tags nest inside structural ones instead of being dropped.
"""
from __future__ import annotations
import json
import logging
from concurrent.futures import ThreadPoolExecutor

from ingestion import tagged_format as tf
from ingestion.tags import compile_tagged, render_tagged, TagError

logger = logging.getLogger(__name__)

PROMPT_VERSION = "annotate-tagged-v1"
MODEL = "anthropic/claude-sonnet-4.6"
CHUNK_SIZE = 30
MAX_TOKENS = 16384
MAX_WORKERS = 8
LOCK_THRESHOLD = 0.9
_STRUCT = {"isnad", "matn", "takhrij"}


def _overlaps(a: tf.Span, b: tf.Span) -> bool:
    return a.start < b.end and b.start < a.end


def merge_spans(detector: list[tf.Span], ai: list[tf.Span]) -> list[tf.Span]:
    """Lock high-confidence detector structural spans; take AI entity spans
    (which nest freely) and AI structural spans where they do not collide with a
    locked one."""
    locked = [s for s in detector if s.label in _STRUCT and (s.conf or 0) >= LOCK_THRESHOLD]
    out = list(locked)
    for s in ai:
        if s.label in _STRUCT:
            if any(_overlaps(s, l) for l in locked):
                continue
            out.append(s)
        else:
            out.append(s)
    out.sort(key=lambda s: (s.start, -s.end))
    return out


def _system_prompt() -> str:
    return """You annotate classical Arabic and Islamic texts (hadith, fiqh, tafsir).

You receive an array of text blocks. Each block has a "key" and "tagged" text
that already contains boundary tags for hadith structure: <isnad>, <matn>,
<takhrij>. Your job:

1. Add ENTITY boundary tags inside the text, nesting freely inside the structural
   tags: <person>, <place>, <quran>, <book_ref>, <hadith_ref>, <date_hijri>.
   Tag every narrator name in an isnad as <person>.
2. Keep the existing <isnad>/<matn>/<takhrij> tags. You may correct a boundary
   only if it is clearly wrong; otherwise leave them unchanged.
3. DO NOT change the words. Only add or adjust tags. The visible text with all
   tags removed must be byte-identical to the input.
4. Tags carry NO attributes. Write <person>...</person>, never <person sub="x">.

Allowed tags only: isnad matn takhrij person place quran book_ref hadith_ref
date_hijri. Any other tag is an error.

Return ONLY JSON: {"blocks":[{"key":"...","tagged":"..."}]}, one entry per input
block, in the same order, no markdown, no explanation."""


def annotate_book_tagged(book: tf.Book, client=None) -> dict:
    """Annotate a tagged-format book in place. Returns a stats dict."""
    stats = {"chunks": 0, "blocks_sent": 0, "entity_spans": 0, "text_mismatch": 0,
             "tag_errors": 0, "api_errors": 0, "input_tokens": 0, "output_tokens": 0,
             "model": MODEL, "prompt_version": PROMPT_VERSION}
    if client is None:
        try:
            from ingestion._client import create_client
            client = create_client()
        except Exception as e:
            logger.warning(f"annotate_tagged: could not create client: {e}")
            return stats

    blocks = [b for p in book.pages for b in p.blocks]
    # Only annotate text-bearing, non-poetry blocks (poetry lives in `lines`).
    targets = [(i, b) for i, b in enumerate(blocks)
               if b.type != "poetry" and b.text.strip()]
    system = _system_prompt()
    chunks = [targets[ci:ci + CHUNK_SIZE] for ci in range(0, len(targets), CHUNK_SIZE)]

    def _call(chunk):
        """One API call for a chunk. Returns (anns, usage) or (None, None)."""
        payload = [{"key": str(idx), "tagged": b.tagged} for idx, b in chunk]
        user = "Annotate these blocks:\n\n" + json.dumps(payload, ensure_ascii=False)
        try:
            resp = client.messages.create(
                model=MODEL, max_tokens=MAX_TOKENS, system=system,
                messages=[{"role": "user", "content": user}],
            )
        except Exception as e:
            logger.warning(f"annotate_tagged: API call failed: {e}")
            return None, None
        body = resp.content[0].text if resp.content else ""
        usage = getattr(resp, "usage", None)
        try:
            data = json.loads(body[body.find("{"):body.rfind("}") + 1])
            return (data.get("blocks") or []), usage
        except (ValueError, json.JSONDecodeError):
            return None, usage

    # Fan the chunk calls out concurrently (the slow part is network I/O), then
    # apply the merges single-threaded so block mutation and stats stay simple.
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        results = list(ex.map(_call, chunks))

    for chunk, (anns, usage) in zip(chunks, results):
        stats["chunks"] += 1
        stats["blocks_sent"] += len(chunk)
        if usage is not None:
            stats["input_tokens"] += getattr(usage, "input_tokens", 0)
            stats["output_tokens"] += getattr(usage, "output_tokens", 0)
        if anns is None:
            stats["api_errors"] += 1
            continue
        for ann in anns:
            try:
                idx = int(ann.get("key"))
            except (TypeError, ValueError):
                continue
            if not (0 <= idx < len(blocks)):
                continue
            b = blocks[idx]
            try:
                ai_text, ai_spans, _ = compile_tagged(ann.get("tagged", ""))
            except TagError:
                stats["tag_errors"] += 1
                continue
            if ai_text != b.text:
                # The model altered the words; keep the deterministic output.
                stats["text_mismatch"] += 1
                continue
            merged = merge_spans(b.spans, ai_spans)
            b.spans = merged
            b.tagged = render_tagged(b.text, merged, b.lines)
            stats["entity_spans"] += sum(1 for s in merged if s.label not in _STRUCT)

    return stats
