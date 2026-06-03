"""Tests for poetry detection in the ingestion parser.

Covers both the original %~% hemistich separator and the %-wrapped format
used in many real OpenITI diwans (e.g. al-Mutanabbi).
"""

from pathlib import Path

from ingestion.parse import parse_file


def _make_book(tmp_path: Path, lines: list[str]) -> Path:
    """Write a minimal OpenITI mARkdown file with the given body lines."""
    src = tmp_path / "test_book.mARkdown"
    header = (
        "######OpenITI#\n"
        "#META# 020.BookTITLE\t:: اختبار\n"
        "#META# 00#VERS#LENGTH###\t:: 5\n"
        "#META#Header#End#\n"
        "# PageV01P001\n"
    )
    src.write_text(header + "\n".join(lines) + "\n", encoding="utf-8")
    return src


def test_percent_wrapped_verse_two_hemistichs(tmp_path):
    """A line with two %-wrapped hemistichs and a trailing verse number should
    produce exactly one poetry block with 1 verse, 2 hemistichs, correct tokens,
    and the verse number set on block.number."""
    src = _make_book(
        tmp_path,
        ["# % أتنكر يا ابن إسحق إخائي % % وتحسب ماء غيري من إنائي ؟ % 2"],
    )
    result = parse_file(src, "0100Test.PoetryBook")
    assert len(result.pages) == 1
    page = result.pages[0]

    poetry_blocks = [b for b in page.content_blocks if b.type == "poetry"]
    assert len(poetry_blocks) == 1, f"Expected 1 poetry block, got {len(poetry_blocks)}"

    block = poetry_blocks[0]
    # hemistichs structure: outer = verses, middle = hemistichs, inner = tokens
    assert len(block.hemistichs) == 1, "Expected 1 verse"
    verse = block.hemistichs[0]
    assert len(verse) == 2, f"Expected 2 hemistichs, got {len(verse)}"

    h1_texts = [t.text for t in verse[0]]
    assert "أتنكر" in h1_texts, f"First hemistich missing 'أتنكر'; got {h1_texts}"

    h2_texts = [t.text for t in verse[1]]
    assert "وتحسب" in h2_texts, f"Second hemistich missing 'وتحسب'; got {h2_texts}"

    assert block.number == "2", f"Expected block.number == '2', got {block.number!r}"


def test_percent_wrapped_single_percent_separator(tmp_path):
    """A line with single % between the two hemistichs (no double %%) parses
    correctly to 1 poetry block, 2 hemistichs, verse number '6'."""
    src = _make_book(
        tmp_path,
        ["# % وهبني قلت : هذا الصبح ليل % أيعمى العالمون عن الضياء ؟ % 6"],
    )
    result = parse_file(src, "0100Test.PoetryBook")
    page = result.pages[0]

    poetry_blocks = [b for b in page.content_blocks if b.type == "poetry"]
    assert len(poetry_blocks) == 1, f"Expected 1 poetry block, got {len(poetry_blocks)}"

    block = poetry_blocks[0]
    assert len(block.hemistichs) == 1
    verse = block.hemistichs[0]
    assert len(verse) == 2, f"Expected 2 hemistichs, got {len(verse)}"

    all_texts = [t.text for h in verse for t in h]
    assert "وهبني" in all_texts
    assert "أيعمى" in all_texts

    assert block.number == "6", f"Expected block.number == '6', got {block.number!r}"


def test_existing_tilde_poetry_still_works(tmp_path):
    """The original %~% hemistich format must continue to parse as poetry (regression guard)."""
    src = _make_book(
        tmp_path,
        ["# قفا نبك %~% بسقط اللوى"],
    )
    result = parse_file(src, "0100Test.TildeBook")
    page = result.pages[0]

    poetry_blocks = [b for b in page.content_blocks if b.type == "poetry"]
    assert len(poetry_blocks) == 1, "Tilde-format poetry must still be detected"

    verse = poetry_blocks[0].hemistichs[0]
    assert len(verse) == 2, f"Expected 2 hemistichs in tilde-format verse, got {len(verse)}"

    h1_texts = [t.text for t in verse[0]]
    assert "قفا" in h1_texts
    assert "نبك" in h1_texts

    h2_texts = [t.text for t in verse[1]]
    assert "بسقط" in h2_texts


def test_no_poetry_block_for_plain_prose(tmp_path):
    """A plain Arabic prose line with no % markers must parse as prose, not poetry."""
    src = _make_book(
        tmp_path,
        ["# هذا نص عادي بدون أي علامات شعرية"],
    )
    result = parse_file(src, "0100Test.ProseBook")
    page = result.pages[0]

    poetry_blocks = [b for b in page.content_blocks if b.type == "poetry"]
    assert len(poetry_blocks) == 0, f"Plain prose should not produce poetry blocks; got {poetry_blocks}"

    prose_blocks = [b for b in page.content_blocks if b.type == "prose"]
    assert len(prose_blocks) == 1, "Plain prose line should produce exactly one prose block"
