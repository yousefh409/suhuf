from ingestion.metadata import parse_file_header, parse_author_yml

SAMPLE_HEADER_LINES = [
    "######OpenITI#",
    "",
    "",
    "#META# 000.SortField\t:: Shamela_0012836",
    "#META# 010.AuthorNAME\t:: أبو زكريا محيي الدين يحيى بن شرف النووي",
    "#META# 011.AuthorDIED\t:: 676",
    "#META# 020.BookTITLE\t:: الأربعون النووية",
    "#META# 022.BookVOLS\t:: 1",
    "#META# 00#VERS#LENGTH###\t:: 3464",
    "#META# 00#VERS#CLENGTH##\t:: 14399",
    "#META# 40#BOOK#GENRE####\t:: HADITH :: MASANID",
    "",
    "#META#Header#End#",
    "",
    "# بسم الله الرحمن الرحيم",
]

def test_parse_file_header_title():
    meta = parse_file_header(SAMPLE_HEADER_LINES, "0676Nawawi.ArbacunaNawawiyya")
    assert meta.title_ar == "الأربعون النووية"

def test_parse_file_header_author():
    meta = parse_file_header(SAMPLE_HEADER_LINES, "0676Nawawi.ArbacunaNawawiyya")
    assert meta.author_openiti_id == "0676Nawawi"
    assert meta.openiti_id == "0676Nawawi.ArbacunaNawawiyya"

def test_parse_file_header_word_count():
    meta = parse_file_header(SAMPLE_HEADER_LINES, "0676Nawawi.ArbacunaNawawiyya")
    assert meta.word_count == 3464
    assert meta.char_count == 14399

def test_parse_file_header_genres():
    meta = parse_file_header(SAMPLE_HEADER_LINES, "0676Nawawi.ArbacunaNawawiyya")
    assert "HADITH" in meta.genres
    assert "MASANID" in meta.genres

def test_parse_file_header_minimal():
    lines = [
        "######OpenITI#",
        "#META# 020.BookTITLE\t:: كتاب ما",
        "#META#Header#End#",
    ]
    meta = parse_file_header(lines, "0100Someone.SomeBook")
    assert meta.title_ar == "كتاب ما"
    assert meta.word_count is None
    assert meta.genres == []

def test_parse_file_header_nodata_treated_as_missing():
    lines = [
        "######OpenITI#",
        "#META# 020.BookTITLE\t:: NODATA",
        "#META#Header#End#",
    ]
    meta = parse_file_header(lines, "0100Someone.SomeBook")
    # Should fallback to URI when title is NODATA
    assert meta.title_ar == "0100Someone.SomeBook"

SAMPLE_AUTHOR_LINES = [
    "00#AUTH#URI######: 0676Nawawi",
    "10#AUTH#ISM####AR: Yahya",
    "10#AUTH#KUNYA##AR: Abu Zakariyya",
    "10#AUTH#LAQAB##AR: Muhyi al-din",
    "10#AUTH#NASAB##AR: b. Sharaf",
    "10#AUTH#NISBA##AR: al-Nawawi",
    "10#AUTH#SHUHRA#AR: al-Nawawi",
    "30#AUTH#BORN###AH: 0631",
    "30#AUTH#DIED###AH: 0676",
]

def test_parse_author_yml_names():
    data = parse_author_yml(SAMPLE_AUTHOR_LINES)
    assert data["shuhra_lat"] == "al-Nawawi"
    assert data["kunya_lat"] == "Abu Zakariyya"
    assert data["laqab_lat"] == "Muhyi al-din"

def test_parse_author_yml_dates():
    data = parse_author_yml(SAMPLE_AUTHOR_LINES)
    assert data["birth_ah"] == 631
    assert data["death_ah"] == 676

def test_parse_author_yml_empty():
    data = parse_author_yml([])
    assert data["shuhra_lat"] is None
    assert data["birth_ah"] is None
