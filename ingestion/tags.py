"""Tag compiler: canonical `tagged` text <-> (text, spans, lines).

`compile_tagged` strips boundary tags to produce clean `text`, records inline
tags as character-offset spans (label only), and folds `verse`/`hemistich` into
`lines`. `render_tagged` is the inverse, emitting canonical boundary tags from
offsets. Tags carry no attributes; metadata lives on the resolved span.
"""
from __future__ import annotations
import re

from ingestion.tagged_format import Span, INLINE_TAGS, STRUCT_TAGS


class TagError(ValueError):
    """Malformed tagged text: unknown tag, bad nesting, or unclosed tag."""


_TAG_SPLIT = re.compile(r"(<[^>]+>)")
# Lenient: tolerate (and ignore) any attributes the canonical form never emits.
_TAG = re.compile(r"<\s*(/?)\s*([a-z_]+)(?:\s[^>]*)?>")


def _unescape(s: str) -> str:
    return s.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")


def _escape(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def compile_tagged(tagged: str) -> tuple[str, list[Span], list[list[str]]]:
    """Return (text, spans, lines) for a canonical tagged string."""
    text = ""
    spans: list[Span] = []
    lines: list[list[str]] = []
    stack: list[list] = []   # [name, start_offset, collected_hemistichs]

    for part in _TAG_SPLIT.split(tagged):
        if not part:
            continue
        if part.startswith("<"):
            m = _TAG.fullmatch(part)
            if not m:
                raise TagError(f"malformed tag: {part!r}")
            closing, name = m.group(1), m.group(2)
            if name not in INLINE_TAGS and name not in STRUCT_TAGS:
                raise TagError(f"unknown tag: {name!r}")
            if not closing:
                stack.append([name, len(text), []])
            else:
                if not stack or stack[-1][0] != name:
                    raise TagError(f"mismatched closing tag: </{name}>")
                _, start, collected = stack.pop()
                if name in INLINE_TAGS:
                    spans.append(Span(start=start, end=len(text), label=name))
                elif name == "hemistich":
                    if not stack or stack[-1][0] != "verse":
                        raise TagError("hemistich outside verse")
                    stack[-1][2].append(text[start:len(text)])
                elif name == "verse":
                    lines.append(collected)
        else:
            text += _unescape(part)

    if stack:
        raise TagError(f"unclosed tag: <{stack[-1][0]}>")

    if lines:
        # Poetry: derived text is the hemistichs joined for search/rendering;
        # structure lives in `lines`, so inline spans are not used here.
        text = " ".join(h for verse in lines for h in verse)
    return text, spans, lines


def render_tagged(text: str, spans: list[Span], lines: list[list[str]]) -> str:
    """Inverse of compile_tagged: emit canonical boundary tags (no attributes)."""
    if lines:
        out = []
        for verse in lines:
            out.append("<verse>")
            for hemi in verse:
                out.append(f"<hemistich>{_escape(hemi)}</hemistich>")
            out.append("</verse>")
        return "".join(out)

    # Order at a shared offset: closes before opens; among opens widest-first;
    # among closes innermost-first (LIFO), so nesting stays well-formed.
    events = []
    for s in spans:
        events.append((s.start, 1, -s.end, s))    # open
        events.append((s.end, 0, -s.start, s))     # close
    events.sort(key=lambda e: (e[0], e[1], e[2]))

    out, pos = [], 0
    for ev_pos, is_open, _, s in events:
        if ev_pos > pos:
            out.append(_escape(text[pos:ev_pos]))
            pos = ev_pos
        out.append(f"<{s.label}>" if is_open else f"</{s.label}>")
    if pos < len(text):
        out.append(_escape(text[pos:]))
    return "".join(out)
