from ingestion.metadata import parse_file_header, parse_author_yml


# ---------------------------------------------------------------------------
# Fixtures: realistic header lines for a Nawawi-like book
# ---------------------------------------------------------------------------

NAWAWI_HEADER = [
    "#META# 020.BookTITLE\t:: الأربعون النووية",
    "#META# 00#VERS#LENGTH###\t:: 3124",
    "#META# 00#VERS#CLENGTH##\t:: 14800",
    "#META# 40#BOOK#GENRE####\t:: Hadith :: Arba`un",
    "#META# 30#BOOK#WROTE##AH\t:: 0660",
    "#META# 10#BOOK#TITLEA#AR\t:: الأربعون في مباني الإسلام وقواعد الأحكام",
    "#META#Header#End#",
    "PageV01P000",
    "بسم الله الرحمن الرحيم",
]

NAWAWI_URI = "0676Nawawi.ArbacunaNawawiyya"


# ---------------------------------------------------------------------------
# parse_file_header – full header
# ---------------------------------------------------------------------------

def test_parse_file_header_title():
    meta = parse_file_header(NAWAWI_HEADER, NAWAWI_URI)
    assert meta.title_ar == "الأربعون النووية"


def test_parse_file_header_author_id():
    meta = parse_file_header(NAWAWI_HEADER, NAWAWI_URI)
    assert meta.author_openiti_id == "0676Nawawi"


def test_parse_file_header_openiti_id():
    meta = parse_file_header(NAWAWI_HEADER, NAWAWI_URI)
    assert meta.openiti_id == NAWAWI_URI


def test_parse_file_header_word_count():
    meta = parse_file_header(NAWAWI_HEADER, NAWAWI_URI)
    assert meta.word_count == 3124


def test_parse_file_header_char_count():
    meta = parse_file_header(NAWAWI_HEADER, NAWAWI_URI)
    assert meta.char_count == 14800


def test_parse_file_header_genres():
    meta = parse_file_header(NAWAWI_HEADER, NAWAWI_URI)
    assert "Hadith" in meta.genres
    assert "Arba`un" in meta.genres


def test_parse_file_header_stops_at_header_end():
    meta = parse_file_header(NAWAWI_HEADER, NAWAWI_URI)
    assert meta.word_count == 3124


def test_parse_file_header_first_title_wins():
    meta = parse_file_header(NAWAWI_HEADER, NAWAWI_URI)
    assert meta.title_ar == "الأربعون النووية"


# ---------------------------------------------------------------------------
# parse_file_header – minimal / missing fields
# ---------------------------------------------------------------------------

MINIMAL_HEADER = [
    "#META# 020.BookTITLE\t:: NODATA",
    "#META# 00#VERS#LENGTH###\t:: NOTGIVEN",
    "#META# 40#BOOK#GENRE####\t:: NODATA",
    "#META#Header#End#",
]

MINIMAL_URI = "0671IbnKhallikan.WafayatAcyan"


def test_parse_file_header_nodata_title_becomes_empty():
    meta = parse_file_header(MINIMAL_HEADER, MINIMAL_URI)
    assert meta.title_ar == ""


def test_parse_file_header_nodata_word_count_is_none():
    meta = parse_file_header(MINIMAL_HEADER, MINIMAL_URI)
    assert meta.word_count is None


def test_parse_file_header_nodata_genres_empty():
    meta = parse_file_header(MINIMAL_HEADER, MINIMAL_URI)
    assert meta.genres == []


def test_parse_file_header_empty_lines_ignored():
    lines = [
        "",
        "PageV01P000",
        "#META# 020.BookTITLE\t:: الأربعون النووية",
        "#META#Header#End#",
    ]
    meta = parse_file_header(lines, NAWAWI_URI)
    assert meta.title_ar == "الأربعون النووية"


def test_parse_file_header_alt_title_key():
    lines = [
        "#META# 10#BOOK#TITLEA#AR\t:: المنهاج شرح صحيح مسلم",
        "#META#Header#End#",
    ]
    meta = parse_file_header(lines, "0676Nawawi.SharhMuslim")
    assert meta.title_ar == "المنهاج شرح صحيح مسلم"


def test_parse_file_header_genre_filters_nodata():
    lines = [
        "#META# 020.BookTITLE\t:: كتاب",
        "#META# 40#BOOK#GENRE####\t:: Fiqh :: NODATA :: Usul",
        "#META#Header#End#",
    ]
    meta = parse_file_header(lines, "0620IbnQudama.Mughni")
    assert "NODATA" not in meta.genres
    assert "Fiqh" in meta.genres
    assert "Usul" in meta.genres


# ---------------------------------------------------------------------------
# parse_author_yml – full fields
# ---------------------------------------------------------------------------

NAWAWI_YML = [
    "10#AUTH#SHUHRA#AR: النووي",
    "10#AUTH#ISM####AR: يحيى",
    "10#AUTH#NASAB##AR: بن شرف",
    "10#AUTH#KUNYA##AR: أبو زكريا",
    "10#AUTH#LAQAB##AR: محيي الدين",
    "10#AUTH#NISBA##AR: النووي الشافعي",
    "30#AUTH#BORN###AH: 0631",
    "30#AUTH#DIED###AH: 0676",
]


def test_parse_author_yml_shuhra():
    data = parse_author_yml(NAWAWI_YML)
    assert data["shuhra_lat"] == "النووي"


def test_parse_author_yml_ism():
    data = parse_author_yml(NAWAWI_YML)
    assert data["ism_lat"] == "يحيى"


def test_parse_author_yml_nasab():
    data = parse_author_yml(NAWAWI_YML)
    assert data["nasab_lat"] == "بن شرف"


def test_parse_author_yml_kunya():
    data = parse_author_yml(NAWAWI_YML)
    assert data["kunya_lat"] == "أبو زكريا"


def test_parse_author_yml_laqab():
    data = parse_author_yml(NAWAWI_YML)
    assert data["laqab_lat"] == "محيي الدين"


def test_parse_author_yml_nisba():
    data = parse_author_yml(NAWAWI_YML)
    assert data["nisba_lat"] == "النووي الشافعي"


def test_parse_author_yml_birth_simple():
    data = parse_author_yml(NAWAWI_YML)
    assert data["birth_ah"] == 631


def test_parse_author_yml_death_simple():
    data = parse_author_yml(NAWAWI_YML)
    assert data["death_ah"] == 676


# ---------------------------------------------------------------------------
# parse_author_yml – date formats with trailing tokens
# ---------------------------------------------------------------------------

def test_parse_author_yml_birth_with_month_code():
    lines = ["30#AUTH#BORN###AH: 0631-MUH-XX"]
    data = parse_author_yml(lines)
    assert data["birth_ah"] == 631


def test_parse_author_yml_death_with_month_code():
    lines = ["30#AUTH#DIED###AH: 0676-SHA-15"]
    data = parse_author_yml(lines)
    assert data["death_ah"] == 676


def test_parse_author_yml_leading_zeros_stripped():
    lines = ["30#AUTH#BORN###AH: 0095"]
    data = parse_author_yml(lines)
    assert data["birth_ah"] == 95


# ---------------------------------------------------------------------------
# parse_author_yml – missing / NODATA values
# ---------------------------------------------------------------------------

def test_parse_author_yml_nodata_skipped():
    lines = [
        "10#AUTH#SHUHRA#AR: النووي",
        "10#AUTH#ISM####AR: NODATA",
    ]
    data = parse_author_yml(lines)
    assert "ism_lat" not in data
    assert data["shuhra_lat"] == "النووي"


def test_parse_author_yml_notgiven_skipped():
    lines = ["30#AUTH#BORN###AH: NOTGIVEN"]
    data = parse_author_yml(lines)
    assert "birth_ah" not in data


def test_parse_author_yml_unknown_keys_ignored():
    lines = [
        "SomeRandomKey: value",
        "10#AUTH#SHUHRA#AR: ابن خلكان",
    ]
    data = parse_author_yml(lines)
    assert list(data.keys()) == ["shuhra_lat"]


def test_parse_author_yml_comment_lines_ignored():
    lines = [
        "# This is a comment",
        "10#AUTH#SHUHRA#AR: ابن خلكان",
    ]
    data = parse_author_yml(lines)
    assert data["shuhra_lat"] == "ابن خلكان"


def test_parse_author_yml_empty_returns_empty_dict():
    data = parse_author_yml([])
    assert data == {}
