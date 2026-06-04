"""End-to-end tests for the flow pipeline (offline, mocked AI).

The win this format buys: a hadith stored across a page boundary comes out as ONE
``<hadith>`` with ONE ``<matn>`` spanning the pages, because structure is tagged
on the continuous document BEFORE it is sliced into pages. These tests build a
synthetic parsed book whose hadith 2 straddles the page 2 -> 3 boundary, run the
pipeline with a mock client that wraps each chunk in a realistic hadith, and
assert the cross-page hadith is whole.
"""
import json

from ingestion.models import Block, Token, Page, ParseResult, BookMetadata
from ingestion.pipeline_flow import flow_from_result
from ingestion.tags import compile_tagged
from ingestion.page_slice import reconstruct, PageSlice


# ── fixture: hadith 2 straddles the page 2 -> 3 boundary ─────────────────────

def _toks(page, key, words):
    return [Token(id=f"p{page}_{key}_w{i}", text=w) for i, w in enumerate(words)]


def _heading(page, key, words):
    return Block(key=key, type="heading", level=3, tokens=_toks(page, key, words))


def _prose(page, key, words):
    return Block(key=key, type="prose", tokens=_toks(page, key, words))


def _fixture():
    meta = BookMetadata(openiti_id="t.1", title_ar="x", author_openiti_id="a")
    p1 = Page(page_number=1, content_blocks=[
        _heading(1, "b0", ["الحديث", "الأول"]),
        _prose(1, "b1", ["عن", "عمر", "قال", "الأعمال"]),
    ])
    p2 = Page(page_number=2, content_blocks=[
        _heading(2, "b0", ["الحديث", "الثاني"]),
        _prose(2, "b1", ["عن", "عمر", "أيضا", "بينما"]),  # isnad + start of matn
    ])
    p3 = Page(page_number=3, content_blocks=[
        _prose(3, "b0", ["نحن", "جلوس", "عند", "النبي"]),  # continuation of matn
    ])
    return ParseResult(metadata=meta, pages=[p1, p2, p3])


class _Resp:
    """Mimics an OpenAI-compatible (OpenRouter) chat completion response."""
    def __init__(self, text):
        msg = type("M", (), {"content": text})()
        self.choices = [type("Ch", (), {"message": msg})()]
        self.usage = type("U", (), {"prompt_tokens": 1, "completion_tokens": 1})()


def _wrap_one_hadith(segment: str) -> str:
    """Wrap one heading+body segment as <hadith>, preserving words exactly.

    A segment is "الحديث الأول عن عمر قال الأعمال ...": the first two words are the
    heading (left untagged), the next three are the isnad, the rest is the matn.
    Join spaces are kept INSIDE tags so the tags-stripped text equals the input.
    """
    words = segment.split(" ")
    head = " ".join(words[:2])
    isnad = " ".join(words[2:5])
    matn = " ".join(words[5:])
    return (f"{head} <hadith><isnad>{isnad}</isnad>"
            f"<matn> {matn}</matn></hadith>")


class _HadithWrappingClient:
    """Realistically wraps EACH hadith in a chunk separately.

    The chunk may contain one or more hadiths (each begins with "الحديث"). We
    split the chunk at each "الحديث" and wrap every segment. The key property the
    pipeline must preserve: ONE matn per hadith, spanning the whole body even
    when a page break later falls in the middle of it.
    """
    def __init__(self):
        self.chat = self
        self.completions = self

    def create(self, *, model, max_tokens, messages):
        user = messages[1]["content"]
        payload = json.loads(user[user.find("{"):user.rfind("}") + 1])
        chunk = payload["text"]
        words = chunk.split(" ")
        # split into segments, each starting at a "الحديث" heading word
        segments, cur = [], []
        for w in words:
            if w == "الحديث" and cur:
                segments.append(cur)
                cur = [w]
            else:
                cur.append(w)
        if cur:
            segments.append(cur)
        tagged = " ".join(_wrap_one_hadith(" ".join(seg)) for seg in segments)
        return _Resp(json.dumps({"tagged": tagged}, ensure_ascii=False))


def _matn_spans(tagged: str):
    _, spans, _ = compile_tagged(tagged)
    return [s for s in spans if s.label == "matn"]


def test_page_fragments_reconstruct_to_numbered_tagged():
    book, stats = flow_from_result(_fixture(), annotate=True,
                                   client=_HadithWrappingClient())
    slices = [PageSlice(tagged=p.tagged, open_tags=p.open_tags) for p in book.pages]
    assert reconstruct(slices) == stats["tagged"]


def test_cross_page_hadith_is_one_hadith_one_matn():
    book, stats = flow_from_result(_fixture(), annotate=True,
                                   client=_HadithWrappingClient())
    # reconstruct the whole continuous doc and compile it
    full = reconstruct([PageSlice(tagged=p.tagged, open_tags=p.open_tags)
                        for p in book.pages])
    text, spans, _ = compile_tagged(full)
    hadiths = [s for s in spans if s.label == "hadith"]
    assert len(hadiths) == 2                       # two whole hadiths
    matns = [s for s in spans if s.label == "matn"]
    # hadith 2's matn must be a SINGLE span covering its whole body across pages
    h2 = sorted(hadiths, key=lambda s: s.start)[1]
    h2_matns = [m for m in matns if h2.start <= m.start and m.end <= h2.end]
    assert len(h2_matns) == 1
    matn_text = text[h2_matns[0].start:h2_matns[0].end]
    assert "بينما" in matn_text and "النبي" in matn_text   # spans both pages


def test_annotations_contain_hadith_id_for_cross_page_hadith():
    book, _ = flow_from_result(_fixture(), annotate=True,
                               client=_HadithWrappingClient())
    hadith_anns = [a for a in book.annotations if a.label == "hadith"]
    assert len(hadith_anns) == 2
    assert all(a.id.startswith("h") for a in hadith_anns)
    # the second hadith's range spans into the page-3 text
    page3 = next(p for p in book.pages if p.page_number == 3)
    h2 = sorted(hadith_anns, key=lambda a: a.start)[1]
    assert h2.start < page3.start_offset < h2.end


def test_continuation_page_open_tags():
    book, _ = flow_from_result(_fixture(), annotate=True,
                               client=_HadithWrappingClient())
    page3 = next(p for p in book.pages if p.page_number == 3)
    names = [t.name for t in page3.open_tags]
    # page 3 opens inside hadith 2's matn -> hadith + matn are open
    assert "hadith" in names and "matn" in names
    # the hadith open tag carries its id
    hadith_open = next(t for t in page3.open_tags if t.name == "hadith")
    assert hadith_open.id is not None and hadith_open.id.startswith("h")


def test_annotate_false_yields_plain_flowbook():
    book, stats = flow_from_result(_fixture(), annotate=False, client=None)
    # no structure tags: the continuous tagged equals the plain assembled text
    full = reconstruct([PageSlice(tagged=p.tagged, open_tags=p.open_tags)
                        for p in book.pages])
    assert "<hadith>" not in full
    assert compile_tagged(full)[0] == full   # no tags at all
    assert book.annotations == []
    # page texts still set, fragments still reconstruct
    assert full == stats["tagged"]


def test_metadata_and_chapters_carried():
    result = _fixture()
    book, _ = flow_from_result(result, annotate=False, client=None)
    assert book.metadata.openiti_id == "t.1"
    assert len(book.pages) == 3
