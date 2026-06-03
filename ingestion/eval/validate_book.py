"""Layered validator for a tagged-format book.

Checks from the block layer up so low-level errors surface before higher ones:
  L0 blocks  - text parity vs source, tagged round-trips, valid types/offsets
  L1 struct  - hadith spans sane, no matn truncations, poetry lines intact
  L2 entity  - entity spans present, no orphaned/invalid refs

Usage: python -m ingestion.eval.validate_book <uri> [--corpus-path ./RELEASE]
Reads web/data/<uri>.book.json. Exits non-zero if any hard check fails.
"""
from __future__ import annotations
import argparse
import json
import re
import sys
from pathlib import Path

_PAGE_TOKEN = re.compile(r"PageV\d+P\d+")

from ingestion import tagged_format as tf
from ingestion.tags import compile_tagged, render_tagged
from ingestion.parse import parse_file
from ingestion.corpus import find_book_file

_INLINE = tf.INLINE_TAGS
_STRUCT = {"isnad", "matn", "takhrij"}


def _fails(label, items, show=5):
    """Print a check line; return 1 if there are items (failures), else 0."""
    n = len(items)
    mark = "ok  " if n == 0 else "FAIL"
    print(f"  [{mark}] {label}: {n}")
    for it in items[:show]:
        print(f"          - {it}")
    return n


def validate(uri: str, corpus_path: str) -> int:
    book = tf.Book.model_validate(json.loads(
        Path(f"web/data/{uri}.book.json").read_text(encoding="utf-8")))
    blocks = [b for p in book.pages for b in p.blocks]
    hard = 0

    print(f"== {uri}: {len(book.pages)} pages, {len(blocks)} blocks ==")

    # ---- L0: blocks ----
    print("L0 blocks")
    # text parity vs a fresh legacy parse (no data loss in the aligner)
    legacy = parse_file(find_book_file(uri, corpus_path=corpus_path), uri)
    legacy_words = " ".join(p.content_plain for p in legacy.pages).split()
    new_words = " ".join(b.text for b in blocks).split()
    parity = [] if legacy_words == new_words else [
        f"word count {len(new_words)} != source {len(legacy_words)}"]
    hard += _fails("text parity vs source", parity)

    bad_rt = [b.key for b in blocks
              if render_tagged(*compile_tagged(b.tagged)) != b.tagged]
    hard += _fails("tagged round-trip", bad_rt)

    bad_type = [f"{b.key}:{b.type}" for b in blocks if b.type not in tf.BLOCK_TYPES]
    hard += _fails("block type in {prose,heading,poetry,quran}", bad_type)

    bad_off = []
    for b in blocks:
        for s in b.spans:
            if not (0 <= s.start < s.end <= len(b.text)):
                bad_off.append(f"{b.key} {s.label} [{s.start},{s.end}) len={len(b.text)}")
            if s.label not in _INLINE:
                bad_off.append(f"{b.key} bad label {s.label}")
    hard += _fails("span offsets in range + valid label", bad_off)

    empty = [b.key for b in blocks
             if b.type != "poetry" and not b.text.strip()
             or b.type == "poetry" and not b.lines]
    hard += _fails("no empty blocks", empty)

    leaked = [b.key for b in blocks if _PAGE_TOKEN.search(b.text)]
    hard += _fails("no page-marker tokens leaked into text", leaked)

    # ---- L1: structure ----
    print("L1 structure")
    by_text = {id(b): b for b in blocks}
    def seg(b, s):
        return b.text[s.start:s.end]
    trunc = []
    for i, b in enumerate(blocks):
        for s in b.spans:
            if s.label == "matn":
                m = seg(b, s)
                if "«" in m and "»" not in m:
                    nxt = blocks[i + 1] if i + 1 < len(blocks) else None
                    cont = nxt and ("»" in nxt.text or any(
                        x.label == "matn" for x in nxt.spans))
                    if not cont:
                        trunc.append(f"{b.key}: …{m[-25:]}")
    hard += _fails("matn truncations (open « unclosed)", trunc)

    bad_poetry = [b.key for b in blocks if b.type == "poetry"
                  and (not b.lines or any(not h for v in b.lines for h in v))]
    hard += _fails("poetry blocks have non-empty lines", bad_poetry)

    # ---- L2: entities (soft: report, do not fail) ----
    print("L2 entities (report)")
    from collections import Counter
    labs = Counter(s.label for b in blocks for s in b.spans)
    print("  span labels:", dict(labs))
    quran = [s for b in blocks for s in b.spans if s.label == "quran"]
    refd = sum(1 for s in quran if s.ref)
    print(f"  quran spans: {len(quran)} ({refd} with ref)")

    print(f"== {uri}: {'ALL HARD CHECKS PASS' if hard == 0 else f'{hard} HARD FAILURES'} ==\n")
    return hard


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("uri")
    ap.add_argument("--corpus-path", default="./RELEASE")
    args = ap.parse_args()
    sys.exit(1 if validate(args.uri, args.corpus_path) else 0)


if __name__ == "__main__":
    main()
