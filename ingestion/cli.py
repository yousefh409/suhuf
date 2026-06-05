import argparse


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ingestion", description="Suhuf book ingestion pipeline")
    sub = parser.add_subparsers(dest="command", required=True)

    # flow command: continuous tagged, page-sliced format (parse -> assemble ->
    # chunk -> AI structure -> number -> slice), dumps <uri>.flow.json
    flow_cmd = sub.add_parser("flow", help="Build the continuous-tagged page-sliced book")
    flow_cmd.add_argument("uri", help="OpenITI URI")
    flow_cmd.add_argument("--corpus-path", default="./RELEASE")
    flow_cmd.add_argument("--dump", required=True, help="Output directory for <uri>.flow.json")
    flow_cmd.add_argument("--skip-annotate", action="store_true",
                          help="Skip the Claude flow structure pass (no API)")
    flow_cmd.add_argument("--tashkeel-engine", default="shakkala",
                          choices=["shakkala", "flan-t5", "sadeed", "none"],
                          help="Diacritization engine for the assembled text (none = skip)")
    flow_cmd.add_argument("--upload", action="store_true",
                          help="Upload the built flow book to Supabase (default: dump only)")

    return parser
