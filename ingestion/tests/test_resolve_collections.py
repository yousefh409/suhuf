"""Tests for reclassifying takhrij collection names person -> book_ref."""
from ingestion import tagged_format as tf
from ingestion.resolve_tagged import reclassify_takhrij_sources


def _block(text, spans):
    return tf.Block(key="b0", type="prose", tagged="", text=text,
                    spans=[tf.Span(**s) for s in spans])


def _book(block):
    meta = tf.BookMetadata(openiti_id="t.1", title_ar="x", author_openiti_id="a")
    return tf.Book(metadata=meta, pages=[tf.Page(page_number=1, blocks=[block])])


def test_collection_in_takhrij_becomes_book_ref():
    text = "متفق عليه رواه البخاري ومسلم"
    tk0, tk1 = 0, len(text)
    bi = text.index("البخاري"); mi = text.index("مسلم")
    blk = _block(text, [
        {"start": tk0, "end": tk1, "label": "takhrij"},
        {"start": bi, "end": bi + len("البخاري"), "label": "person"},
        {"start": mi, "end": mi + len("مسلم"), "label": "person"},
    ])
    book = _book(blk)
    n = reclassify_takhrij_sources(book)
    labels = {book.pages[0].blocks[0].text[s.start:s.end]: s.label
              for s in book.pages[0].blocks[0].spans if s.label != "takhrij"}
    assert n == 2
    assert labels["البخاري"] == "book_ref"
    assert labels["مسلم"] == "book_ref"


def test_narrator_collection_name_outside_takhrij_stays_person():
    # Malik as a narrator inside an isnad must remain a person.
    text = "عن مالك عن نافع عن ابن عمر"
    mi = text.index("مالك")
    blk = _block(text, [
        {"start": 0, "end": len(text), "label": "isnad"},
        {"start": mi, "end": mi + len("مالك"), "label": "person"},
    ])
    book = _book(blk)
    n = reclassify_takhrij_sources(book)
    assert n == 0
    assert book.pages[0].blocks[0].spans[1].label == "person"


def test_multiword_collection_abu_dawud():
    text = "رواه أبو داود"
    di = text.index("أبو")
    blk = _block(text, [
        {"start": 0, "end": len(text), "label": "takhrij"},
        {"start": di, "end": len(text), "label": "person"},
    ])
    book = _book(blk)
    assert reclassify_takhrij_sources(book) == 1
    assert book.pages[0].blocks[0].spans[1].label == "book_ref"
