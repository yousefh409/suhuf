"""SQLite caching layer for PDF extraction and i3rab analysis results."""

import hashlib
import json
import sqlite3
import time
from pathlib import Path
from dataclasses import asdict

from .models import WordI3rab, SentenceAnalysis, DocumentAnalysis


DEFAULT_CACHE_DIR = Path("cache")


class AnalysisCache:
    """SQLite-based cache for i3rab analysis results."""

    def __init__(self, cache_dir: str | Path = DEFAULT_CACHE_DIR):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.cache_dir / "i3rab_cache.db"
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sentence_cache (
                    sentence_hash TEXT PRIMARY KEY,
                    sentence_text TEXT NOT NULL,
                    analysis_json TEXT NOT NULL,
                    created_at REAL NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS document_cache (
                    doc_hash TEXT PRIMARY KEY,
                    title TEXT,
                    analysis_json TEXT NOT NULL,
                    created_at REAL NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS pdf_words_cache (
                    doc_hash TEXT,
                    page_num INTEGER,
                    words_json TEXT NOT NULL,
                    PRIMARY KEY (doc_hash, page_num)
                )
            """)

    @staticmethod
    def hash_text(text: str) -> str:
        """SHA-256 hash of stripped (undiacritized-normalized) text."""
        from .arabic import strip_harakat
        normalized = strip_harakat(text).strip()
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    @staticmethod
    def hash_file(file_path: str) -> str:
        """SHA-256 hash of file bytes."""
        h = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()

    # ── Sentence-level cache ────────────────────────────────────────────

    def get_sentence(self, sentence_text: str) -> SentenceAnalysis | None:
        """Look up cached i3rab analysis for a sentence."""
        h = self.hash_text(sentence_text)
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT analysis_json FROM sentence_cache WHERE sentence_hash = ?",
                (h,)
            ).fetchone()

        if not row:
            return None

        data = json.loads(row[0])
        words = [WordI3rab(**w) for w in data["words"]]
        return SentenceAnalysis(
            sentence_text=data["sentence_text"],
            sentence_index=data["sentence_index"],
            words=words,
        )

    def put_sentence(self, analysis: SentenceAnalysis):
        """Cache i3rab analysis for a sentence."""
        h = self.hash_text(analysis.sentence_text)
        data = {
            "sentence_text": analysis.sentence_text,
            "sentence_index": analysis.sentence_index,
            "words": [asdict(w) for w in analysis.words],
        }
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO sentence_cache (sentence_hash, sentence_text, analysis_json, created_at) VALUES (?, ?, ?, ?)",
                (h, analysis.sentence_text, json.dumps(data, ensure_ascii=False), time.time())
            )

    # ── Document-level cache ────────────────────────────────────────────

    def get_document(self, doc_hash: str) -> DocumentAnalysis | None:
        """Look up cached full document analysis."""
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT analysis_json FROM document_cache WHERE doc_hash = ?",
                (doc_hash,)
            ).fetchone()

        if not row:
            return None

        data = json.loads(row[0])
        sentences = []
        for s in data["sentences"]:
            words = [WordI3rab(**w) for w in s["words"]]
            sentences.append(SentenceAnalysis(
                sentence_text=s["sentence_text"],
                sentence_index=s["sentence_index"],
                words=words,
            ))

        return DocumentAnalysis(
            document_id=data.get("document_id", ""),
            title=data.get("title", ""),
            sentences=sentences,
            total_words=data.get("total_words", 0),
            analyzed_words=data.get("analyzed_words", 0),
        )

    def put_document(self, doc_hash: str, analysis: DocumentAnalysis):
        """Cache full document analysis."""
        data = {
            "document_id": analysis.document_id,
            "title": analysis.title,
            "total_words": analysis.total_words,
            "analyzed_words": analysis.analyzed_words,
            "sentences": [
                {
                    "sentence_text": s.sentence_text,
                    "sentence_index": s.sentence_index,
                    "words": [asdict(w) for w in s.words],
                }
                for s in analysis.sentences
            ],
        }
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO document_cache (doc_hash, title, analysis_json, created_at) VALUES (?, ?, ?, ?)",
                (doc_hash, analysis.title, json.dumps(data, ensure_ascii=False), time.time())
            )

    # ── PDF word positions cache ────────────────────────────────────────

    def get_pdf_words(self, doc_hash: str, page_num: int) -> list[dict] | None:
        """Look up cached word positions for a PDF page."""
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT words_json FROM pdf_words_cache WHERE doc_hash = ? AND page_num = ?",
                (doc_hash, page_num)
            ).fetchone()

        if not row:
            return None
        return json.loads(row[0])

    def put_pdf_words(self, doc_hash: str, page_num: int, words: list[dict]):
        """Cache word positions for a PDF page."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO pdf_words_cache (doc_hash, page_num, words_json) VALUES (?, ?, ?)",
                (doc_hash, page_num, json.dumps(words, ensure_ascii=False))
            )
