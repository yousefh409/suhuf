"""Flow AI structure pass: the model tags a whole passage from scratch.

The pass starts from PLAIN text and asks the model to return the SAME words with
ALL structure added: each hadith wrapped in ``<hadith>`` containing
``<isnad>/<matn>/<takhrij>``, plus the entity tags. Tags are attribute-free; ids
are assigned later by ``assign_ids``.

Each returned chunk is validated with ``compile_tagged``. If it raises
``TagError`` or its tags-stripped text differs from the input chunk, the chunk
falls back to the original plain text (no tags) and is counted in stats. The pass
operates on a list of plain chunks and returns a parallel list of tagged chunks
plus a stats dict. The chunk calls fan out across a thread pool (network-bound).
"""
from __future__ import annotations
import json
import logging
import os
from concurrent.futures import ThreadPoolExecutor

from ingestion.tags import compile_tagged, TagError
from ingestion.tag_transfer import transfer_tags

logger = logging.getLogger(__name__)

PROMPT_VERSION = "annotate-flow-v1"
MODEL = "anthropic/claude-sonnet-4.5"  # via OpenRouter (OpenAI-compatible API)
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
MAX_TOKENS = 16384
MAX_WORKERS = 8


def _system_prompt() -> str:
    return """You tag one passage of classical Arabic / Islamic text (hadith, fiqh, tafsir).

You receive ONE passage of plain Arabic text. Return the SAME text with structure
and entity boundary tags added. Do NOT change, add, or remove any character — the
visible text with every tag removed must be byte-identical to the input.

CRITICAL: preserve EVERY character exactly, including all punctuation and the
quotation guillemets « and » . Do NOT drop, add, normalize, or move any character
(no removing «», no changing diacritics, hamza, or spacing). You ONLY insert tags.

Structure tags:
- Wrap each complete hadith in <hadith>...</hadith>.
- Inside a hadith, wrap the chain of narration in <isnad>...</isnad>, the body of
  the report in <matn>...</matn>, and any sourcing/grading in <takhrij>...</takhrij>.
- Text that is not part of a hadith (chapter titles, author commentary) stays
  untagged.

Entity tags (nest freely inside the structure tags):
- <person> for narrator and other personal names.
- <place> for place names.
- <quran> for a Quran quotation.
- <book_ref> for a cited book title.
- <hadith_ref> for a cross-reference to another hadith.
- <date_hijri> for a Hijri date.

Rules:
- Tags carry NO attributes. Write <person>...</person>, never <person sub="x">.
- Allowed tags only: hadith isnad matn takhrij person place quran book_ref
  hadith_ref date_hijri. Any other tag is an error.
- Tags must nest properly (no crossing).

Return ONLY JSON: {"tagged":"<the tagged passage>"} — no markdown, no explanation."""


def _build_client(client):
    """Return a usable client, or None when one cannot be built offline-safely.

    A caller-supplied client is used as-is. Otherwise an OpenRouter client (the
    OpenAI-compatible SDK pointed at OpenRouter) is built only when
    ``OPENROUTER_API_KEY`` is present, so tests with the key unset never touch the
    network.
    """
    if client is not None:
        return client
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        return None
    try:
        from openai import OpenAI
        return OpenAI(base_url=OPENROUTER_BASE_URL, api_key=key)
    except Exception as e:  # pragma: no cover - construction rarely fails
        logger.warning(f"annotate_flow: could not create client: {e}")
        return None


def annotate_flow(chunks: list[str], client=None) -> tuple[list[str], dict]:
    """Tag each plain chunk with full structure; validate or fall back to plain.

    Returns ``(tagged_chunks, stats)`` where ``tagged_chunks`` is parallel to
    ``chunks``. ``stats`` carries ``chunks``, ``fallbacks`` (validation or API
    failures that reverted to plain), ``api_errors``, ``input_tokens``,
    ``output_tokens``, ``no_client``, ``model``, and ``prompt_version``.
    """
    stats = {"chunks": len(chunks), "fallbacks": 0, "transferred": 0,
             "api_errors": 0, "input_tokens": 0, "output_tokens": 0,
             "no_client": False, "model": MODEL, "prompt_version": PROMPT_VERSION}

    client = _build_client(client)
    if client is None:
        stats["no_client"] = True
        # No AI pass: every chunk passes through as plain text (no tags).
        return list(chunks), stats

    system = _system_prompt()

    def _call(chunk: str):
        """One API call (OpenAI-compatible chat completion). Returns (tagged_or_None, usage)."""
        user = "Tag this passage:\n\n" + json.dumps({"text": chunk}, ensure_ascii=False)
        try:
            resp = client.chat.completions.create(
                model=MODEL, max_tokens=MAX_TOKENS,
                messages=[{"role": "system", "content": system},
                          {"role": "user", "content": user}],
            )
        except Exception as e:
            logger.warning(f"annotate_flow: API call failed: {e}")
            return None, None
        body = resp.choices[0].message.content if resp.choices else ""
        usage = getattr(resp, "usage", None)
        try:
            data = json.loads(body[body.find("{"):body.rfind("}") + 1])
            return data.get("tagged"), usage
        except (ValueError, json.JSONDecodeError):
            return None, usage

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        results = list(ex.map(_call, chunks))

    out: list[str] = []
    for chunk, (tagged, usage) in zip(chunks, results):
        if usage is not None:
            stats["input_tokens"] += getattr(usage, "prompt_tokens", 0) or 0
            stats["output_tokens"] += getattr(usage, "completion_tokens", 0) or 0
        if tagged is None:
            stats["api_errors"] += 1
            stats["fallbacks"] += 1
            out.append(chunk)
            continue
        try:
            plain, _, _ = compile_tagged(tagged)
        except TagError:
            stats["fallbacks"] += 1
            out.append(chunk)
            continue
        if plain != chunk:
            # The model drifted characters (commonly dropped the « » matn marks).
            # Transfer the tags onto the EXACT source via alignment instead of
            # losing the whole chunk's structure; only genuinely garbled output
            # (low alignment similarity) falls back to plain.
            transferred = transfer_tags(tagged, chunk)
            if transferred is not None:
                stats["transferred"] += 1
                out.append(transferred)
            else:
                stats["fallbacks"] += 1
                out.append(chunk)
            continue
        out.append(tagged)

    return out, stats
