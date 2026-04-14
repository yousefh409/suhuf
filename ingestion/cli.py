import argparse


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ingestion", description="Suhuf book ingestion pipeline")
    sub = parser.add_subparsers(dest="command", required=True)

    # ingest command
    ingest = sub.add_parser("ingest", help="Run full pipeline for a book")
    ingest.add_argument("uri", nargs="?", help="OpenITI URI (e.g., 0676Nawawi.ArbacunaNawawiyya)")
    ingest.add_argument("--starter", action="store_true", help="Ingest all starter books")
    ingest.add_argument("--corpus-path", default="./RELEASE", help="Path to OpenITI RELEASE clone")
    ingest.add_argument("--tashkeel-engine", default="shakkala", choices=["shakkala", "flan-t5", "sadeed", "none"])
    ingest.add_argument("--force-tashkeel", action="store_true", help="Re-diacritize everything")
    ingest.add_argument("--dump", help="Write intermediate JSON to this directory")
    ingest.add_argument("--dry-run", action="store_true", help="Parse and tashkeel but skip upload")
    ingest.add_argument("--skip-enrich", action="store_true", help="Skip AI metadata enrichment")

    # parse command
    parse_cmd = sub.add_parser("parse", help="Run parse stage only")
    parse_cmd.add_argument("uri", help="OpenITI URI")
    parse_cmd.add_argument("--corpus-path", default="./RELEASE")
    parse_cmd.add_argument("--dump", required=True, help="Output directory for parsed JSON")

    return parser
