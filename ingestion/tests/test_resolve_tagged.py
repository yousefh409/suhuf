"""Tests for the tagged-format resolution passes."""
from ingestion import tagged_format as tf
from ingestion.resolve_tagged import resolve_quran_refs


def _book_with_quran(text, start, end):
    blk = tf.Block(key="b0", type="prose", tagged="", text=text,
                   spans=[tf.Span(start=start, end=end, label="quran")])
    meta = tf.BookMetadata(openiti_id="t.1", title_ar="x", author_openiti_id="a")
    return tf.Book(metadata=meta, pages=[tf.Page(page_number=1, blocks=[blk])])


def test_resolve_quran_ref_on_offset_span():
    text = "قال تعالى الحمد لله رب العالمين بعد ذلك"
    start = text.index("الحمد")
    end = text.index("العالمين") + len("العالمين")
    book = _book_with_quran(text, start, end)
    n = resolve_quran_refs(book)
    span = book.pages[0].blocks[0].spans[0]
    assert n == 1
    assert span.ref == "1:2"   # al-Fatiha: الحمد لله رب العالمين


def test_resolve_ignores_non_quran_spans():
    blk = tf.Block(key="b0", type="prose", tagged="", text="عن أبي هريرة",
                   spans=[tf.Span(start=0, end=12, label="isnad")])
    meta = tf.BookMetadata(openiti_id="t.1", title_ar="x", author_openiti_id="a")
    book = tf.Book(metadata=meta, pages=[tf.Page(page_number=1, blocks=[blk])])
    assert resolve_quran_refs(book) == 0
    assert book.pages[0].blocks[0].spans[0].ref is None
