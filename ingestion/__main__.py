import json
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
from ingestion.upload import upload_book

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

STARTER_URIS = [
    "0676Nawawi.ArbacunaNawawiyya",
    "0676Nawawi.RiyadSalihin",
    "0774IbnKathir.TafsirQuran",
    "0256Bukhari.Sahih",
    "0505Ghazali.IhyaCulumDin",
]


def run_ingest(args):
    load_dotenv()

    if not args.uri and not args.starter:
        logger.error("Provide a URI or use --starter")
        sys.exit(1)

    uris = [args.uri] if args.uri else STARTER_URIS

    # Load tashkeel engine once (stays warm)
    engine = None
    if args.tashkeel_engine != "none":
        engine = load_engine(args.tashkeel_engine)
        if engine:
            logger.info(f"Loaded tashkeel engine: {args.tashkeel_engine}")
        else:
            logger.warning("No tashkeel engine loaded. Skipping diacritization.")

    # Supabase client (unless dry-run)
    client = None
    if not args.dry_run:
        from supabase import create_client
        url = os.environ["SUPABASE_URL"]
        key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
        client = create_client(url, key)

    for uri in uris:
        logger.info(f"\n{'='*60}\nIngesting: {uri}\n{'='*60}")

        # Stage 1: Parse
        path = find_book_file(uri, corpus_path=args.corpus_path)
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

        if args.dump and engine:
            (dump_dir / f"{uri}.tashkeeled.json").write_text(
                result.model_dump_json(indent=2), encoding="utf-8"
            )

        # Stage 3: Upload
        if not args.dry_run and client:
            author_data = {}
            author_yml = find_author_metadata(result.metadata.author_openiti_id, args.corpus_path)
            if author_yml:
                author_data = parse_author_yml(author_yml.read_text(encoding="utf-8").splitlines())

            upload_book(result, author_data, client, has_tashkeel=engine is not None)
            logger.info("Uploaded to Supabase")
        elif args.dry_run:
            logger.info("Dry run - skipping upload")

    logger.info("\nDone!")


def run_parse(args):
    path = find_book_file(args.uri, corpus_path=args.corpus_path)
    result = parse_file(path, args.uri)
    dump_dir = Path(args.dump)
    dump_dir.mkdir(parents=True, exist_ok=True)
    (dump_dir / f"{args.uri}.parsed.json").write_text(
        result.model_dump_json(indent=2), encoding="utf-8"
    )
    logger.info(f"Parsed {len(result.pages)} pages -> {args.dump}")


def main():
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "ingest":
        run_ingest(args)
    elif args.command == "parse":
        run_parse(args)


if __name__ == "__main__":
    main()
