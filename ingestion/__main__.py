# ingestion/__main__.py
"""CLI entry point: python -m ingestion <command> [args]"""
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from ingestion.cli import build_parser

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def run_flow(args):
    """Execute the flow pipeline and dump <uri>.flow.json."""
    # The flow structure pass needs OPENROUTER_API_KEY; load the project .env so
    # the real run picks it up (override empty/stale shell-inherited values).
    load_dotenv(override=True)
    from ingestion.pipeline_flow import build_flow_book
    book, _ = build_flow_book(
        args.uri, corpus_path=args.corpus_path, annotate=not args.skip_annotate,
        tashkeel_engine=args.tashkeel_engine,
    )
    dump_dir = Path(args.dump)
    dump_dir.mkdir(parents=True, exist_ok=True)
    out = dump_dir / f"{args.uri}.flow.json"
    out.write_text(book.model_dump_json(indent=2), encoding="utf-8")
    logger.info(f"Wrote: {out}")

    # Default is dump-only; only write to the DB when --upload is set. The flow
    # path has no author yml in hand, so author_data is None (uploader handles it).
    if getattr(args, "upload", False):
        from supabase import create_client
        from ingestion.upload_flow import upload_flow_book
        url = os.environ.get("SUPABASE_URL")
        key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
        if not url or not key:
            logger.error("Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY environment variables")
            sys.exit(1)
        client = create_client(url, key)
        upload_flow_book(book, client, author_data=None)
        logger.info(f"Upload complete: {args.uri}")


def main():
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "flow":
        run_flow(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
