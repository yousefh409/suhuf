"""Aligner: legacy token / token-id-span book -> tagged format.

Deterministic, no AI. Joins a block's tokens into `text`, maps every token-id
span onto character offsets, folds poetry hemistichs into `lines`, and renders
the canonical `tagged`. Legacy isnad/matn/takhrij block *types* collapse to a
prose block carrying a span of that label. See the simpler-book-format spec.
"""
from __future__ import annotations

from ingestion.models import Block as LegacyBlock, ParseResult, Footnote as LegacyFootnote
from ingestion import tagged_format as tf
from ingestion.tags import render_tagged

# Legacy block types that are now span labels, not block types.
_SPAN_TYPES = {"isnad", "matn", "takhrij"}


def _flatten_tokens(block: LegacyBlock):
    """Tokens in reading order; for poetry, flatten the hemistich structure."""
    if block.type == "poetry":
        return [t for verse in block.hemistichs for hemi in verse for t in hemi]
    return list(block.tokens)


def _offsets(tokens):
    """Return joined text, joined raw text, and id -> (start, end) char offsets."""
    text, raw, pos, offs, any_raw = "", "", 0, {}, False
    for i, tok in enumerate(tokens):
        if i:
            text += " "
            raw += " "
            pos += 1
        offs[tok.id] = (pos, pos + len(tok.text))
        text += tok.text
        pos += len(tok.text)
        if tok.text_raw is not None:
            any_raw = True
        raw += tok.text_raw if tok.text_raw is not None else tok.text
    return text, (raw if any_raw else None), offs


def _spans(legacy_spans, offs, extra_full_label=None, full_len=0):
    out = []
    if extra_full_label:
        out.append(tf.Span(start=0, end=full_len, label=extra_full_label))
    for s in legacy_spans:
        a = offs.get(s.start_token_id)
        b = offs.get(s.end_token_id)
        if a is None or b is None:
            continue
        out.append(tf.Span(start=a[0], end=b[1], label=s.label,
                           sub=s.sub_label, ref=s.ref, conf=s.confidence))
    return out


def _align_block(block: LegacyBlock) -> tf.Block:
    tokens = _flatten_tokens(block)
    text, raw, offs = _offsets(tokens)

    if block.type == "poetry":
        lines = [[" ".join(t.text for t in hemi) for hemi in verse]
                 for verse in block.hemistichs]
        text = " ".join(h for verse in lines for h in verse)
        tagged = render_tagged(text, [], lines)
        return tf.Block(key=block.key, type="poetry", tagged=tagged, text=text,
                        text_raw=raw, lines=lines, number=block.number,
                        level=block.level, parser_type=block.parser_type,
                        flags=list(block.flags))

    if block.type in _SPAN_TYPES:
        new_type, extra = "prose", block.type
    elif block.type in tf.BLOCK_TYPES:
        new_type, extra = block.type, None
    else:
        new_type, extra = "prose", None

    spans = _spans(block.spans, offs, extra_full_label=extra, full_len=len(text))
    spans.sort(key=lambda s: (s.start, -s.end))
    tagged = render_tagged(text, spans, [])
    return tf.Block(key=block.key, type=new_type, tagged=tagged, text=text,
                    text_raw=raw, spans=spans, number=block.number,
                    level=block.level,
                    parser_type=block.parser_type or (block.type if extra else None),
                    flags=list(block.flags))


def _align_footnote(fn: LegacyFootnote) -> tf.Footnote:
    text, _, _ = _offsets(list(fn.tokens))
    return tf.Footnote(marker=fn.marker, tagged=render_tagged(text, [], []), text=text)


def align_book(result: ParseResult) -> tf.Book:
    pages = []
    for p in result.pages:
        pages.append(tf.Page(
            page_number=p.page_number,
            volume=p.volume,
            blocks=[_align_block(b) for b in p.content_blocks],
            footnotes=[_align_footnote(f) for f in p.footnotes],
        ))
    return tf.Book(metadata=result.metadata, pages=pages, chapters=list(result.chapters))
