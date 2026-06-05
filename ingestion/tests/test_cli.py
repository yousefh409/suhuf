from ingestion.cli import build_parser


def test_flow_command_parses():
    parser = build_parser()
    args = parser.parse_args(["flow", "0676Nawawi.ArbacunaNawawiyya", "--dump", "./out"])
    assert args.command == "flow"
    assert args.uri == "0676Nawawi.ArbacunaNawawiyya"
    assert args.corpus_path == "./RELEASE"
    assert args.dump == "./out"
    assert args.skip_annotate is False
    assert args.skip_enrich is False
    assert args.upload is False


def test_flow_skip_annotate():
    parser = build_parser()
    args = parser.parse_args(
        ["flow", "0676Nawawi.ArbacunaNawawiyya", "--dump", "./out", "--skip-annotate"]
    )
    assert args.skip_annotate is True


def test_flow_skip_enrich():
    parser = build_parser()
    args = parser.parse_args(
        ["flow", "0676Nawawi.ArbacunaNawawiyya", "--dump", "./out", "--skip-enrich"]
    )
    assert args.skip_enrich is True


def test_flow_upload_flag():
    parser = build_parser()
    args = parser.parse_args(
        ["flow", "0676Nawawi.ArbacunaNawawiyya", "--dump", "./out", "--upload"]
    )
    assert args.upload is True
