"""Tests for tag transfer via alignment.

The model echoes a passage with tags but may drift a few characters. `transfer_tags`
must re-emit the EXACT source text carrying those tags, so the tags-stripped result
is byte-identical to the source even when the model dropped or changed characters.
"""
from ingestion.tag_transfer import transfer_tags
from ingestion.tags import compile_tagged


def _stripped(tagged: str) -> str:
    return compile_tagged(tagged)[0]


def test_identity_when_model_matches():
    source = "عن زيد قال نعم"
    tagged = "<hadith><isnad>عن زيد</isnad><matn> قال نعم</matn></hadith>"
    out = transfer_tags(tagged, source)
    assert out == tagged
    assert _stripped(out) == source


def test_dropped_guillemets_are_recovered():
    # source keeps the «» quote marks; the model dropped them in its echo.
    source = "عن عمر قال «إنما الأعمال بالنيات» رواه البخاري"
    model = "<hadith><isnad>عن عمر قال</isnad> <matn>إنما الأعمال بالنيات</matn> <takhrij>رواه البخاري</takhrij></hadith>"
    out = transfer_tags(model, source)
    assert out is not None
    # the stored text is byte-identical to the source, « » preserved
    assert _stripped(out) == source
    assert "«إنما الأعمال بالنيات»" in _stripped(out)
    # structure survived: one matn covering the body
    _, spans, _ = compile_tagged(out)
    matn = [s for s in spans if s.label == "matn"]
    assert len(matn) == 1
    assert "إنما الأعمال" in _stripped(out)[matn[0].start:matn[0].end]


def test_entity_tags_land_near_their_name():
    source = "حدثنا «محمد بن إسماعيل» قال"
    model = "<isnad>حدثنا <person>محمد بن إسماعيل</person> قال</isnad>"  # dropped « »
    out = transfer_tags(model, source)
    assert out is not None
    assert _stripped(out) == source
    _, spans, _ = compile_tagged(out)
    person = [s for s in spans if s.label == "person"]
    assert len(person) == 1
    assert "محمد بن إسماعيل" in _stripped(out)[person[0].start:person[0].end]


def test_too_different_falls_back_to_none():
    source = "عن زيد قال نعم"
    model = "<matn>كلام مختلف تماما لا يشبه المصدر أبدا</matn>"
    assert transfer_tags(model, source, min_ratio=0.9) is None


def test_no_tags_returns_source():
    source = "نص بلا وسوم"
    assert transfer_tags(source, source) == source


def test_result_always_compiles_and_strips_to_source():
    source = "باب الإخلاص عن عمر قال «الأعمال بالنيات» متفق عليه"
    # realistic drift: chapter title kept as untagged text, only « » dropped
    model = ("باب الإخلاص <hadith><isnad>عن عمر قال</isnad> "
             "<matn>الأعمال بالنيات</matn> <takhrij>متفق عليه</takhrij></hadith>")
    out = transfer_tags(model, source)
    assert out is not None
    assert _stripped(out) == source
