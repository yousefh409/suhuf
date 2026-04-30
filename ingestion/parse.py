from __future__ import annotations

import re
from pathlib import Path

from ingestion.models import Token, Block, Page, Chapter, ParseResult
from ingestion.metadata import parse_file_header

_PAGE_RE = re.compile(r"PageV(\d+)P(\d+)")
_HEADING_RE = re.compile(r"^###\s+(\|+)\s+(.*)")
_EDITOR_RE = re.compile(r"^###\s+\|EDITOR\|")
_HADITH_RE = re.compile(r"^\$RWY\$\s*(.*)")
_BIO_RE = re.compile(r"^###\s+\$(?:BIO_MAN|BIO_WOM|\$?)\$?\s*(.*)")
# OpenITI milestone tokens (msNN) split each printed page into ~300-word chunks
# for the project's NLP alignment tooling. They have no meaning for human
# readers; strip them inline before tokenization.
_MILESTONE_RE = re.compile(r"\bms\d+\b")


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
    pending_text = ""
    chapter_sort = 0

    def _flush_hadith():
        """Flush accumulated hadith words as an isnad block."""
        nonlocal hadith_words, in_hadith
        if not hadith_words:
            in_hadith = False
            return
        block_idx = len(current_blocks)
        tokens = [
            Token(id=f"p{current_page_num}_b{block_idx}_w{i}", text=w)
            for i, w in enumerate(hadith_words)
        ]
        current_blocks.append(Block(key=f"b{block_idx}", type="isnad", tokens=tokens))
        hadith_words = []
        in_hadith = False

    def _dispatch(line_text: str):
        """Process a complete content line (after stripping prefix and joining continuations)."""
        nonlocal in_hadith, hadith_words, chapter_sort

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
            current_blocks.append(Block(key=f"b{block_idx}", type="heading", tokens=tokens))
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
            remainder = m.group(1).strip()
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
            current_blocks.append(Block(key=f"b{block_idx}", type="isnad", tokens=tokens))
            hadith_words = []
            in_hadith = False
            # Create matn block from text after @MATN@
            if after.strip():
                block_idx = len(current_blocks)
                tokens = _tokenize(after.strip(), current_page_num, block_idx)
                current_blocks.append(Block(key=f"b{block_idx}", type="matn", tokens=tokens))
            return

        # Biography markers
        m = _BIO_RE.match(line_text)
        if m:
            _flush_hadith()
            remainder = m.group(1).strip()
            if remainder:
                block_idx = len(current_blocks)
                tokens = _tokenize(remainder, current_page_num, block_idx)
                current_blocks.append(Block(key=f"b{block_idx}", type="biography", tokens=tokens))
            return

        # Accumulate text in hadith mode
        if in_hadith:
            hadith_words.extend(line_text.strip().split())
            return

        # Default: prose
        block_idx = len(current_blocks)
        tokens = _tokenize(line_text.strip(), current_page_num, block_idx)
        if tokens:
            current_blocks.append(Block(key=f"b{block_idx}", type="prose", tokens=tokens))

    def _flush_pending():
        nonlocal pending_text
        if pending_text:
            _dispatch(pending_text)
            pending_text = ""

    def _flush_page():
        nonlocal current_blocks
        _flush_pending()
        _flush_hadith()
        if current_blocks and current_page_num > 0:
            pages.append(Page(
                page_number=current_page_num,
                volume=current_volume,
                content_blocks=current_blocks,
            ))
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
