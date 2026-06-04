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

    # Walk boundary points; keep a stack of open spans. Spans may partially
    # cross (an entity straddling a structural edge), which tags cannot express
    # directly — so close-and-reopen: to close a span that is not on top, close
    # the spans above it, close it, then reopen the survivors. This yields valid
    # nested markup for ANY span set (crossing spans are split into pieces).
    points = sorted({0, len(text)}
                    | {s.start for s in spans} | {s.end for s in spans})
    starts: dict[int, list] = {}
    for s in spans:
        starts.setdefault(s.start, []).append(s)
    # Open wider spans first so nesting is stable.
    for p in starts:
        starts[p].sort(key=lambda s: (-(s.end), s.label))

    out, stack, pos = [], [], 0
    for p in points:
        if p > pos:
            out.append(_escape(text[pos:p]))
            pos = p
        if any(s.end == p for s in stack):
            lo = min(i for i, s in enumerate(stack) if s.end == p)
            reopen = []
            while len(stack) > lo:
                top = stack.pop()
                out.append(f"</{top.label}>")
                if top.end != p:
                    reopen.append(top)
            for s in reversed(reopen):
                out.append(f"<{s.label}>")
                stack.append(s)
        for s in starts.get(p, []):
            out.append(f"<{s.label}>")
            stack.append(s)
    return "".join(out)
