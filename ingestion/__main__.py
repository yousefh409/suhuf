# ingestion/__main__.py
"""CLI entry point: python -m ingestion <command> [args]"""
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from ingestion.cli import build_parser
from ingestion.corpus import find_book_file, find_author_metadata
from ingestion.metadata import parse_author_yml
from ingestion.parse import parse_file
from ingestion.tashkeel import diacritize_blocks, load_engine

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def _ingest_one(uri: str, args, engine, client):
    """Run the full pipeline for a single book."""
    corpus = args.corpus_path

    # Stage 1: Parse
    path = find_book_file(uri, corpus_path=corpus)
    logger.info(f"Found file: {path.name}")
    result = parse_file(path, uri)
    logger.info(f"Parsed: {len(result.pages)} pages, {len(result.chapters)} chapters")

    if args.dump:
        dump_dir = Path(args.dump)
        dump_dir.mkdir(parents=True, exist_ok=True)
        (dump_dir / f"{uri}.parsed.json").write_text(
            result.model_dump_json(indent=2), encoding="utf-8"
        )

    # Stage 2: Tashkeel
    if engine:
        result.pages = diacritize_blocks(result.pages, engine)
        logger.info("Tashkeel complete")

        if args.dump:
            dump_dir = Path(args.dump)
            (dump_dir / f"{uri}.tashkeeled.json").write_text(
                result.model_dump_json(indent=2), encoding="utf-8"
            )

    # Stage 3: AI enrichment
    enriched_book = {}
    enriched_author = {}
    if not getattr(args, "skip_enrich", False):
        from ingestion.enrich import enrich_book_metadata, enrich_author_metadata
        logger.info("Running AI metadata enrichment...")
        enriched_book = enrich_book_metadata(result)
        if enriched_book:
            logger.info(f"Book enriched: title_en={enriched_book.get('title_en')}, genres={enriched_book.get('genres')}")
        enriched_author = enrich_author_metadata(result.metadata.author_openiti_id, {})
        if enriched_author:
            logger.info(f"Author enriched: {enriched_author.get('full_name_en')}")
    else:
        logger.info("Skipping AI enrichment (--skip-enrich)")

    # Stage 4: Upload
    if not args.dry_run and client:
        from ingestion.upload import upload_book

        author_data = {}
        author_yml = find_author_metadata(result.metadata.author_openiti_id, corpus)
        if author_yml:
            with open(author_yml, encoding="utf-8") as f:
                author_data = parse_author_yml(f.readlines())

        upload_book(
            result, author_data, client,
            has_tashkeel=engine is not None,
            enriched_book=enriched_book,
            enriched_author=enriched_author,
        )
        logger.info(f"Upload complete: {uri}")
    elif args.dry_run:
        logger.info(f"Dry run -- skipping upload for {uri}")


def run_ingest(args):
    """Execute the ingest command."""
    load_dotenv()

    if not args.uri and not args.starter:
        logger.error("Provide a URI or use --starter")
        sys.exit(1)

    uris = [args.uri] if args.uri else []
    if args.starter:
        logger.error("--starter not yet implemented")
        sys.exit(1)

    # Load tashkeel engine once
    engine = None
    if args.tashkeel_engine != "none":
        engine = load_engine(args.tashkeel_engine)
        if engine:
            logger.info(f"Loaded tashkeel engine: {args.tashkeel_engine}")
        else:
            logger.warning("No tashkeel engine available. Skipping diacritization.")

    # Supabase client (unless dry-run)
    client = None
    if not args.dry_run:
        from supabase import create_client
        url = os.environ.get("SUPABASE_URL")
        key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
        if not url or not key:
            logger.error("Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY environment variables")
            sys.exit(1)
        client = create_client(url, key)

    for uri in uris:
        logger.info(f"\n{'='*60}\nIngesting: {uri}\n{'='*60}")
        _ingest_one(uri, args, engine, client)


def run_parse(args):
    """Execute the parse command."""
    uri = args.uri
    path = find_book_file(uri, corpus_path=args.corpus_path)
    logger.info(f"Found file: {path.name}")
    result = parse_file(path, uri)
    logger.info(f"Parsed: {len(result.pages)} pages, {len(result.chapters)} chapters")

    dump_dir = Path(args.dump)
    dump_dir.mkdir(parents=True, exist_ok=True)
    out = dump_dir / f"{uri}.parsed.json"
    out.write_text(result.model_dump_json(indent=2), encoding="utf-8")
    logger.info(f"Wrote: {out}")


def main():
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "ingest":
        run_ingest(args)
    elif args.command == "parse":
        run_parse(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
