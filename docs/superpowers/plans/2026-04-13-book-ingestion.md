# Book Ingestion Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ingest OpenITI mARkdown files into Supabase with typed blocks, word tokens, and tashkeel. Validate with Nawawi's Arba'un.

**Architecture:** Python CLI (`python -m ingestion ingest <uri>`) with 3 in-memory stages: parse -> tashkeel -> upload. Pydantic models between stages.

**Tech Stack:** Python 3.11+, Pydantic, supabase-py, torch, transformers, pytest

**Spec:** `docs/superpowers/specs/2026-04-13-book-ingestion-design.md`

---

### Task 1: Project scaffold + data models

**Files:**
- Create: `ingestion/__init__.py`, `ingestion/models.py`, `ingestion/requirements.txt`
- Create: `ingestion/tests/__init__.py`, `ingestion/tests/test_models.py`

- [ ] **Step 1: Create `ingestion/requirements.txt`**

```
pydantic>=2.0.0
supabase>=2.0.0
torch>=2.0.0
transformers>=4.30.0
pyyaml>=6.0
python-dotenv>=1.0.0
pytest>=8.0.0
```

- [ ] **Step 2: Create venv and install deps**

```bash
cd ingestion && python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt
```

- [ ] **Step 3: Write test for models**

```python
# ingestion/tests/test_models.py
from ingestion.models import Token, Block, Page, Chapter, BookMetadata, ParseResult

def test_token_creation():
    t = Token(id="p1_b0_w0", text="حدثنا")
    assert t.id == "p1_b0_w0"
    assert t.text == "حدثنا"

def test_block_with_tokens():
    tokens = [Token(id="p1_b0_w0", text="حدثنا"), Token(id="p1_b0_w1", text="عبد")]
    b = Block(key="b0", type="isnad", tokens=tokens)
    assert b.type == "isnad"
    assert len(b.tokens) == 2
    assert b.hemistichs == []
    assert b.metadata is None

def test_poetry_block_with_hemistichs():
    h1 = [Token(id="p1_b0_w0", text="قفا"), Token(id="p1_b0_w1", text="نبك")]
    h2 = [Token(id="p1_b0_w2", text="بسقط"), Token(id="p1_b0_w3", text="اللوى")]
    b = Block(key="b0", type="poetry", tokens=[], hemistichs=[[h1, h2]])
    assert len(b.hemistichs) == 1
    assert len(b.hemistichs[0]) == 2

def test_page_content_plain_and_hash():
    tokens = [Token(id="p1_b0_w0", text="بسم"), Token(id="p1_b0_w1", text="الله")]
    b = Block(key="b0", type="prose", tokens=tokens)
    p = Page(page_number=1, volume=1, content_blocks=[b])
    assert p.content_plain == "بسم الله"
    assert len(p.content_hash) == 64  # SHA-256 hex

def test_chapter():
    c = Chapter(title="باب النية", level=1, page_number=42, sort_order=1)
    assert c.parent_index is None

def test_parse_result():
    meta = BookMetadata(
        openiti_id="0676Nawawi.ArbacunaNawawiyya",
        title_ar="الأربعون النووية",
        author_openiti_id="0676Nawawi",
        genres=["HADITH"],
    )
    result = ParseResult(metadata=meta, pages=[], chapters=[])
    assert result.metadata.language == "ara"
```

- [ ] **Step 4: Run test, verify it fails (no models.py yet)**

```bash
cd ingestion && python -m pytest tests/test_models.py -v
```

- [ ] **Step 5: Implement models**

```python
# ingestion/models.py
from __future__ import annotations
import hashlib
import unicodedata
from pydantic import BaseModel, Field, computed_field

class Token(BaseModel):
    id: str
    text: str

class Block(BaseModel):
    key: str
    type: str  # prose | hadith | isnad | matn | poetry | biography | heading
    tokens: list[Token] = []
    hemistichs: list[list[list[Token]]] = []
    metadata: dict | None = None

class Page(BaseModel):
    page_number: int
    volume: int = 1
    content_blocks: list[Block] = []

    @computed_field
    @property
    def content_plain(self) -> str:
        words = []
        for block in self.content_blocks:
            if block.type == "poetry":
                for verse in block.hemistichs:
                    for hemistich in verse:
                        words.extend(t.text for t in hemistich)
            else:
                words.extend(t.text for t in block.tokens)
        return " ".join(words)

    @computed_field
    @property
    def content_hash(self) -> str:
        normalized = unicodedata.normalize("NFC", self.content_plain)
        return hashlib.sha256(normalized.encode()).hexdigest()

class Chapter(BaseModel):
    title: str
    level: int
    page_number: int
    sort_order: int
    parent_index: int | None = None

class BookMetadata(BaseModel):
    openiti_id: str
    title_ar: str
    title_lat: str | None = None
    author_openiti_id: str
    genres: list[str] = []
    word_count: int | None = None
    char_count: int | None = None
    version_status: str | None = None
    language: str = "ara"

class ParseResult(BaseModel):
    metadata: BookMetadata
    pages: list[Page] = []
    chapters: list[Chapter] = []
```

- [ ] **Step 6: Run tests, verify pass**
- [ ] **Step 7: Commit**

```bash
git add ingestion/ && git commit -m "feat(ingestion): add project scaffold and Pydantic data models"
```

---

### Task 2: Corpus locator

**Files:**
- Create: `ingestion/corpus.py`
- Create: `ingestion/tests/test_corpus.py`

The corpus locator finds mARkdown files in the OpenITI RELEASE repo given an OpenITI URI.

**RELEASE directory structure:**
```
data/{DeathYear}{Author}/{Author}.{Book}/{Author}.{Book}.{Source}-ara{N}.mARkdown
```

- [ ] **Step 1: Write tests**

```python
# ingestion/tests/test_corpus.py
import os
import tempfile
from pathlib import Path
from ingestion.corpus import find_book_file, find_author_metadata, parse_uri

def test_parse_uri():
    author_id, book_id = parse_uri("0676Nawawi.ArbacunaNawawiyya")
    assert author_id == "0676Nawawi"
    assert book_id == "ArbacunaNawawiyya"

def test_parse_uri_invalid():
    import pytest
    with pytest.raises(ValueError):
        parse_uri("invalid-no-dot")

def test_find_book_file_prefers_markdown():
    """Creates a fake RELEASE tree and verifies .mARkdown is preferred."""
    with tempfile.TemporaryDirectory() as tmp:
        # Create fake file structure
        book_dir = Path(tmp) / "data" / "0676Nawawi" / "0676Nawawi.ArbacunaNawawiyya"
        book_dir.mkdir(parents=True)
        # Create two versions: one .mARkdown, one raw
        md_file = book_dir / "0676Nawawi.ArbacunaNawawiyya.Shamela0012836-ara1.mARkdown"
        raw_file = book_dir / "0676Nawawi.ArbacunaNawawiyya.Sham19Y0147927-ara2"
        md_file.write_text("test", encoding="utf-8")
        raw_file.write_text("test", encoding="utf-8")

        result = find_book_file("0676Nawawi.ArbacunaNawawiyya", corpus_path=tmp)
        assert result == md_file

def test_find_book_file_falls_back_to_completed():
    with tempfile.TemporaryDirectory() as tmp:
        book_dir = Path(tmp) / "data" / "0676Nawawi" / "0676Nawawi.ArbacunaNawawiyya"
        book_dir.mkdir(parents=True)
        completed = book_dir / "0676Nawawi.ArbacunaNawawiyya.Shamela0012836-ara1.completed"
        completed.write_text("test", encoding="utf-8")

        result = find_book_file("0676Nawawi.ArbacunaNawawiyya", corpus_path=tmp)
        assert result == completed

def test_find_book_file_falls_back_to_raw():
    with tempfile.TemporaryDirectory() as tmp:
        book_dir = Path(tmp) / "data" / "0676Nawawi" / "0676Nawawi.ArbacunaNawawiyya"
        book_dir.mkdir(parents=True)
        raw = book_dir / "0676Nawawi.ArbacunaNawawiyya.Sham19Y0147927-ara2"
        raw.write_text("test", encoding="utf-8")

        result = find_book_file("0676Nawawi.ArbacunaNawawiyya", corpus_path=tmp)
        assert result == raw

def test_find_book_file_not_found():
    with tempfile.TemporaryDirectory() as tmp:
        import pytest
        with pytest.raises(FileNotFoundError):
            find_book_file("0676Nawawi.ArbacunaNawawiyya", corpus_path=tmp)

def test_find_author_metadata():
    with tempfile.TemporaryDirectory() as tmp:
        author_dir = Path(tmp) / "data" / "0676Nawawi"
        author_dir.mkdir(parents=True)
        yml = author_dir / "0676Nawawi.yml"
        yml.write_text("00#AUTH#URI######: 0676Nawawi\n", encoding="utf-8")

        result = find_author_metadata("0676Nawawi", corpus_path=tmp)
        assert result == yml
```

- [ ] **Step 2: Run tests, verify fail**
- [ ] **Step 3: Implement corpus.py**

```python
# ingestion/corpus.py
from pathlib import Path

def parse_uri(openiti_uri: str) -> tuple[str, str]:
    """Parse '0676Nawawi.ArbacunaNawawiyya' into (author_id, book_id)."""
    if "." not in openiti_uri:
        raise ValueError(f"Invalid OpenITI URI (expected 'Author.Book'): {openiti_uri}")
    author_id, book_id = openiti_uri.split(".", 1)
    return author_id, book_id

def find_book_file(openiti_uri: str, corpus_path: str) -> Path:
    """Locate the best-quality text file for a book in the RELEASE corpus.

    Priority: .mARkdown > .completed > raw (no extension after ara{N}).
    """
    author_id, _ = parse_uri(openiti_uri)
    book_dir = Path(corpus_path) / "data" / author_id / openiti_uri

    if not book_dir.is_dir():
        raise FileNotFoundError(f"Book directory not found: {book_dir}")

    # Collect all text files (not .yml, not .md, not directories)
    skip_exts = {".yml", ".md"}
    candidates = [
        f for f in book_dir.iterdir()
        if f.is_file() and f.suffix not in skip_exts and f.name != "README.md"
    ]

    if not candidates:
        raise FileNotFoundError(f"No text files found in {book_dir}")

    # Sort by quality: .mARkdown first, .completed second, raw last
    def quality(f: Path) -> int:
        if f.name.endswith(".mARkdown"):
            return 0
        elif f.name.endswith(".completed"):
            return 1
        else:
            return 2

    candidates.sort(key=quality)
    return candidates[0]

def find_author_metadata(author_id: str, corpus_path: str) -> Path | None:
    """Locate the author .yml metadata file."""
    yml = Path(corpus_path) / "data" / author_id / f"{author_id}.yml"
    return yml if yml.is_file() else None
```

- [ ] **Step 4: Run tests, verify pass**
- [ ] **Step 5: Commit**

```bash
git add ingestion/corpus.py ingestion/tests/test_corpus.py
git commit -m "feat(ingestion): add corpus locator with quality-tier file selection"
```

---

### Task 3: Metadata parser

**Files:**
- Create: `ingestion/metadata.py`
- Create: `ingestion/tests/test_metadata.py`

Parses two things:
1. The `#META#` header inside `.mARkdown` files
2. The author `.yml` files (custom `##` format, NOT real YAML)

- [ ] **Step 1: Write tests**

Test with real header content from the Nawawi Arba'un file.

```python
# ingestion/tests/test_metadata.py
from ingestion.metadata import parse_file_header, parse_author_yml
from ingestion.models import BookMetadata

SAMPLE_HEADER = """######OpenITI#


#META# 000.SortField\t:: Shamela_0012836
#META# 010.AuthorNAME\t:: أبو زكريا محيي الدين يحيى بن شرف النووي
#META# 011.AuthorDIED\t:: 676
#META# 020.BookTITLE\t:: الأربعون النووية
#META# 022.BookVOLS\t:: 1
#META# 00#VERS#LENGTH###\t:: 3464
#META# 00#VERS#CLENGTH##\t:: 14399
#META# 40#BOOK#GENRE####\t:: HADITH :: MASANID

#META#Header#End#

# بسم الله الرحمن الرحيم
"""

def test_parse_file_header():
    meta = parse_file_header(SAMPLE_HEADER.splitlines(), "0676Nawawi.ArbacunaNawawiyya")
    assert meta.openiti_id == "0676Nawawi.ArbacunaNawawiyya"
    assert meta.title_ar == "الأربعون النووية"
    assert meta.author_openiti_id == "0676Nawawi"
    assert meta.word_count == 3464
    assert meta.char_count == 14399
    assert "HADITH" in meta.genres

def test_parse_file_header_missing_fields():
    """Minimal header with just the markers."""
    lines = [
        "######OpenITI#",
        "#META# 020.BookTITLE\t:: كتاب ما",
        "#META#Header#End#",
    ]
    meta = parse_file_header(lines, "0100Someone.SomeBook")
    assert meta.title_ar == "كتاب ما"
    assert meta.word_count is None
    assert meta.genres == []

SAMPLE_AUTHOR_YML = """00#AUTH#URI######: 0676Nawawi
10#AUTH#ISM####AR: Yahya
10#AUTH#KUNYA##AR: Abu Zakariyya
10#AUTH#LAQAB##AR: Muhyi al-din
10#AUTH#NASAB##AR: b. Sharaf
10#AUTH#NISBA##AR: al-Nawawi
10#AUTH#SHUHRA#AR: al-Nawawi
30#AUTH#BORN###AH: 0631
30#AUTH#DIED###AH: 0676
"""

def test_parse_author_yml():
    data = parse_author_yml(SAMPLE_AUTHOR_YML.splitlines())
    assert data["shuhra_lat"] == "al-Nawawi"
    assert data["birth_ah"] == 631
    assert data["death_ah"] == 676
    assert data["kunya_lat"] == "Abu Zakariyya"
```

- [ ] **Step 2: Run tests, verify fail**
- [ ] **Step 3: Implement metadata.py**

```python
# ingestion/metadata.py
from __future__ import annotations
import re
from ingestion.models import BookMetadata
from ingestion.corpus import parse_uri

def parse_file_header(lines: list[str], openiti_uri: str) -> BookMetadata:
    """Parse #META# header lines from a mARkdown file."""
    author_id, _ = parse_uri(openiti_uri)
    fields: dict[str, str] = {}

    for line in lines:
        if line.strip() == "#META#Header#End#":
            break
        if not line.startswith("#META#"):
            continue
        # Format: #META# key\t:: value
        match = re.match(r"#META#\s+(.+?)\t::\s*(.*)", line)
        if match:
            fields[match.group(1).strip()] = match.group(2).strip()

    # Extract genres from "HADITH :: MASANID" format
    genre_raw = fields.get("40#BOOK#GENRE####", "")
    genres = [g.strip() for g in genre_raw.split("::") if g.strip() and g.strip() != "NODATA"]

    def int_or_none(key: str) -> int | None:
        val = fields.get(key, "")
        try:
            return int(val)
        except (ValueError, TypeError):
            return None

    title = fields.get("020.BookTITLE", fields.get("10#BOOK#TITLEA#AR", ""))

    return BookMetadata(
        openiti_id=openiti_uri,
        title_ar=title if title and title != "NODATA" else openiti_uri,
        author_openiti_id=author_id,
        genres=genres,
        word_count=int_or_none("00#VERS#LENGTH###"),
        char_count=int_or_none("00#VERS#CLENGTH##"),
    )

def parse_author_yml(lines: list[str]) -> dict:
    """Parse the custom ## format author metadata into a flat dict."""
    fields: dict[str, str] = {}
    for line in lines:
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        fields[key.strip()] = value.strip()

    def int_or_none(key: str) -> int | None:
        val = fields.get(key, "")
        # Strip leading zeros, extract year
        match = re.match(r"(\d+)", val)
        return int(match.group(1)) if match else None

    return {
        "shuhra_lat": fields.get("10#AUTH#SHUHRA#AR"),
        "ism_lat": fields.get("10#AUTH#ISM####AR"),
        "nasab_lat": fields.get("10#AUTH#NASAB##AR"),
        "kunya_lat": fields.get("10#AUTH#KUNYA##AR"),
        "laqab_lat": fields.get("10#AUTH#LAQAB##AR"),
        "nisba_lat": fields.get("10#AUTH#NISBA##AR"),
        "birth_ah": int_or_none("30#AUTH#BORN###AH"),
        "death_ah": int_or_none("30#AUTH#DIED###AH"),
    }
```

- [ ] **Step 4: Run tests, verify pass**
- [ ] **Step 5: Commit**

```bash
git add ingestion/metadata.py ingestion/tests/test_metadata.py
git commit -m "feat(ingestion): add metadata parser for mARkdown headers and author YML"
```

---

### Task 4: mARkdown content parser

**Files:**
- Create: `ingestion/parse.py`
- Create: `ingestion/tests/test_parse.py`
- Create: `ingestion/tests/fixtures/sample.mARkdown` (small test fixture)

This is the core parser. It reads an OpenITI mARkdown file and produces a `ParseResult`.

**Real mARkdown format notes (from RELEASE corpus):**
- Paragraphs start with `# ` (hash + space)
- Line continuations start with `~~`
- Page markers: `# PageV01P035` (inside a `# ` paragraph line)
- Headings: `### | text`, `### || text`, etc.
- Hadith: `# $RWY$ text`
- Matn boundary: `@MATN@` inline
- Biography: `### $BIO_MAN$ text`
- Poetry hemistich divider: `%~%`
- `PageV00P000` = null/unknown, skip it

- [ ] **Step 1: Create test fixture**

```
# ingestion/tests/fixtures/sample.mARkdown
######OpenITI#

#META# 020.BookTITLE	:: كتاب تجريبي
#META# 00#VERS#LENGTH###	:: 50

#META#Header#End#

# PageV01P001
### | باب الأول
# بسم الله الرحمن الرحيم الحمد لله
~~رب العالمين
# PageV01P002
# $RWY$ حدثنا عبد الله بن يوسف
~~أنا مالك عن نافع
# @MATN@ إنما الأعمال بالنيات
# PageV01P003
### || فصل في الشعر
# قفا نبك %~% بسقط اللوى
# PageV00P000
# هذا نص عادي
```

- [ ] **Step 2: Write tests**

```python
# ingestion/tests/test_parse.py
from pathlib import Path
from ingestion.parse import parse_file
from ingestion.models import ParseResult

FIXTURE = Path(__file__).parent / "fixtures" / "sample.mARkdown"

def test_parse_produces_correct_page_count():
    result = parse_file(FIXTURE, "0100Test.TestBook")
    # Pages: V01P001, V01P002, V01P003. PageV00P000 is skipped.
    assert len(result.pages) == 3

def test_parse_page_numbers():
    result = parse_file(FIXTURE, "0100Test.TestBook")
    page_numbers = [p.page_number for p in result.pages]
    assert page_numbers == [1, 2, 3]

def test_parse_heading_block():
    result = parse_file(FIXTURE, "0100Test.TestBook")
    page1 = result.pages[0]
    heading = page1.content_blocks[0]
    assert heading.type == "heading"
    assert heading.tokens[0].text == "باب"

def test_parse_prose_with_continuation():
    result = parse_file(FIXTURE, "0100Test.TestBook")
    page1 = result.pages[0]
    prose = page1.content_blocks[1]
    assert prose.type == "prose"
    # "بسم الله الرحمن الرحيم الحمد لله رب العالمين" (continuation joined)
    texts = [t.text for t in prose.tokens]
    assert "رب" in texts
    assert "العالمين" in texts

def test_parse_hadith_isnad_matn_split():
    result = parse_file(FIXTURE, "0100Test.TestBook")
    page2 = result.pages[1]
    types = [b.type for b in page2.content_blocks]
    assert "isnad" in types
    assert "matn" in types

def test_parse_isnad_tokens():
    result = parse_file(FIXTURE, "0100Test.TestBook")
    page2 = result.pages[1]
    isnad = [b for b in page2.content_blocks if b.type == "isnad"][0]
    texts = [t.text for t in isnad.tokens]
    assert "حدثنا" in texts

def test_parse_matn_tokens():
    result = parse_file(FIXTURE, "0100Test.TestBook")
    page2 = result.pages[1]
    matn = [b for b in page2.content_blocks if b.type == "matn"][0]
    texts = [t.text for t in matn.tokens]
    assert "الأعمال" in texts

def test_parse_poetry_hemistichs():
    result = parse_file(FIXTURE, "0100Test.TestBook")
    page3 = result.pages[2]
    poetry = [b for b in page3.content_blocks if b.type == "poetry"]
    assert len(poetry) == 1
    verse = poetry[0]
    assert len(verse.hemistichs) == 1
    assert len(verse.hemistichs[0]) == 2  # two hemistichs
    h1_texts = [t.text for t in verse.hemistichs[0][0]]
    assert "قفا" in h1_texts

def test_parse_token_ids_format():
    result = parse_file(FIXTURE, "0100Test.TestBook")
    page1 = result.pages[0]
    first_token = page1.content_blocks[0].tokens[0]
    # p{page}_b{block}_w{word}
    assert first_token.id.startswith("p1_b0_w0")

def test_parse_chapters():
    result = parse_file(FIXTURE, "0100Test.TestBook")
    assert len(result.chapters) == 2
    assert result.chapters[0].title == "باب الأول"
    assert result.chapters[0].level == 1
    assert result.chapters[1].title == "فصل في الشعر"
    assert result.chapters[1].level == 2

def test_parse_skips_pagev00p000():
    """PageV00P000 is a null marker and should not create a new page."""
    result = parse_file(FIXTURE, "0100Test.TestBook")
    page_numbers = [p.page_number for p in result.pages]
    assert 0 not in page_numbers

def test_parse_content_plain():
    result = parse_file(FIXTURE, "0100Test.TestBook")
    for page in result.pages:
        assert len(page.content_plain) > 0
        assert len(page.content_hash) == 64

def test_parse_metadata():
    result = parse_file(FIXTURE, "0100Test.TestBook")
    assert result.metadata.title_ar == "كتاب تجريبي"
    assert result.metadata.word_count == 50
```

- [ ] **Step 3: Run tests, verify fail**
- [ ] **Step 4: Implement parse.py**

The parser reads the file line by line. Key rules:
- Lines starting `# ` are paragraph/content lines (strip the `# ` prefix)
- Lines starting `~~` are continuations (strip `~~`, append to previous line)
- `# PageV{vol}P{page}` triggers a page flush
- `### |` lines are headings (count pipes for level)
- `# $RWY$` starts hadith/isnad accumulation
- `@MATN@` inline splits isnad from matn
- `%~%` splits poetry hemistichs
- `PageV00P000` is skipped

```python
# ingestion/parse.py
from __future__ import annotations
import re
from pathlib import Path
from ingestion.models import Token, Block, Page, Chapter, BookMetadata, ParseResult
from ingestion.metadata import parse_file_header

PAGE_RE = re.compile(r"^PageV(\d+)P(\d+)$")
HEADING_RE = re.compile(r"^###\s+(\|+)\s+(.+)")
HADITH_RE = re.compile(r"^\$RWY\$\s*(.*)")
BIO_RE = re.compile(r"^###\s+\$(?:BIO_MAN|BIO_WOM|\$?)\$?\s*(.*)")
EDITOR_RE = re.compile(r"^###\s+\|EDITOR\|")


def _tokenize(text: str, page_num: int, block_idx: int) -> list[Token]:
    words = text.split()
    return [Token(id=f"p{page_num}_b{block_idx}_w{i}", text=w) for i, w in enumerate(words)]


def _strip_line_prefix(line: str) -> tuple[str, bool]:
    """Strip mARkdown line prefix. Returns (text, is_continuation)."""
    if line.startswith("~~"):
        return line[2:].strip(), True
    if line.startswith("# "):
        return line[2:].strip(), False
    return line.strip(), False


def parse_file(path: Path, openiti_uri: str) -> ParseResult:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()

    # Parse metadata header
    metadata = parse_file_header(lines, openiti_uri)

    # Find where body starts (after #META#Header#End#)
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
    hadith_tokens: list[Token] = []  # accumulates isnad tokens
    pending_text = ""  # for continuation lines
    chapter_sort = 0

    def flush_pending():
        nonlocal pending_text
        if not pending_text:
            return
        text = pending_text
        pending_text = ""
        _process_content_line(text)

    def flush_page():
        nonlocal current_blocks, in_hadith, hadith_tokens
        flush_pending()
        _flush_hadith_tokens()
        if current_blocks and current_page_num > 0:
            pages.append(Page(
                page_number=current_page_num,
                volume=current_volume,
                content_blocks=current_blocks,
            ))
        current_blocks = []
        in_hadith = False
        hadith_tokens = []

    def _flush_hadith_tokens():
        nonlocal hadith_tokens, in_hadith
        if hadith_tokens and in_hadith:
            # Remaining tokens without @MATN@ split -> hadith block
            block_idx = len(current_blocks)
            # Re-index tokens for current block
            retokened = [Token(id=f"p{current_page_num}_b{block_idx}_w{i}", text=t.text)
                         for i, t in enumerate(hadith_tokens)]
            current_blocks.append(Block(key=f"b{block_idx}", type="hadith", tokens=retokened))
            hadith_tokens = []

    def _process_content_line(text: str):
        nonlocal in_hadith, hadith_tokens, chapter_sort

        if not text.strip():
            return

        # Check for page marker within content
        page_match = PAGE_RE.match(text.strip())
        if page_match:
            return  # Already handled

        # Editor content - skip
        if EDITOR_RE.match(text):
            return

        # Heading
        heading_match = HEADING_RE.match(text)
        if heading_match:
            _flush_hadith_tokens()
            in_hadith = False
            level = len(heading_match.group(1))
            title = heading_match.group(2).strip()
            block_idx = len(current_blocks)
            tokens = _tokenize(title, current_page_num, block_idx)
            current_blocks.append(Block(key=f"b{block_idx}", type="heading", tokens=tokens))
            chapter_sort += 1
            chapters.append(Chapter(
                title=title, level=level,
                page_number=current_page_num, sort_order=chapter_sort,
            ))
            return

        # Hadith start
        hadith_match = HADITH_RE.match(text)
        if hadith_match:
            _flush_hadith_tokens()
            in_hadith = True
            hadith_tokens = []
            remainder = hadith_match.group(1).strip()
            if remainder:
                hadith_tokens.extend(
                    Token(id=f"tmp_{i}", text=w) for i, w in enumerate(remainder.split())
                )
            return

        # Poetry
        if "%~%" in text:
            _flush_hadith_tokens()
            in_hadith = False
            parts = text.split("%~%")
            block_idx = len(current_blocks)
            hemistichs = []
            w_idx = 0
            for part in parts:
                words = part.strip().split()
                h_tokens = [Token(id=f"p{current_page_num}_b{block_idx}_w{w_idx + i}", text=w)
                           for i, w in enumerate(words)]
                w_idx += len(words)
                if h_tokens:
                    hemistichs.append(h_tokens)
            if hemistichs:
                current_blocks.append(Block(
                    key=f"b{block_idx}", type="poetry",
                    hemistichs=[hemistichs],
                ))
            return

        # @MATN@ split
        if "@MATN@" in text and in_hadith:
            before, _, after = text.partition("@MATN@")
            # Flush accumulated isnad tokens + before text
            if before.strip():
                hadith_tokens.extend(
                    Token(id=f"tmp_{i}", text=w) for i, w in enumerate(before.strip().split())
                )
            block_idx = len(current_blocks)
            retokened = [Token(id=f"p{current_page_num}_b{block_idx}_w{i}", text=t.text)
                         for i, t in enumerate(hadith_tokens)]
            current_blocks.append(Block(key=f"b{block_idx}", type="isnad", tokens=retokened))
            hadith_tokens = []

            # Start matn
            if after.strip():
                block_idx = len(current_blocks)
                tokens = _tokenize(after.strip(), current_page_num, block_idx)
                current_blocks.append(Block(key=f"b{block_idx}", type="matn", tokens=tokens))
            in_hadith = False
            return

        # In hadith mode: accumulate
        if in_hadith:
            hadith_tokens.extend(
                Token(id=f"tmp_{i}", text=w) for i, w in enumerate(text.strip().split())
            )
            return

        # Default: prose
        block_idx = len(current_blocks)
        tokens = _tokenize(text.strip(), current_page_num, block_idx)
        if tokens:
            current_blocks.append(Block(key=f"b{block_idx}", type="prose", tokens=tokens))

    # Main loop
    for line in lines[body_start:]:
        stripped = line.strip()

        # Skip empty lines and metadata remnants
        if not stripped or stripped.startswith("#META#") or stripped == "######OpenITI#":
            continue

        # Check for page marker
        # Page markers appear as "# PageV01P035" or just "PageV01P035"
        raw_text = stripped
        if raw_text.startswith("# "):
            raw_text = raw_text[2:]

        page_match = PAGE_RE.match(raw_text.strip())
        if page_match:
            vol = int(page_match.group(1))
            page = int(page_match.group(2))
            # Skip null markers
            if vol == 0 and page == 0:
                continue
            flush_page()
            current_volume = vol
            current_page_num = page
            continue

        # Strip line prefix
        text, is_continuation = _strip_line_prefix(line)
        if not text:
            continue

        if is_continuation:
            pending_text += " " + text if pending_text else text
        else:
            flush_pending()
            pending_text = text

    # Flush final state
    flush_pending()
    flush_page()

    return ParseResult(metadata=metadata, pages=pages, chapters=chapters)
```

- [ ] **Step 5: Run tests, verify pass. Debug any failures against the fixture.**
- [ ] **Step 6: Commit**

```bash
git add ingestion/parse.py ingestion/tests/test_parse.py ingestion/tests/fixtures/
git commit -m "feat(ingestion): add mARkdown content parser with block/token extraction"
```

---

### Task 5: Tashkeel stage

**Files:**
- Create: `ingestion/tashkeel.py`
- Create: `ingestion/tests/test_tashkeel.py`

- [ ] **Step 1: Write tests**

```python
# ingestion/tests/test_tashkeel.py
import unicodedata
from ingestion.tashkeel import has_diacritics, diacritize_blocks
from ingestion.models import Token, Block, Page

ARABIC_DIACRITICS = set("\u064B\u064C\u064D\u064E\u064F\u0650\u0651\u0652")

def test_has_diacritics_true():
    assert has_diacritics("حَدَّثَنَا") is True

def test_has_diacritics_false():
    assert has_diacritics("حدثنا") is False

def test_has_diacritics_partial():
    # Ratio below threshold -> not considered diacritized
    assert has_diacritics("حَدثنا عبد الله") is False

def test_diacritize_blocks_skips_already_vocalized():
    """Blocks with sufficient diacritics should be left unchanged."""
    vocalized = "حَدَّثَنَا عَبْدُ اللَّهِ"
    tokens = [Token(id=f"p1_b0_w{i}", text=w) for i, w in enumerate(vocalized.split())]
    block = Block(key="b0", type="prose", tokens=tokens)
    page = Page(page_number=1, volume=1, content_blocks=[block])

    # Use None engine (should not be called since block is already vocalized)
    result = diacritize_blocks([page], engine=None)
    assert result[0].content_blocks[0].tokens[0].text == "حَدَّثَنَا"

def test_diacritize_blocks_processes_unvocalized():
    """Unvocalized blocks should be sent to the engine."""
    tokens = [Token(id="p1_b0_w0", text="حدثنا"), Token(id="p1_b0_w1", text="عبد")]
    block = Block(key="b0", type="prose", tokens=tokens)
    page = Page(page_number=1, volume=1, content_blocks=[block])

    class MockEngine:
        def diacritize(self, text: str) -> str:
            return "حَدَّثَنَا عَبْدُ"

    result = diacritize_blocks([page], engine=MockEngine())
    assert any(
        c in ARABIC_DIACRITICS
        for c in result[0].content_blocks[0].tokens[0].text
    )

def test_diacritize_blocks_handles_token_count_mismatch():
    """If engine returns different word count, keep original text."""
    tokens = [Token(id="p1_b0_w0", text="حدثنا"), Token(id="p1_b0_w1", text="عبد")]
    block = Block(key="b0", type="prose", tokens=tokens)
    page = Page(page_number=1, volume=1, content_blocks=[block])

    class BadEngine:
        def diacritize(self, text: str) -> str:
            return "حَدَّثَنَا"  # Only 1 word instead of 2

    result = diacritize_blocks([page], engine=BadEngine())
    # Should keep original since count mismatched
    assert result[0].content_blocks[0].tokens[0].text == "حدثنا"
```

- [ ] **Step 2: Run tests, verify fail**
- [ ] **Step 3: Implement tashkeel.py**

```python
# ingestion/tashkeel.py
from __future__ import annotations
import logging
from typing import Protocol
from ingestion.models import Token, Block, Page

logger = logging.getLogger(__name__)

DIACRITIC_CODEPOINTS = {
    "\u064B", "\u064C", "\u064D", "\u064E", "\u064F",
    "\u0650", "\u0651", "\u0652",  # fathatan through sukun
}
DIACRITIC_RATIO_THRESHOLD = 0.15


class TashkeelEngine(Protocol):
    def diacritize(self, text: str) -> str: ...


def has_diacritics(text: str) -> bool:
    """Check if text has sufficient diacritical marks (ratio > threshold)."""
    if not text:
        return False
    total = sum(1 for c in text if c.isalpha() or c in DIACRITIC_CODEPOINTS)
    if total == 0:
        return False
    diac_count = sum(1 for c in text if c in DIACRITIC_CODEPOINTS)
    return (diac_count / total) > DIACRITIC_RATIO_THRESHOLD


def _block_text(block: Block) -> str:
    """Get all text from a block as a single string."""
    if block.type == "poetry":
        words = []
        for verse in block.hemistichs:
            for hemistich in verse:
                words.extend(t.text for t in hemistich)
        return " ".join(words)
    return " ".join(t.text for t in block.tokens)


def _diacritize_block(block: Block, engine: TashkeelEngine | None, page_num: int) -> Block:
    """Diacritize a single block. Returns a new Block with updated tokens."""
    text = _block_text(block)
    if not text or has_diacritics(text) or engine is None:
        return block

    try:
        result = engine.diacritize(text)
    except Exception as e:
        logger.warning(f"Tashkeel failed for block {block.key} on page {page_num}: {e}")
        return block

    result_words = result.split()

    if block.type == "poetry":
        # Rebuild hemistichs with diacritized words
        original_words = []
        for verse in block.hemistichs:
            for hemistich in verse:
                original_words.extend(t.text for t in hemistich)

        if len(result_words) != len(original_words):
            logger.warning(
                f"Token count mismatch in poetry block {block.key} on page {page_num}: "
                f"expected {len(original_words)}, got {len(result_words)}. Keeping original."
            )
            return block

        # Map diacritized words back into hemistich structure
        idx = 0
        new_hemistichs = []
        for verse in block.hemistichs:
            new_verse = []
            for hemistich in verse:
                new_h = []
                for token in hemistich:
                    new_h.append(Token(id=token.id, text=result_words[idx]))
                    idx += 1
                new_verse.append(new_h)
            new_hemistichs.append(new_verse)

        return Block(key=block.key, type=block.type, hemistichs=new_hemistichs, metadata=block.metadata)

    # Non-poetry blocks
    if len(result_words) != len(block.tokens):
        logger.warning(
            f"Token count mismatch in block {block.key} on page {page_num}: "
            f"expected {len(block.tokens)}, got {len(result_words)}. Keeping original."
        )
        return block

    new_tokens = [Token(id=t.id, text=w) for t, w in zip(block.tokens, result_words)]
    return Block(key=block.key, type=block.type, tokens=new_tokens, metadata=block.metadata)


def diacritize_blocks(pages: list[Page], engine: TashkeelEngine | None) -> list[Page]:
    """Diacritize all blocks in all pages. Returns new Page objects."""
    result = []
    for page in pages:
        new_blocks = [_diacritize_block(b, engine, page.page_number) for b in page.content_blocks]
        result.append(Page(page_number=page.page_number, volume=page.volume, content_blocks=new_blocks))
    return result


def load_engine(name: str = "sadeed") -> TashkeelEngine | None:
    """Load a tashkeel engine by name. Returns None if loading fails."""
    if name == "sadeed":
        try:
            from transformers import AutoTokenizer, AutoModelForSeq2SeqLM
            # Attempt to load Sadeed model - exact model ID TBD based on HuggingFace availability
            logger.info("Loading Sadeed tashkeel model...")
            # Placeholder: actual model loading depends on published HuggingFace model ID
            raise ImportError("Sadeed model ID not yet confirmed on HuggingFace")
        except Exception as e:
            logger.warning(f"Failed to load Sadeed: {e}. Trying Shakkala fallback.")
            return load_engine("shakkala")
    elif name == "shakkala":
        try:
            from models import Shakkala as ShakkalaModel  # PyTorch port
            logger.info("Loading Shakkala tashkeel model...")

            class _ShakkalaEngine:
                def __init__(self):
                    self._model = ShakkalaModel(sd_path="./data/shakkala_second_model6.pth")

                def diacritize(self, text: str) -> str:
                    return self._model.predict(text)

            return _ShakkalaEngine()
        except Exception as e:
            logger.warning(f"Failed to load Shakkala: {e}")
            return None
    else:
        logger.error(f"Unknown tashkeel engine: {name}")
        return None
```

- [ ] **Step 4: Run tests, verify pass**
- [ ] **Step 5: Commit**

```bash
git add ingestion/tashkeel.py ingestion/tests/test_tashkeel.py
git commit -m "feat(ingestion): add tashkeel stage with engine protocol and fill-gaps-only mode"
```

---

### Task 6: Supabase schema migration

**Files:**
- Modify: `supabase/migrations/20260413100000_book_schema.sql` (replace with full spec schema)

The existing migration has a simplified schema. We need to replace it with the full spec schema including `authors`, volume support on `pages`, proper `chapters` with levels, and all user tables.

- [ ] **Step 1: Write the new migration**

Replace `supabase/migrations/20260413100000_book_schema.sql` with the complete schema from `docs/reader/book-format.md`. This includes:
- `authors` table (all name fields, dates, geography)
- `books` table (FK to authors, genres, metrics, version info)
- `pages` table (with `volume`, `content_blocks`, `content_plain`, `content_hash`)
- `chapters` table (with `level`, `page_id`, `parent_id`, `sort_order`)
- `irab_cache` table
- `user_library`, `user_bookmarks`, `user_highlights`, `user_notes`, `user_reading_positions`
- RLS policies

Full SQL in spec: `docs/reader/book-format.md` Storage Format section.

- [ ] **Step 2: Delete the old `seed-books.mjs`** (it uses the old schema and has hardcoded credentials)

- [ ] **Step 3: Apply migration to Supabase**

```bash
cd supabase && supabase db push
```

Or if remote: apply via Supabase dashboard SQL editor.

- [ ] **Step 4: Verify tables exist**

```bash
supabase db dump --schema public | grep "CREATE TABLE"
```

- [ ] **Step 5: Commit**

```bash
git add supabase/migrations/ && git rm seed-books.mjs
git commit -m "feat(db): replace simplified book schema with full spec schema"
```

---

### Task 7: Upload stage

**Files:**
- Create: `ingestion/upload.py`
- Create: `ingestion/tests/test_upload.py`

- [ ] **Step 1: Write tests**

Tests use mocks for the Supabase client since we don't want to hit a real DB in unit tests.

```python
# ingestion/tests/test_upload.py
from unittest.mock import MagicMock, patch, call
from ingestion.upload import upload_book
from ingestion.models import Token, Block, Page, Chapter, BookMetadata, ParseResult

def _make_result() -> ParseResult:
    tokens = [Token(id="p1_b0_w0", text="بسم"), Token(id="p1_b0_w1", text="الله")]
    block = Block(key="b0", type="prose", tokens=tokens)
    page = Page(page_number=1, volume=1, content_blocks=[block])
    chapter = Chapter(title="باب", level=1, page_number=1, sort_order=1)
    meta = BookMetadata(
        openiti_id="0676Nawawi.ArbacunaNawawiyya",
        title_ar="الأربعون النووية",
        author_openiti_id="0676Nawawi",
        genres=["HADITH"],
    )
    return ParseResult(metadata=meta, pages=[page], chapters=[chapter])

def test_upload_calls_upsert_in_order():
    """Verify upload order: author -> book -> pages -> chapters."""
    client = MagicMock()
    # Mock return values for upserts
    author_resp = MagicMock()
    author_resp.data = [{"id": "author-uuid"}]
    book_resp = MagicMock()
    book_resp.data = [{"id": "book-uuid"}]
    page_resp = MagicMock()
    page_resp.data = [{"id": "page-uuid", "page_number": 1, "volume": 1}]

    table_mock = MagicMock()
    table_mock.upsert.return_value.execute.side_effect = [
        author_resp, book_resp, page_resp, MagicMock(data=[])
    ]
    client.table.return_value = table_mock

    result = _make_result()
    upload_book(result, author_data={}, client=client)

    # Verify table() was called for authors, books, pages, chapters
    table_calls = [c.args[0] for c in client.table.call_args_list]
    assert "authors" in table_calls
    assert "books" in table_calls
    assert "pages" in table_calls
    assert "chapters" in table_calls

def test_upload_sets_has_tashkeel():
    client = MagicMock()
    resp = MagicMock()
    resp.data = [{"id": "uuid"}]
    client.table.return_value.upsert.return_value.execute.return_value = resp

    result = _make_result()
    upload_book(result, author_data={}, client=client, has_tashkeel=True)

    # Find the books upsert call and check has_tashkeel
    for c in client.table.return_value.upsert.call_args_list:
        data = c.args[0]
        if isinstance(data, dict) and "has_tashkeel" in data:
            assert data["has_tashkeel"] is True
```

- [ ] **Step 2: Run tests, verify fail**
- [ ] **Step 3: Implement upload.py**

```python
# ingestion/upload.py
from __future__ import annotations
import json
import logging
from supabase import Client
from ingestion.models import ParseResult

logger = logging.getLogger(__name__)
PAGE_BATCH_SIZE = 100


def upload_book(
    result: ParseResult,
    author_data: dict,
    client: Client,
    has_tashkeel: bool = False,
) -> None:
    """Upload a parsed book to Supabase. All operations are upserts."""
    meta = result.metadata
    author_id = meta.author_openiti_id

    # 1. Upsert author
    author_row = {
        "openiti_id": author_id,
        "shuhra_ar": author_data.get("shuhra_lat", author_id),  # fallback to ID
        "shuhra_lat": author_data.get("shuhra_lat"),
        "ism_ar": author_data.get("ism_lat"),
        "nasab_ar": author_data.get("nasab_lat"),
        "kunya_ar": author_data.get("kunya_lat"),
        "laqab_ar": author_data.get("laqab_lat"),
        "nisba_ar": author_data.get("nisba_lat"),
        "birth_ah": author_data.get("birth_ah"),
        "death_ah": author_data.get("death_ah"),
    }
    # Remove None values
    author_row = {k: v for k, v in author_row.items() if v is not None}
    resp = client.table("authors").upsert(author_row, on_conflict="openiti_id").execute()
    author_uuid = resp.data[0]["id"]
    logger.info(f"Upserted author: {author_id} -> {author_uuid}")

    # 2. Upsert book
    book_row = {
        "openiti_id": meta.openiti_id,
        "author_id": author_uuid,
        "title_ar": meta.title_ar,
        "title_lat": meta.title_lat,
        "genres": meta.genres,
        "word_count": meta.word_count,
        "char_count": meta.char_count,
        "total_pages": len(result.pages),
        "total_volumes": max((p.volume for p in result.pages), default=1),
        "version_status": meta.version_status,
        "language": meta.language,
        "has_tashkeel": has_tashkeel,
    }
    book_row = {k: v for k, v in book_row.items() if v is not None}
    resp = client.table("books").upsert(book_row, on_conflict="openiti_id").execute()
    book_uuid = resp.data[0]["id"]
    logger.info(f"Upserted book: {meta.openiti_id} -> {book_uuid}")

    # 3. Upsert pages in batches
    for i in range(0, len(result.pages), PAGE_BATCH_SIZE):
        batch = result.pages[i:i + PAGE_BATCH_SIZE]
        page_rows = []
        for page in batch:
            page_rows.append({
                "book_id": book_uuid,
                "page_number": page.page_number,
                "volume": page.volume,
                "content_blocks": json.loads(page.model_dump_json())["content_blocks"],
                "content_plain": page.content_plain,
                "content_hash": page.content_hash,
            })
        resp = client.table("pages").upsert(
            page_rows, on_conflict="book_id,volume,page_number"
        ).execute()
        logger.info(f"Upserted pages {i+1}-{i+len(batch)} / {len(result.pages)}")

    # 4. Upsert chapters
    # First, get page UUIDs for linking
    page_resp = client.table("pages").select("id,page_number,volume").eq(
        "book_id", book_uuid
    ).execute()
    page_map = {(r["volume"], r["page_number"]): r["id"] for r in page_resp.data}

    for chapter in result.chapters:
        page_uuid = page_map.get((1, chapter.page_number))  # Default volume 1
        chapter_row = {
            "book_id": book_uuid,
            "title": chapter.title,
            "level": chapter.level,
            "page_id": page_uuid,
            "sort_order": chapter.sort_order,
        }
        chapter_row = {k: v for k, v in chapter_row.items() if v is not None}
        client.table("chapters").upsert(chapter_row, on_conflict="book_id,sort_order").execute()

    logger.info(f"Upserted {len(result.chapters)} chapters")
```

- [ ] **Step 4: Run tests, verify pass**
- [ ] **Step 5: Commit**

```bash
git add ingestion/upload.py ingestion/tests/test_upload.py
git commit -m "feat(ingestion): add upload stage with batched upserts to Supabase"
```

---

### Task 8: CLI orchestrator

**Files:**
- Create: `ingestion/__main__.py`
- Create: `ingestion/cli.py`

- [ ] **Step 1: Implement cli.py**

```python
# ingestion/cli.py
import argparse

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ingestion", description="Suhuf book ingestion pipeline")
    sub = parser.add_subparsers(dest="command", required=True)

    # ingest command
    ingest = sub.add_parser("ingest", help="Run full pipeline for a book")
    ingest.add_argument("uri", nargs="?", help="OpenITI URI (e.g., 0676Nawawi.ArbacunaNawawiyya)")
    ingest.add_argument("--starter", action="store_true", help="Ingest all 18 starter books")
    ingest.add_argument("--corpus-path", default="./RELEASE", help="Path to OpenITI RELEASE clone")
    ingest.add_argument("--tashkeel-engine", default="sadeed", choices=["sadeed", "shakkala", "none"])
    ingest.add_argument("--force-tashkeel", action="store_true", help="Re-diacritize everything")
    ingest.add_argument("--dump", help="Write intermediate JSON to this directory")
    ingest.add_argument("--dry-run", action="store_true", help="Parse and tashkeel but skip upload")

    # Individual stage commands
    parse_cmd = sub.add_parser("parse", help="Run parse stage only")
    parse_cmd.add_argument("uri", help="OpenITI URI")
    parse_cmd.add_argument("--corpus-path", default="./RELEASE")
    parse_cmd.add_argument("--dump", required=True, help="Output directory for parsed JSON")

    return parser
```

- [ ] **Step 2: Implement __main__.py**

```python
# ingestion/__main__.py
import json
import logging
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

from ingestion.cli import build_parser
from ingestion.corpus import find_book_file, find_author_metadata
from ingestion.metadata import parse_author_yml
from ingestion.parse import parse_file
from ingestion.tashkeel import diacritize_blocks, load_engine
from ingestion.upload import upload_book

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def run_ingest(args):
    load_dotenv()

    if not args.uri and not args.starter:
        logger.error("Provide a URI or use --starter")
        sys.exit(1)

    uris = [args.uri] if args.uri else _get_starter_uris()

    # Load tashkeel engine once (stays warm)
    engine = None
    if args.tashkeel_engine != "none":
        engine = load_engine(args.tashkeel_engine)
        if engine:
            logger.info(f"Loaded tashkeel engine: {args.tashkeel_engine}")
        else:
            logger.warning("No tashkeel engine loaded. Skipping diacritization.")

    # Supabase client (unless dry-run)
    client = None
    if not args.dry_run:
        from supabase import create_client
        url = os.environ["SUPABASE_URL"]
        key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
        client = create_client(url, key)

    for uri in uris:
        logger.info(f"\n{'='*60}\nIngesting: {uri}\n{'='*60}")

        # Stage 1: Parse
        path = find_book_file(uri, corpus_path=args.corpus_path)
        logger.info(f"Found file: {path.name}")
        result = parse_file(path, uri)
        logger.info(f"Parsed: {len(result.pages)} pages, {len(result.chapters)} chapters")

        if args.dump:
            dump_dir = Path(args.dump)
            dump_dir.mkdir(parents=True, exist_ok=True)
            (dump_dir / f"{uri}.parsed.json").write_text(
                result.model_dump_json(indent=2), encoding="utf-8"
            )

        # Stage 2: Tashkeel
        if engine:
            result.pages = diacritize_blocks(result.pages, engine)
            logger.info("Tashkeel complete")

        if args.dump:
            (dump_dir / f"{uri}.tashkeeled.json").write_text(
                result.model_dump_json(indent=2), encoding="utf-8"
            )

        # Stage 3: Upload
        if not args.dry_run and client:
            author_data = {}
            author_yml = find_author_metadata(result.metadata.author_openiti_id, args.corpus_path)
            if author_yml:
                author_data = parse_author_yml(author_yml.read_text(encoding="utf-8").splitlines())

            upload_book(result, author_data, client, has_tashkeel=engine is not None)
            logger.info(f"Uploaded to Supabase")
        elif args.dry_run:
            logger.info("Dry run - skipping upload")

    logger.info("\nDone!")


def _get_starter_uris() -> list[str]:
    return [
        "0676Nawawi.ArbacunaNawawiyya",
        "0676Nawawi.RiyadSalihin",
        "0774IbnKathir.TafsirQuran",
        "0256Bukhari.Sahih",
        "0505Ghazali.IhyaCulumDin",
        # Add remaining 13 as needed
    ]


def main():
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "ingest":
        run_ingest(args)
    elif args.command == "parse":
        path = find_book_file(args.uri, corpus_path=args.corpus_path)
        result = parse_file(path, args.uri)
        dump_dir = Path(args.dump)
        dump_dir.mkdir(parents=True, exist_ok=True)
        (dump_dir / f"{args.uri}.parsed.json").write_text(
            result.model_dump_json(indent=2), encoding="utf-8"
        )
        logger.info(f"Parsed {len(result.pages)} pages -> {args.dump}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Commit**

```bash
git add ingestion/__main__.py ingestion/cli.py
git commit -m "feat(ingestion): add CLI orchestrator with ingest/parse commands"
```

---

### Task 9: End-to-end test with Nawawi

**Requires:** OpenITI RELEASE corpus cloned locally, Supabase migration applied.

- [ ] **Step 1: Clone the RELEASE corpus (one-time)**

```bash
git clone --depth 1 https://github.com/OpenITI/RELEASE.git
```

- [ ] **Step 2: Run parse-only with dump to inspect output**

```bash
cd ingestion && source venv/bin/activate
python -m ingestion parse 0676Nawawi.ArbacunaNawawiyya --corpus-path ../RELEASE --dump ./output
```

Inspect `output/0676Nawawi.ArbacunaNawawiyya.parsed.json`:
- Verify page count (~15-20 pages, starting around page 35)
- Verify hadith blocks have isnad/matn splits
- Verify heading blocks exist for each hadith title
- Verify token IDs follow `p{page}_b{block}_w{word}` pattern

- [ ] **Step 3: Run full pipeline dry-run (with tashkeel=none for speed)**

```bash
python -m ingestion ingest 0676Nawawi.ArbacunaNawawiyya \
  --corpus-path ../RELEASE --tashkeel-engine none --dump ./output --dry-run
```

- [ ] **Step 4: Fix any parsing issues found in the output**

- [ ] **Step 5: Run full pipeline with upload (tashkeel=none first)**

```bash
python -m ingestion ingest 0676Nawawi.ArbacunaNawawiyya \
  --corpus-path ../RELEASE --tashkeel-engine none
```

Verify in Supabase dashboard:
- `authors` table has a row for al-Nawawi
- `books` table has a row with correct metadata
- `pages` table has all pages with JSON content_blocks
- `chapters` table has entries for each hadith heading

- [ ] **Step 6: Re-run to verify idempotency** (no duplicates created)

- [ ] **Step 7: Commit any fixes**

```bash
git add -A && git commit -m "fix(ingestion): adjustments from Nawawi end-to-end test"
```
