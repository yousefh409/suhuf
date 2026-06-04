"""Transfer AI-authored tags onto the exact source text via alignment.

The flow AI pass echoes a passage with boundary tags added, but LLMs reliably
drift a few characters when echoing Arabic (dropping the «» matn-quote marks,
normalizing hamza/diacritics, touching spacing). A byte-exact, all-or-nothing
check then discards the whole chunk's structure on any drift.

`transfer_tags` keeps the structure without trusting the model's characters: it
strips the tags off the model output, aligns that plain text to the *source*
chunk with difflib, maps each tag's position onto the source, and emits the
SOURCE text with the tags re-inserted. The stored text is therefore always
byte-identical to the source; only genuinely garbled output (low alignment
similarity) falls back to plain.
"""
from __future__ import annotations
import difflib

from ingestion.tags import _TAG_SPLIT, _TAG, compile_tagged, TagError


def _split_tags(tagged: str) -> tuple[str, list[tuple[int, str]]]:
    """Return (plain, tags) where `plain` is the tag-stripped text and `tags` is
    an ordered list of (plain_offset, tag_string): each tag and the position in
    `plain` at which it sits."""
    plain_parts: list[str] = []
    tags: list[tuple[int, str]] = []
    pos = 0
    for part in _TAG_SPLIT.split(tagged):
        if not part:
            continue
        if part.startswith("<") and _TAG.fullmatch(part):
            tags.append((pos, part))
        else:
            plain_parts.append(part)
            pos += len(part)
    return "".join(plain_parts), tags


def _position_map(a: str, b: str) -> list[int]:
    """Map every position 0..len(a) in `a` to a position in `b`, using difflib
    opcodes. Inside an equal run the map is linear; across an edit the interior
    collapses to the run's start and the end pins to the run's end."""
    amap = [0] * (len(a) + 1)
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            for k in range(i2 - i1):
                amap[i1 + k] = j1 + k
            amap[i2] = j2
        else:
            for p in range(i1, i2):
                amap[p] = j1
            amap[i2] = j2
    amap[len(a)] = len(b)
    return amap


def transfer_tags(tagged_ai: str, source: str, min_ratio: float = 0.9) -> str | None:
    """Re-emit `source` carrying the tags from `tagged_ai`, aligned by content.

    Returns the tagged source (whose tags-stripped text is exactly `source`), or
    None when the model output is too different from the source to trust
    (alignment ratio < `min_ratio`) or the rebuilt string fails to compile.
    `tagged_ai` is assumed to already compile (the caller validated it).
    """
    ai_plain, tags = _split_tags(tagged_ai)
    if not tags:
        return source
    if difflib.SequenceMatcher(None, ai_plain, source, autojunk=False).ratio() < min_ratio:
        return None

    amap = _position_map(ai_plain, source)
    out: list[str] = []
    cursor = 0
    for plain_pos, tag_str in tags:
        # Monotonic: a tag can only sit at or after the previously placed one.
        b_pos = max(amap[plain_pos], cursor)
        out.append(source[cursor:b_pos])
        out.append(tag_str)
        cursor = b_pos
    out.append(source[cursor:])
    rebuilt = "".join(out)

    try:
        plain, _, _ = compile_tagged(rebuilt)
    except TagError:
        return None
    if plain != source:
        return None
    return rebuilt
