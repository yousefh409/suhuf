from __future__ import annotations

import re
from pathlib import Path

from ingestion.models import Token, Block, Footnote, Page, Chapter, ParseResult, Span
from ingestion.metadata import parse_file_header

_PAGE_RE = re.compile(r"PageV(\d+)P(\d+)")
_HEADING_RE = re.compile(r"^###\s+(\|+)\s+(.*)")
_EDITOR_RE = re.compile(r"^###\s+\|EDITOR\|")
_HADITH_RE = re.compile(r"^\$RWY\$\s*(.*)")
_BIO_MARKER_RE = re.compile(r"^###\s+\$(?:BIO_MAN|BIO_WOM|\$?)\$?\s*(.*)")
# Matches a leading printed ordinal: one or more digits (Arabic-Indic U+0660–U+0669
# or ASCII 0–9) optionally followed by a separator (-, ., ), ،) with surrounding spaces.
_ORDINAL_RE = re.compile(r"^([\u0660-\u06690-9]+)\s*[-.)،]\s*")
# OpenITI milestone tokens (msNN) split each printed page into ~300-word chunks
# for the project's NLP alignment tooling. They have no meaning for human
# readers; strip them inline before tokenization.
_MILESTONE_RE = re.compile(r"\bms\d+\b")

# ---------------------------------------------------------------------------
# Footnote extraction — provisional, conservative, correlation-gated.
#
# Cleaned OpenITI corpora strip footnotes, so these structures will almost
# always be EMPTY.  The primary design goal is zero false positives on real
# body text: a stray parenthesised number must NEVER be mis-classified as a
# footnote anchor.
#
# Convention (both conditions must hold on the SAME PAGE to activate):
#   1. Definition line: a content line whose cleaned text matches
#      _FOOTNOTE_DEF_RE (starts with a parenthesised number then note text).
#      Such a line is held as a pending definition and NOT emitted as a block.
#   2. Inline marker token: a body token whose text equals or ends with (N).
#      Detected during page-flush correlation after all blocks are built.
#
# If only one side exists, nothing is recorded (dropped silently).
# ---------------------------------------------------------------------------
_FOOTNOTE_DEF_RE = re.compile(
    r"^\(([0-9\u0660-\u0669]+)\)\s+(.+)$"
)
# Matches a token that IS a footnote marker or ENDS with one, e.g. "عظيم(١)"
_FOOTNOTE_MARKER_RE = re.compile(r"\(([0-9\u0660-\u0669]+)\)$")

# First-word keywords that identify a takhrij (source-attribution) line.
# Matched against the first whitespace-delimited token only.
_TAKHRIJ_KEYWORDS: tuple[str, ...] = ("رواه", "أخرجه", "أخرجها", "رواها", "متفق")

# Ornate Quranic bracket glyphs.
_QURAN_OPEN = "\uFD3F"   # ﴿ U+FD3F ORNATE RIGHT PARENTHESIS — opens the ayah
_QURAN_CLOSE = "\uFD3E"  # ﴾ U+FD3E ORNATE LEFT PARENTHESIS  — closes the ayah


def _extract_leading_ordinal(text: str) -> tuple[str | None, str]:
    """Extract a leading printed ordinal from text.

    Returns (digit_string, remaining_text) if an ordinal prefix is found,
    or (None, original_text) if not.  The digit string contains only the
    digit characters (e.g. '١'), not the separator.
    """
    m = _ORDINAL_RE.match(text)
    if m:
        return m.group(1), text[m.end():]
    return None, text


def _tokenize(text: str, page_num: int, block_idx: int) -> list[Token]:
    """Split text into word tokens with deterministic IDs."""
    words = text.split()
    return [
        Token(id=f"p{page_num}_b{block_idx}_w{i}", text=w)
        for i, w in enumerate(words)
    ]


def parse_file(path: Path, openiti_uri: str) -> ParseResult:
    """Parse an OpenITI mARkdown file into structured pages, blocks, and chapters."""
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()

    # Metadata pass
    metadata = parse_file_header(lines, openiti_uri)

    # Find body start
    body_start = 0
    for i, line in enumerate(lines):
        if line.strip() == "#META#Header#End#":
            body_start = i + 1
            break

    # State
    pages: list[Page] = []
    chapters: list[Chapter] = []
    current_blocks: list[Block] = []
    current_page_num = 0
    current_volume = 1
    in_hadith = False
    hadith_words: list[str] = []
    hadith_number: str | None = None
    pending_text = ""
    chapter_sort = 0
    # Footnote definitions collected during current page (marker -> note_text).
    # Resolved at _flush_page via correlation with inline markers in body tokens.
    pending_fn_defs: dict[str, str] = {}

    def _flush_hadith():
        """Flush accumulated hadith words as an isnad block."""
        nonlocal hadith_words, in_hadith, hadith_number
        if not hadith_words:
            in_hadith = False
            hadith_number = None
            return
        block_idx = len(current_blocks)
        tokens = [
            Token(id=f"p{current_page_num}_b{block_idx}_w{i}", text=w)
            for i, w in enumerate(hadith_words)
        ]
        current_blocks.append(Block(key=f"b{block_idx}", type="isnad", tokens=tokens, number=hadith_number))
        hadith_words = []
        in_hadith = False
        hadith_number = None

    def _dispatch(line_text: str):
        """Process a complete content line (after stripping prefix and joining continuations)."""
        nonlocal in_hadith, hadith_words, hadith_number, chapter_sort

        # Drop OpenITI milestone markers (msNN); they are tooling artifacts, not text.
        line_text = _MILESTONE_RE.sub("", line_text)
        line_text = re.sub(r"\s{2,}", " ", line_text).strip()
        if not line_text:
            return

        # Editor lines - skip
        if _EDITOR_RE.match(line_text):
            return

        # Heading
        m = _HEADING_RE.match(line_text)
        if m:
            _flush_hadith()
            level = len(m.group(1))
            title = m.group(2).strip()
            block_idx = len(current_blocks)
            tokens = _tokenize(title, current_page_num, block_idx)
            current_blocks.append(Block(key=f"b{block_idx}", type="heading", level=level, tokens=tokens))
            chapter_sort += 1
            chapters.append(Chapter(
                title=title,
                level=level,
                page_number=current_page_num,
                sort_order=chapter_sort,
                block_index=block_idx,
            ))
            return

        # Hadith start ($RWY$)
        m = _HADITH_RE.match(line_text)
        if m:
            _flush_hadith()
            in_hadith = True
            hadith_words = []
            hadith_number = None
            remainder = m.group(1).strip()
            if remainder:
                hadith_number, remainder = _extract_leading_ordinal(remainder)
                if remainder:
                    hadith_words.extend(remainder.split())
            return

        # Poetry (check before @MATN@ since %~% is unambiguous)
        if "%~%" in line_text:
            _flush_hadith()
            parts = line_text.split("%~%")
            block_idx = len(current_blocks)
            hemistichs = []
            w_idx = 0
            for part in parts:
                words = part.strip().split()
                h_tokens = [
                    Token(id=f"p{current_page_num}_b{block_idx}_w{w_idx + j}", text=w)
                    for j, w in enumerate(words)
                ]
                w_idx += len(words)
                if h_tokens:
                    hemistichs.append(h_tokens)
            if hemistichs:
                current_blocks.append(
                    Block(key=f"b{block_idx}", type="poetry", hemistichs=[hemistichs])
                )
            return

        # @MATN@ boundary (only meaningful in hadith mode)
        if "@MATN@" in line_text and in_hadith:
            before, _, after = line_text.partition("@MATN@")
            if before.strip():
                hadith_words.extend(before.strip().split())
            # Flush accumulated words as isnad
            block_idx = len(current_blocks)
            tokens = [
                Token(id=f"p{current_page_num}_b{block_idx}_w{i}", text=w)
                for i, w in enumerate(hadith_words)
            ]
            current_blocks.append(Block(key=f"b{block_idx}", type="isnad", tokens=tokens, number=hadith_number))
            hadith_words = []
            in_hadith = False
            hadith_number = None
            # Create matn block from text after @MATN@
            if after.strip():
                block_idx = len(current_blocks)
                tokens = _tokenize(after.strip(), current_page_num, block_idx)
                current_blocks.append(Block(key=f"b{block_idx}", type="matn", tokens=tokens))
            return

        # Biography markers — "biography" is a CUT type; fall back to prose.
        # Strip the $BIO_MAN$/$BIO_WOM$ marker prefix and emit the remainder as prose.
        m = _BIO_MARKER_RE.match(line_text)
        if m:
            _flush_hadith()
            remainder = m.group(1).strip()
            if remainder:
                prose_number, remainder = _extract_leading_ordinal(remainder)
                block_idx = len(current_blocks)
                tokens = _tokenize(remainder, current_page_num, block_idx)
                if tokens:
                    current_blocks.append(Block(key=f"b{block_idx}", type="prose", tokens=tokens, number=prose_number))
            return

        # Accumulate text in hadith mode
        if in_hadith:
            hadith_words.extend(line_text.strip().split())
            return

        # Quran: standalone ayah line wrapped in ornate brackets ﴿…﴾
        candidate = line_text.strip()
        if candidate.startswith(_QURAN_OPEN) and candidate.endswith(_QURAN_CLOSE):
            quran_number, quran_text = _extract_leading_ordinal(candidate)
            block_idx = len(current_blocks)
            tokens = _tokenize(quran_text, current_page_num, block_idx)
            if tokens:
                current_blocks.append(Block(key=f"b{block_idx}", type="quran", tokens=tokens, number=quran_number))
            return

        # Takhrij: source-attribution line identified by its first word
        parts = candidate.split()
        first_word = parts[0] if parts else ""
        if first_word in _TAKHRIJ_KEYWORDS:
            takhrij_number, takhrij_text = _extract_leading_ordinal(candidate)
            block_idx = len(current_blocks)
            tokens = _tokenize(takhrij_text, current_page_num, block_idx)
            if tokens:
                current_blocks.append(Block(key=f"b{block_idx}", type="takhrij", tokens=tokens, number=takhrij_number))
            return

        # Footnote definition line: (N) note text — hold as pending, do NOT emit a block.
        # Correlated with inline markers at page flush; unmatched definitions are dropped.
        m = _FOOTNOTE_DEF_RE.match(line_text.strip())
        if m:
            pending_fn_defs[m.group(1)] = m.group(2)
            return

        # Default: prose
        prose_text = line_text.strip()
        prose_number, prose_text = _extract_leading_ordinal(prose_text)
        block_idx = len(current_blocks)
        tokens = _tokenize(prose_text, current_page_num, block_idx)
        if tokens:
            current_blocks.append(Block(key=f"b{block_idx}", type="prose", tokens=tokens, number=prose_number))

    def _flush_pending():
        nonlocal pending_text
        if pending_text:
            _dispatch(pending_text)
            pending_text = ""

    def _flush_page():
        nonlocal current_blocks, pending_fn_defs
        _flush_pending()
        _flush_hadith()
        if current_blocks and current_page_num > 0:
            # Correlation-gated footnote resolution.
            # Walk all body tokens; for each token whose text ends with (N),
            # check whether a pending definition for N exists on this page.
            # Only correlated pairs produce a Footnote + span; unmatched sides
            # are silently dropped (prevents false positives on cleaned corpora).
            page_footnotes: list[Footnote] = []
            fn_idx = 0  # 1-based index within this page, incremented on match

            for block in current_blocks:
                for token in block.tokens:
                    m = _FOOTNOTE_MARKER_RE.search(token.text)
                    if not m:
                        continue
                    marker = m.group(1)
                    if marker not in pending_fn_defs:
                        continue
                    # Correlated match: build Footnote and attach Span
                    fn_idx += 1
                    note_text = pending_fn_defs.pop(marker)
                    fn_tokens = [
                        Token(id=f"p{current_page_num}_fn{fn_idx}_w{i}", text=w)
                        for i, w in enumerate(note_text.split())
                    ]
                    page_footnotes.append(Footnote(marker=marker, tokens=fn_tokens))
                    block.spans.append(Span(
                        start_token_id=token.id,
                        end_token_id=token.id,
                        label="footnote",
                        ref=marker,
                    ))

            pages.append(Page(
                page_number=current_page_num,
                volume=current_volume,
                content_blocks=current_blocks,
                footnotes=page_footnotes,
            ))
        pending_fn_defs = {}
        current_blocks = []

    # Main loop over body lines
    for line in lines[body_start:]:
        stripped = line.strip()

        # Skip blank lines and metadata remnants in body
        if not stripped or stripped.startswith("#META#") or stripped == "######OpenITI#":
            continue

        # Check for page marker - strip "# " prefix if present
        raw = stripped[2:] if stripped.startswith("# ") else stripped
        m = _PAGE_RE.match(raw.strip())
        if m:
            vol, page = int(m.group(1)), int(m.group(2))
            if vol == 0 and page == 0:
                # Null page marker - skip without flushing
                continue
            _flush_page()
            current_volume = vol
            current_page_num = page
            continue

        # Handle line types by prefix
        if line.startswith("~~"):
            # Continuation line - append to pending text
            content = line[2:].strip()
            pending_text = (pending_text + " " + content) if pending_text else content
        elif line.startswith("# "):
            # New paragraph - flush previous, start new pending
            _flush_pending()
            pending_text = line[2:].strip()
        elif stripped.startswith("### "):
            # Heading line
            _flush_pending()
            pending_text = stripped
        else:
            # Other content
            _flush_pending()
            pending_text = stripped

    # Flush final page
    _flush_page()

    return ParseResult(metadata=metadata, pages=pages, chapters=chapters)
