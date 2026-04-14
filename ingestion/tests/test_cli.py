from ingestion.cli import build_parser


def test_ingest_command_parses():
    parser = build_parser()
    args = parser.parse_args(["ingest", "0676Nawawi.ArbacunaNawawiyya"])
    assert args.command == "ingest"
    assert args.uri == "0676Nawawi.ArbacunaNawawiyya"
    assert args.corpus_path == "./RELEASE"
    assert args.tashkeel_engine == "shakkala"
    assert args.dry_run is False


def test_ingest_dry_run():
    parser = build_parser()
    args = parser.parse_args(["ingest", "0676Nawawi.ArbacunaNawawiyya", "--dry-run"])
    assert args.dry_run is True


def test_ingest_tashkeel_none():
    parser = build_parser()
    args = parser.parse_args(["ingest", "0676Nawawi.ArbacunaNawawiyya", "--tashkeel-engine", "none"])
    assert args.tashkeel_engine == "none"


def test_parse_command_parses():
    parser = build_parser()
    args = parser.parse_args(["parse", "0676Nawawi.ArbacunaNawawiyya", "--dump", "./output"])
    assert args.command == "parse"
    assert args.uri == "0676Nawawi.ArbacunaNawawiyya"
    assert args.dump == "./output"


def test_ingest_starter_flag():
    parser = build_parser()
    args = parser.parse_args(["ingest", "--starter"])
    assert args.starter is True
    assert args.uri is None


def test_ingest_with_dump():
    parser = build_parser()
    args = parser.parse_args(["ingest", "0676Nawawi.ArbacunaNawawiyya", "--dump", "/tmp/debug"])
    assert args.dump == "/tmp/debug"
