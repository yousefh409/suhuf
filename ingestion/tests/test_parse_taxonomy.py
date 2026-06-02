"""Tests for heading-level propagation and takhrij detection using the taxonomy fixture."""
from pathlib import Path

import pytest

from ingestion.parse import parse_file

FIXTURE = Path(__file__).parent / "fixtures" / "taxonomy_sample.mARkdown"


def _heading_blocks(result):
    blocks = []
    for page in result.pages:
        for block in page.content_blocks:
            if block.type == "heading":
                blocks.append(block)
    return blocks


def _isnad_blocks(result):
    blocks = []
    for page in result.pages:
        for block in page.content_blocks:
            if block.type == "isnad":
                blocks.append(block)
    return blocks


def test_heading_levels():
    result = parse_file(FIXTURE, "0000Sample.Taxonomy")
    headings = _heading_blocks(result)
    assert len(headings) == 2, f"Expected 2 heading blocks, got {len(headings)}"

    level1 = headings[0]
    level2 = headings[1]

    assert level1.level == 1, f"Expected level 1, got {level1.level}"
    assert level2.level == 2, f"Expected level 2, got {level2.level}"


def test_isnad_ordinal_extracted():
    """The leading ordinal '١ - ' must be extracted into block.number,
    not left as tokens."""
    result = parse_file(FIXTURE, "0000Sample.Taxonomy")
    isnads = _isnad_blocks(result)
    assert len(isnads) == 1, f"Expected 1 isnad block, got {len(isnads)}"
    isnad = isnads[0]
    assert isnad.number == "١", f"Expected number='١', got {isnad.number!r}"
    assert isnad.tokens[0].text == "عن", (
        f"Expected first token 'عن', got {isnad.tokens[0].text!r}"
    )


def _quran_blocks(result):
    blocks = []
    for page in result.pages:
        for block in page.content_blocks:
            if block.type == "quran":
                blocks.append(block)
    return blocks


def test_quran_block_detected():
    """A standalone ayah line wrapped in ﴿…﴾ must be classified as quran,
    not prose. The bracket glyphs stay in the token text."""
    result = parse_file(FIXTURE, "0000Sample.Taxonomy")
    quran_blocks = _quran_blocks(result)
    assert len(quran_blocks) >= 1, (
        f"Expected at least 1 quran block, got {len(quran_blocks)}; "
        f"all block types: {[b.type for p in result.pages for b in p.content_blocks]}"
    )
    block = quran_blocks[0]
    # In the fixture the line is stored as U+FD3F … U+FD3E (RTL text order).
    assert block.tokens[0].text.startswith("\uFD3F"), (
        f"First token should start with ﴿ (U+FD3F), got {block.tokens[0].text!r}"
    )
    assert block.tokens[-1].text.endswith("\uFD3E"), (
        f"Last token should end with ﴾ (U+FD3E), got {block.tokens[-1].text!r}"
    )


def _takhrij_blocks(result):
    blocks = []
    for page in result.pages:
        for block in page.content_blocks:
            if block.type == "takhrij":
                blocks.append(block)
    return blocks


def test_takhrij_detected():
    """Line starting with رواه after the matn must be classified as takhrij,
    not prose, and its first token must be the keyword itself."""
    result = parse_file(FIXTURE, "0000Sample.Taxonomy")
    takhrijat = _takhrij_blocks(result)
    assert len(takhrijat) >= 1, (
        f"Expected at least 1 takhrij block, got {len(takhrijat)}; "
        f"all block types: {[b.type for p in result.pages for b in p.content_blocks]}"
    )
    takhrij = takhrijat[0]
    assert takhrij.tokens[0].text == "رواه", (
        f"Expected first token 'رواه', got {takhrij.tokens[0].text!r}"
    )


def test_biography_marker_emits_prose_not_biography(tmp_path):
    """biography is a CUT block type. A $BIO_MAN$ marker line must produce a
    prose block (marker prefix stripped, name text preserved) — never biography."""
    src = tmp_path / "bio.mARkdown"
    src.write_text(
        "######OpenITI#\n"
        "#META# 020.BookTITLE\t:: اختبار\n"
        "#META# 00#VERS#LENGTH###\t:: 5\n"
        "#META#Header#End#\n"
        "# PageV01P001\n"
        "### $BIO_MAN$ محمد بن إسماعيل البخاري إمام\n",
        encoding="utf-8",
    )
    result = parse_file(src, "0100Test.BioBook")
    all_blocks = [block for page in result.pages for block in page.content_blocks]

    # No block may have type "biography"
    bio_blocks = [b for b in all_blocks if b.type == "biography"]
    assert bio_blocks == [], (
        f"Expected no biography blocks, got {len(bio_blocks)}: {bio_blocks}"
    )

    # The content must appear as a prose block
    prose_blocks = [b for b in all_blocks if b.type == "prose"]
    assert len(prose_blocks) >= 1, (
        f"Expected at least 1 prose block, got {len(prose_blocks)}; "
        f"all types: {[b.type for b in all_blocks]}"
    )

    all_tokens = [t.text for b in prose_blocks for t in b.tokens]
    # The name text is preserved
    assert "محمد" in all_tokens, (
        f"Expected 'محمد' in prose tokens, got {all_tokens}"
    )
    # The marker prefix is stripped (no $BIO_MAN$ or ### in any token)
    for tok in all_tokens:
        assert "$BIO_MAN$" not in tok, f"Marker prefix leaked into token: {tok!r}"
        assert tok != "###", f"Heading marker leaked into token: {tok!r}"


# ---------------------------------------------------------------------------
# Footnote extraction tests (Task 6)
# ---------------------------------------------------------------------------

_MINIMAL_HEADER = (
    "######OpenITI#\n"
    "#META# 020.BookTITLE\t:: اختبار\n"
    "#META# 00#VERS#LENGTH###\t:: 5\n"
    "#META#Header#End#\n"
)


def test_footnote_correlated_extraction(tmp_path):
    """A body token carrying (١) and a matching definition line on the same page
    must produce a correlated footnote: page.footnotes has one Footnote, the body
    block has a Span(label='footnote', ref='١'), and the definition line does NOT
    become its own content block."""
    src = tmp_path / "fn.mARkdown"
    src.write_text(
        _MINIMAL_HEADER
        + "# PageV01P001\n"
        + "# هذا ثناء عظيم(١) في التفسير\n"
        + "# (١) سقط في نسخة أ\n",
        encoding="utf-8",
    )
    result = parse_file(src, "0100Test.FnBook")
    assert len(result.pages) == 1
    page = result.pages[0]

    # 1. page.footnotes has exactly one footnote
    assert len(page.footnotes) == 1, (
        f"Expected 1 footnote, got {len(page.footnotes)}: {page.footnotes}"
    )
    fn = page.footnotes[0]
    assert fn.marker == "١", f"Expected marker '١', got {fn.marker!r}"
    fn_texts = [t.text for t in fn.tokens]
    assert "سقط" in fn_texts, f"Expected 'سقط' in footnote tokens, got {fn_texts}"

    # 2. footnote token IDs use p1_fn1_wN format
    assert fn.tokens[0].id == "p1_fn1_w0", (
        f"Expected id 'p1_fn1_w0', got {fn.tokens[0].id!r}"
    )

    # 3. The body block has exactly one footnote span pointing at the marker token
    all_fn_spans = [
        span
        for block in page.content_blocks
        for span in block.spans
        if span.label == "footnote"
    ]
    assert len(all_fn_spans) == 1, (
        f"Expected 1 footnote span, got {len(all_fn_spans)}: {all_fn_spans}"
    )
    span = all_fn_spans[0]
    assert span.ref == "١", f"Expected span.ref='١', got {span.ref!r}"
    # start and end token IDs must be the same (single-token span)
    assert span.start_token_id == span.end_token_id, (
        f"Expected single-token span, got {span.start_token_id!r}..{span.end_token_id!r}"
    )

    # 4. The definition line did NOT become a content block
    all_block_texts = [
        t.text for block in page.content_blocks for t in block.tokens
    ]
    # The marker "(١)" itself should not appear as a standalone token in content
    # (definition text may appear as footnote tokens, not body tokens)
    assert "(١)" not in all_block_texts, (
        f"Definition marker '(١)' leaked into content block tokens: {all_block_texts}"
    )


def test_no_footnotes_when_absent():
    """The shared taxonomy_sample.mARkdown has no (N) definition lines.
    Every page must have an empty footnotes list and no block may carry a
    footnote-labelled span."""
    result = parse_file(FIXTURE, "0000Sample.Taxonomy")
    for page in result.pages:
        assert page.footnotes == [], (
            f"Page {page.page_number} unexpectedly has footnotes: {page.footnotes}"
        )
        for block in page.content_blocks:
            fn_spans = [s for s in block.spans if s.label == "footnote"]
            assert fn_spans == [], (
                f"Page {page.page_number} block {block.key} has unexpected footnote spans: {fn_spans}"
            )


def test_footnote_definition_without_marker_dropped(tmp_path):
    """A definition line (٥) with no matching inline marker in the body must be
    dropped entirely: page.footnotes stays empty and the definition text does not
    appear as a prose block."""
    src = tmp_path / "fn_orphan.mARkdown"
    src.write_text(
        _MINIMAL_HEADER
        + "# PageV01P001\n"
        + "# هذا نص عادي بدون علامة هامش\n"
        + "# (٥) تعليق يتيم\n",
        encoding="utf-8",
    )
    result = parse_file(src, "0100Test.OrphanFn")
    assert len(result.pages) == 1
    page = result.pages[0]

    # No footnotes recorded (no matching inline marker)
    assert page.footnotes == [], (
        f"Expected no footnotes, got {page.footnotes}"
    )

    # The definition text did not sneak into any content block
    all_block_texts = [t.text for block in page.content_blocks for t in block.tokens]
    assert "تعليق" not in all_block_texts, (
        f"Orphan definition text 'تعليق' leaked into content blocks: {all_block_texts}"
    )
