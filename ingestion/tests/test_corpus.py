from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from ingestion.corpus import find_author_metadata, find_book_file, parse_uri


# ---------------------------------------------------------------------------
# parse_uri
# ---------------------------------------------------------------------------

def test_parse_uri_valid():
    author, book = parse_uri("0676Nawawi.ArbacunaNawawiyya")
    assert author == "0676Nawawi"
    assert book == "ArbacunaNawawiyya"


def test_parse_uri_another_book():
    author, book = parse_uri("0179Malik.Muwatta")
    assert author == "0179Malik"
    assert book == "Muwatta"


def test_parse_uri_no_dot_raises():
    with pytest.raises(ValueError):
        parse_uri("0676NawawiArbacunaNawawiyya")


def test_parse_uri_empty_raises():
    with pytest.raises(ValueError):
        parse_uri("")


# ---------------------------------------------------------------------------
# find_book_file - quality preference
# ---------------------------------------------------------------------------

def _book_dir(tmp: str, author: str, book: str) -> Path:
    d = Path(tmp) / "data" / author / f"{author}.{book}"
    d.mkdir(parents=True, exist_ok=True)
    return d


def test_find_book_file_prefers_markdown_over_completed():
    with tempfile.TemporaryDirectory() as tmp:
        book_dir = _book_dir(tmp, "0676Nawawi", "ArbacunaNawawiyya")
        (book_dir / "0676Nawawi.ArbacunaNawawiyya.Shamela0012836-ara1.mARkdown").write_text("text")
        (book_dir / "0676Nawawi.ArbacunaNawawiyya.Shamela0012836-ara1.completed").write_text("text")

        result = find_book_file("0676Nawawi.ArbacunaNawawiyya", tmp)
        assert result.suffix == ".mARkdown"


def test_find_book_file_prefers_completed_over_raw():
    with tempfile.TemporaryDirectory() as tmp:
        book_dir = _book_dir(tmp, "0676Nawawi", "ArbacunaNawawiyya")
        (book_dir / "0676Nawawi.ArbacunaNawawiyya.Shamela0012836-ara1.completed").write_text("text")
        (book_dir / "0676Nawawi.ArbacunaNawawiyya.Shamela0012836-ara1").write_text("text")

        result = find_book_file("0676Nawawi.ArbacunaNawawiyya", tmp)
        assert result.suffix == ".completed"


def test_find_book_file_falls_back_to_raw():
    with tempfile.TemporaryDirectory() as tmp:
        book_dir = _book_dir(tmp, "0676Nawawi", "ArbacunaNawawiyya")
        raw = book_dir / "0676Nawawi.ArbacunaNawawiyya.Shamela0012836-ara1"
        raw.write_text("text")

        result = find_book_file("0676Nawawi.ArbacunaNawawiyya", tmp)
        assert result == raw


def test_find_book_file_skips_yml_and_md():
    with tempfile.TemporaryDirectory() as tmp:
        book_dir = _book_dir(tmp, "0676Nawawi", "ArbacunaNawawiyya")
        (book_dir / "0676Nawawi.ArbacunaNawawiyya.yml").write_text("meta")
        (book_dir / "0676Nawawi.ArbacunaNawawiyya.md").write_text("notes")
        raw = book_dir / "0676Nawawi.ArbacunaNawawiyya.Shamela0012836-ara1"
        raw.write_text("text")

        result = find_book_file("0676Nawawi.ArbacunaNawawiyya", tmp)
        assert result == raw


def test_find_book_file_only_yml_md_raises():
    with tempfile.TemporaryDirectory() as tmp:
        book_dir = _book_dir(tmp, "0676Nawawi", "ArbacunaNawawiyya")
        (book_dir / "0676Nawawi.ArbacunaNawawiyya.yml").write_text("meta")
        (book_dir / "0676Nawawi.ArbacunaNawawiyya.md").write_text("notes")

        with pytest.raises(FileNotFoundError):
            find_book_file("0676Nawawi.ArbacunaNawawiyya", tmp)


def test_find_book_file_missing_book_dir_raises():
    with tempfile.TemporaryDirectory() as tmp:
        with pytest.raises(FileNotFoundError):
            find_book_file("0676Nawawi.ArbacunaNawawiyya", tmp)


def test_find_book_file_returns_path_object():
    with tempfile.TemporaryDirectory() as tmp:
        book_dir = _book_dir(tmp, "0179Malik", "Muwatta")
        f = book_dir / "0179Malik.Muwatta.Shamela0001-ara1.mARkdown"
        f.write_text("text")

        result = find_book_file("0179Malik.Muwatta", tmp)
        assert isinstance(result, Path)
        assert result.exists()


# ---------------------------------------------------------------------------
# find_author_metadata
# ---------------------------------------------------------------------------

def test_find_author_metadata_found():
    with tempfile.TemporaryDirectory() as tmp:
        author_dir = Path(tmp) / "data" / "0676Nawawi"
        author_dir.mkdir(parents=True)
        yml = author_dir / "0676Nawawi.yml"
        yml.write_text("name: Nawawi")

        result = find_author_metadata("0676Nawawi", tmp)
        assert result == yml


def test_find_author_metadata_not_found_returns_none():
    with tempfile.TemporaryDirectory() as tmp:
        result = find_author_metadata("0676Nawawi", tmp)
        assert result is None


def test_find_author_metadata_missing_dir_returns_none():
    with tempfile.TemporaryDirectory() as tmp:
        result = find_author_metadata("9999Unknown", tmp)
        assert result is None
