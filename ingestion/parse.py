from __future__ import annotations

import logging
import re
from pathlib import Path

from ingestion.models import Token, Block, Footnote, Page, Chapter, ParseResult, Span

logger = logging.getLogger(__name__)
from ingestion.metadata import parse_file_header
from ingestion import quran as _quran

_PAGE_RE = re.compile(r"PageV(\d+)P(\d+)")
# Matches a PageVxxPyyy token anywhere in a string (with word boundary awareness).
# Used by the normalization pre-pass.
_PAGE_TOKEN_RE = re.compile(r"(PageV\d+P\d+)")
_HEADING_RE = re.compile(r"^###\s+(\|+)\s+(.*)")
_EDITOR_RE = re.compile(r"^###\s+\|EDITOR\|")
# Print-edition sheet/page reference, e.g. "[ص: 6]". Some raw OpenITI files tag
# these as ### | headings; they are editorial pagination, not chapters.
_SHEET_REF_RE = re.compile(r"^\[\s*ص\s*:\s*[\d٠-٩]+\s*\]$")
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

# Ellipsis hemistich separator. Many diwans (e.g. Alfiyyat Ibn Malik) and
# embedded verse split a bayt's two hemistichs with a standalone "..." / "…"
# rather than the %~% tag. We only treat it as verse when guards hold (single
# standalone separator, both halves >= 2 words, balanced length) so prose
# elisions aren't mistaken for poetry.
_ELLIPSIS_TOKENS = {"...", "…"}
_ELLIPSIS_MIN_WORDS = 2
_ELLIPSIS_BALANCE = 0.4  # shorter half must be >= 40% of the longer half


def _split_ellipsis_hemistichs(line_text: str) -> list[str] | None:
    """Return ``[hemistich1, hemistich2]`` if *line_text* is a single bayt split
    by one standalone ellipsis token into two balanced halves, else ``None``."""
    words = line_text.split()
    seps = [i for i, w in enumerate(words) if w in _ELLIPSIS_TOKENS]
    if len(seps) != 1:
        return None
    left, right = words[: seps[0]], words[seps[0] + 1:]
    if len(left) < _ELLIPSIS_MIN_WORDS or len(right) < _ELLIPSIS_MIN_WORDS:
        return None
    lo, hi = sorted((len(left), len(right)))
    if lo / hi < _ELLIPSIS_BALANCE:
        return None
    return [" ".join(left), " ".join(right)]

# Ornate Quranic bracket glyphs.
_QURAN_OPEN = "\uFD3F"   # ﴿ U+FD3F ORNATE RIGHT PARENTHESIS — opens the ayah
_QURAN_CLOSE = "\uFD3E"  # ﴾ U+FD3E ORNATE LEFT PARENTHESIS  — closes the ayah


def _normalize_body_lines(lines: list[str]) -> list[str]:
    """Expand lines that contain embedded page markers into multiple lines.

    The main parse loop only recognises page markers when they are the ENTIRE
    content of a line (after stripping a ``# `` prefix).  Many real OpenITI
    books embed markers inside content lines, e.g.:

        ~~نص أول PageV01P002 نص ثانٍ

    This function performs a pre-pass over the body lines and splits any such
    line at each embedded marker so the existing standalone-marker logic handles
    them unchanged.

    Normalization rules for a single line:
    - Determine the line's leading prefix (``~~``, ``# ``, ``### ``, or none).
    - If the line is ALREADY a standalone marker (whole content = page marker),
      pass it through unchanged.
    - Otherwise split on each ``PageVxxPyyy`` token left-to-right:
        * Emit the before-segment (with original prefix) if non-whitespace.
        * Emit ``# PageVxxPyyy`` as a standalone marker line.
        * Continue with the remaining text.
      The final after-segment (text after the last marker) is emitted as ``# ``
      if non-whitespace (new paragraph on the new page).
    - ``PageV00P000`` null markers are emitted as ``# PageV00P000`` standalone
      lines; the main loop already skips them without flushing — behaviour is
      preserved.
    """
    result: list[str] = []
    for line in lines:
        # Fast path: no page marker token at all.
        if "PageV" not in line:
            result.append(line)
            continue

        # Detect leading prefix and the bare content without it.
        if line.startswith("~~"):
            prefix = "~~"
            content = line[2:]
        elif line.startswith("# "):
            prefix = "# "
            content = line[2:]
        elif line.startswith("### "):
            prefix = "### "
            content = line[4:]
        else:
            prefix = ""
            content = line

        # Check if this is ALREADY a standalone marker: content (stripped) is
        # exactly a page token and nothing else.
        content_stripped = content.strip()
        if _PAGE_RE.fullmatch(content_stripped):
            # Standalone marker, but possibly behind a prefix the main loop won't
            # strip (e.g. "~~PageV00P000" in the Bulugh source). Normalize to a
            # "# " marker line so the main loop recognizes and skips/flushes it
            # instead of treating it as continuation content.
            result.append("# " + content_stripped)
            continue

        # Split the content on embedded page tokens.
        parts = _PAGE_TOKEN_RE.split(content)
        # _PAGE_TOKEN_RE.split gives: [before, token, after, token, after, ...]
        # Odd-indexed parts are the captured page token strings.

        is_first_before = True
        i = 0
        while i < len(parts):
            if i % 2 == 0:
                # Text segment (before/after/between markers)
                seg = parts[i]
                if seg.strip():
                    if is_first_before:
                        # First before-segment keeps the ORIGINAL prefix.
                        result.append(prefix + seg.strip())
                    else:
                        # Subsequent text segments: new paragraph on new page.
                        result.append("# " + seg.strip())
                is_first_before = False
            else:
                # Page marker token
                page_token = parts[i]
                result.append("# " + page_token)
                is_first_before = False
            i += 1

    return result


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


def _extract_inline_quran(words: list[str]) -> tuple[list[str], list[tuple[int, int, str | None]]]:
    """Pull inline Quranic quotations out of a prose word list.

    The source convention is ``{ayah text} [سورة: آية]`` — curly braces wrap the
    verse, an immediately-following bracket carries the citation. For each such
    pair this strips the braces from the verse words and records a span over
    them. The ``ref`` comes from the citation (sura-name table → "sura:ayah"),
    which is the source's own explicit reference and far more reliable than
    phrase-matching a standard-orthography quote against a Uthmani index; the
    phrase lookup is only a fallback when the citation cannot be resolved.

    A ``{...}`` group with no following citation is left untouched — without that
    evidence we don't assume the braces mark Qur'an.

    Returns ``(cleaned_words, spans)`` where each span is
    ``(start_index, end_index, ref)`` in *cleaned_words* coordinates (inclusive).
    Citation words are kept in the output, faithful to the source.
    """
    out: list[str] = []
    spans: list[tuple[int, int, str | None]] = []
    i, n = 0, len(words)

    while i < n:
        word = words[i]
        if "{" not in word:
            out.append(word)
            i += 1
            continue

        # Find the word that closes the brace group (may be the same word
        # for a one-word quote like "{كلمة}").
        if "}" in word[word.index("{") + 1:]:
            j = i
        else:
            j = i + 1
            while j < n and "}" not in words[j]:
                j += 1

        if j >= n:
            # Unbalanced opener — not a quotation; emit verbatim.
            out.append(word)
            i += 1
            continue

        # Look ahead for a "[...:...]" citation immediately after the close.
        cite_words: list[str] = []
        k = j + 1
        if k < n and words[k].startswith("["):
            while k < n:
                cite_words.append(words[k])
                if "]" in words[k]:
                    k += 1
                    break
                k += 1

        inner = " ".join(cite_words).strip().lstrip("[").rstrip("]").strip()
        if not cite_words or ":" not in inner:
            # No citation evidence — treat the braces as ordinary text.
            out.append(word)
            i += 1
            continue

        ayah_words = [w.replace("{", "").replace("}", "") for w in words[i:j + 1]]
        ayah_words = [w for w in ayah_words if w]
        if not ayah_words:
            out.append(word)
            i += 1
            continue

        start = len(out)
        out.extend(ayah_words)
        end = len(out) - 1

        ref = _quran.citation_to_ref(inner)
        if ref is None:
            hit = _quran.lookup(" ".join(ayah_words))
            if hit is not None:
                ref = f"{hit[0]}:{hit[1]}"

        spans.append((start, end, ref))
        out.extend(cite_words)
        i = j + 1 + len(cite_words)

    return out, spans


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
    # An ordinal-only heading ("### | 12 -") is a printed item number for the
    # NEXT content block (numbered hadith), not a chapter. Held here until the
    # following block consumes it.
    pending_block_number: str | None = None
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

    def _emit_inline_hadith(isnad_text: str, matn_text: str, number: str | None):
        """Emit ONE prose block for a running-line hadith.

        isnad/matn/takhrij live as inline spans over token ranges instead of
        separate blocks. An embedded ``{ayah} [sura:ayah]`` citation in the matn
        keeps its quran span. The ``@MATN@`` marker itself is never tokenized.
        """
        isnad_words = isnad_text.split()
        matn_words, quran_spans = _extract_inline_quran(matn_text.split())

        all_words = isnad_words + matn_words
        if not all_words:
            return
        block_idx = len(current_blocks)
        tokens = [
            Token(id=f"p{current_page_num}_b{block_idx}_w{i}", text=w)
            for i, w in enumerate(all_words)
        ]

        spans: list[Span] = []
        n_isnad = len(isnad_words)
        if n_isnad:
            spans.append(Span(
                start_token_id=tokens[0].id,
                end_token_id=tokens[n_isnad - 1].id,
                label="isnad",
            ))

        # An optional trailing takhrij begins at the first source-attribution
        # keyword inside the matn portion (mirrors the standalone-line rule).
        takhrij_local: int | None = None
        for j, w in enumerate(matn_words):
            if w in _TAKHRIJ_KEYWORDS:
                takhrij_local = j
                break

        if matn_words:
            matn_end_local = (
                takhrij_local - 1 if takhrij_local is not None else len(matn_words) - 1
            )
            if matn_end_local >= 0:
                spans.append(Span(
                    start_token_id=tokens[n_isnad].id,
                    end_token_id=tokens[n_isnad + matn_end_local].id,
                    label="matn",
                ))
            if takhrij_local is not None:
                spans.append(Span(
                    start_token_id=tokens[n_isnad + takhrij_local].id,
                    end_token_id=tokens[-1].id,
                    label="takhrij",
                ))

        # Quran spans sit inside the matn portion; append last so they win on
        # overlap with the matn span (reader: later span wins per token).
        for start, end, ref in quran_spans:
            spans.append(Span(
                start_token_id=tokens[n_isnad + start].id,
                end_token_id=tokens[n_isnad + end].id,
                label="quran",
                ref=ref,
            ))

        current_blocks.append(Block(
            key=f"b{block_idx}", type="prose", tokens=tokens, spans=spans, number=number,
        ))

    def _emit_prose(text: str, number: str | None = None) -> bool:
        """Tokenize *text* into a prose block (with inline quran spans) and
        append it. Returns True if a block was emitted (non-empty)."""
        block_idx = len(current_blocks)
        words, quran_spans = _extract_inline_quran(text.split())
        tokens = [
            Token(id=f"p{current_page_num}_b{block_idx}_w{i}", text=w)
            for i, w in enumerate(words)
        ]
        if not tokens:
            return False
        spans = [
            Span(start_token_id=tokens[s].id, end_token_id=tokens[e].id, label="quran", ref=r)
            for s, e, r in quran_spans
        ]
        current_blocks.append(Block(
            key=f"b{block_idx}", type="prose", tokens=tokens, spans=spans, number=number,
        ))
        return True

    def _dispatch(line_text: str):
        """Process a complete content line (after stripping prefix and joining continuations)."""
        nonlocal in_hadith, hadith_words, hadith_number, chapter_sort, pending_block_number

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
            # An ordinal-only heading ("### | 12 -") is a printed item number for
            # the next content block (numbered hadith), not a chapter.
            ord_num, ord_rest = _extract_leading_ordinal(title)
            if ord_num is not None and not ord_rest.strip():
                pending_block_number = ord_num
                return
            # Print-sheet reference ("[ص: 6]") — editorial pagination, not a
            # chapter. Drop it (leave any pending item number intact).
            if _SHEET_REF_RE.match(title):
                return
            # A heading that opens with content punctuation (":" or an opening
            # quote «) is mistagged body text, not a chapter title (common in raw
            # files where hadith continuations get a ### | marker). Preserve it as
            # prose so the text survives without polluting the chapter list.
            if title[:1] in (":", "«"):
                _emit_prose(title[1:].strip() if title[:1] == ":" else title,
                            number=pending_block_number)
                pending_block_number = None
                return
            # A real titled heading ends any pending item number.
            pending_block_number = None
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
            remainder = m.group(1).strip()
            hadith_number = None
            if remainder:
                hadith_number, remainder = _extract_leading_ordinal(remainder)
            # Inline hadith: isnad and matn share one source line, joined by
            # @MATN@. Emit one prose block with spans, not separate blocks.
            if remainder and "@MATN@" in remainder:
                before, _, after = remainder.partition("@MATN@")
                _emit_inline_hadith(before.strip(), after.strip(), hadith_number)
                in_hadith = False
                hadith_words = []
                hadith_number = None
                return
            # Separate-line hadith: accumulate isnad words; a later @MATN@
            # dispatch (or a flush) closes it as separate blocks.
            in_hadith = True
            hadith_words = []
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

        # %-wrapped poetry: line starts with % and contains at least two % chars.
        # Format: % hemistich1 % % hemistich2 % [verse_number]
        # Splitting on % and taking non-empty trimmed segments yields the
        # hemistich texts plus an optional trailing verse number.
        _normalized = _MILESTONE_RE.sub("", line_text)
        _normalized = re.sub(r"\s{2,}", " ", _normalized).strip()
        if _normalized.startswith("%") and _normalized.count("%") >= 2:
            _flush_hadith()
            segments = [s.strip() for s in _normalized.split("%") if s.strip()]
            # If the last segment is purely digits (ASCII or Arabic-Indic), treat it as verse number.
            verse_number: str | None = None
            if segments and re.fullmatch(r"[0-9\u0660-\u0669]+", segments[-1]):
                verse_number = segments.pop()
            # Remaining segments are hemistichs.
            if segments:
                block_idx = len(current_blocks)
                hemistichs = []
                w_idx = 0
                for seg in segments:
                    words = seg.split()
                    h_tokens = [
                        Token(id=f"p{current_page_num}_b{block_idx}_w{w_idx + j}", text=w)
                        for j, w in enumerate(words)
                    ]
                    w_idx += len(words)
                    if h_tokens:
                        hemistichs.append(h_tokens)
                if hemistichs:
                    current_blocks.append(
                        Block(key=f"b{block_idx}", type="poetry", hemistichs=[hemistichs], number=verse_number)
                    )
            return

        # Ellipsis-separated verse: "hemistich1 ... hemistich2" (e.g. Alfiyya).
        # Guarded against prose elisions by _split_ellipsis_hemistichs. Not while
        # accumulating a hadith, so hadith text containing "..." isn't stolen.
        if not in_hadith:
            hemi = _split_ellipsis_hemistichs(line_text)
            if hemi:
                block_idx = len(current_blocks)
                hemistichs = []
                w_idx = 0
                for part in hemi:
                    words = part.split()
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
        if _emit_prose(prose_text, number=prose_number or pending_block_number):
            pending_block_number = None

    def _flush_pending():
        nonlocal pending_text
        if pending_text:
            _dispatch(pending_text)
            pending_text = ""

    def _flush_page():
        nonlocal current_blocks, pending_fn_defs, pending_block_number
        _flush_pending()
        _flush_hadith()
        pending_block_number = None  # item numbers do not cross page boundaries
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
    # Run normalization pre-pass first so embedded page markers are expanded
    # into standalone marker lines that the existing loop logic can handle.
    body_lines = _normalize_body_lines(lines[body_start:])
    for line in body_lines:
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
            if vol == current_volume and page == current_page_num:
                # Redundant repeat of the current page marker (some raw files
                # double-print them). Not a new page — keep accumulating, else
                # we emit duplicate page rows that collide on upload.
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

    # Residual duplicate page keys (rare non-adjacent marker repeats) collide on
    # upload's (book_id, volume, page_number) upsert and would silently drop a
    # page. Merging them would clash token IDs, so warn instead of losing data.
    seen: set[tuple[int, int]] = set()
    dups: set[tuple[int, int]] = set()
    for p in pages:
        key = (p.volume, p.page_number)
        (dups if key in seen else seen).add(key)
    if dups:
        logger.warning(
            "Duplicate page rows remain after dedup (will collide on upload): %s",
            ", ".join(f"v{v}p{p}" for v, p in sorted(dups)),
        )

    return ParseResult(metadata=metadata, pages=pages, chapters=chapters)
