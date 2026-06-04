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
from ingestion.enrich import resolve_spans
from ingestion.hadith import detect_hadith_structure
from ingestion.parse import parse_file
from ingestion.tashkeel import diacritize_blocks, load_engine

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


_TASHKEEL_RE = __import__("re").compile(r"[\u064B-\u065F\u0670]")


def _pages_have_tashkeel(result, sample_budget: int = 100) -> bool:
    """Sample tokens until we find a diacritic or exhaust the budget."""
    sampled = 0
    for page in result.pages:
        for block in page.content_blocks:
            tokens = []
            if block.type == "poetry":
                for verse in block.hemistichs:
                    for hemistich in verse:
                        tokens.extend(hemistich)
            else:
                tokens = block.tokens
            for t in tokens:
                if _TASHKEEL_RE.search(t.text):
                    return True
                sampled += 1
                if sampled >= sample_budget:
                    return False
    return False


def _ingest_one(uri: str, args, engine, client):
    """Run the full pipeline for a single book."""
    import json

    corpus = args.corpus_path

    # Stage 1: Parse
    path = find_book_file(uri, corpus_path=corpus)
    logger.info(f"Found file: {path.name}")
    result = parse_file(path, uri)
    logger.info(f"Parsed: {len(result.pages)} pages, {len(result.chapters)} chapters")

    # Deterministic hadith-structure pass (isnad/matn/takhrij spans) — runs
    # before the parsed.json dump so the structure is part of the parse tier.
    hstats = detect_hadith_structure(result)
    logger.info(
        f"Hadith structure: {hstats['matn']} matn, {hstats['isnad']} isnad, "
        f"{hstats['takhrij']} takhrij ({hstats['high_conf']} high / {hstats['low_conf']} low conf)"
    )

    # Author yml — used by enrichment context, dump, and upload
    author_data: dict = {}
    author_yml = find_author_metadata(result.metadata.author_openiti_id, corpus)
    if author_yml:
        with open(author_yml, encoding="utf-8") as f:
            author_data = parse_author_yml(f.readlines())

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

        if not _pages_have_tashkeel(result):
            # Engine ran but produced no diacritics. Loud warning so the
            # operator notices — a tashkeel-less enriched.json silently
            # shadows a good prior tashkeeled.json on the reader side.
            logger.warning(
                "Tashkeel engine ran but no diacritics were added. "
                "The enriched.json dump will be missing tashkeel."
            )

        if args.dump:
            dump_dir = Path(args.dump)
            (dump_dir / f"{uri}.tashkeeled.json").write_text(
                result.model_dump_json(indent=2), encoding="utf-8"
            )

    # Stage 3a: Claude annotation pass (block relabel + inline spans + quality flags)
    annotate_stats: dict = {}
    if not getattr(args, "skip_annotate", False):
        from ingestion.annotate import annotate_book
        logger.info("Running annotation pass...")
        annotate_stats = annotate_book(result, force=getattr(args, "force_annotate", False))
        relabel_allowed = annotate_stats.get("relabel_allowed", True)
        relabel_note = "" if relabel_allowed else " (relabel suppressed — native tags)"
        logger.info(
            f"Annotated: {annotate_stats.get('relabeled', 0)} relabeled, "
            f"{annotate_stats.get('spans_total', 0)} spans, "
            f"{annotate_stats.get('flags_total', 0)} flags "
            f"({annotate_stats.get('input_tokens', 0)} in / "
            f"{annotate_stats.get('output_tokens', 0)} out tokens)"
            f"{relabel_note}"
        )

        if args.dump:
            dump_dir = Path(args.dump)
            (dump_dir / f"{uri}.annotated.json").write_text(
                result.model_dump_json(indent=2), encoding="utf-8"
            )
    else:
        logger.info("Skipping annotation pass (--skip-annotate)")

    # Stage 3b: AI enrichment
    enriched_book: dict = {}
    enriched_author: dict = {}
    if not getattr(args, "skip_enrich", False):
        from ingestion.enrich import enrich_book_metadata, enrich_author_metadata
        logger.info("Running AI metadata enrichment...")
        enriched_book = enrich_book_metadata(result)
        if enriched_book:
            logger.info(f"Book enriched: title_en={enriched_book.get('title_en')}, genres={enriched_book.get('genres')}")
        enriched_author = enrich_author_metadata(
            result.metadata.author_openiti_id, author_data
        )
        if enriched_author:
            logger.info(f"Author enriched: {enriched_author.get('full_name_en')}")
    else:
        logger.info("Skipping AI enrichment (--skip-enrich)")

    # Resolve quran span refs — deterministic, no AI client needed.
    # Runs regardless of --skip-enrich so resolved refs are always serialized.
    resolved_count = resolve_spans(result)
    logger.info(f"Resolved {resolved_count} quran span refs")

    # Dump full pipeline output (parse + tashkeel + enrichment + author yml)
    if args.dump:
        dump_dir = Path(args.dump)
        full = {
            **json.loads(result.model_dump_json()),
            "enrichment": {
                "book": enriched_book,
                "author": enriched_author,
            },
            "author_data": author_data,
        }
        (dump_dir / f"{uri}.enriched.json").write_text(
            json.dumps(full, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        logger.info(f"Wrote: {dump_dir / f'{uri}.enriched.json'}")

    # Stage 4: Upload
    if not args.dry_run and client:
        from ingestion.upload import upload_book
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
    # override=True lets the project .env beat empty/stale shell-inherited
    # values (e.g. OPENROUTER_API_KEY="" leaking from a parent process).
    load_dotenv(override=True)

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
    detect_hadith_structure(result)

    dump_dir = Path(args.dump)
    dump_dir.mkdir(parents=True, exist_ok=True)
    out = dump_dir / f"{uri}.parsed.json"
    out.write_text(result.model_dump_json(indent=2), encoding="utf-8")
    logger.info(f"Wrote: {out}")


def run_tagged(args):
    """Execute the tagged-format pipeline and dump <uri>.book.json."""
    from ingestion.pipeline_tagged import build_tagged_book
    book, _ = build_tagged_book(
        args.uri, corpus_path=args.corpus_path, annotate=not args.skip_annotate,
        tashkeel_engine=args.tashkeel_engine,
    )
    dump_dir = Path(args.dump)
    dump_dir.mkdir(parents=True, exist_ok=True)
    out = dump_dir / f"{args.uri}.book.json"
    out.write_text(book.model_dump_json(indent=2), encoding="utf-8")
    logger.info(f"Wrote: {out}")


def run_flow(args):
    """Execute the flow pipeline and dump <uri>.flow.json."""
    # The flow structure pass needs OPENROUTER_API_KEY; load the project .env so
    # the real run picks it up (override empty/stale shell-inherited values).
    load_dotenv(override=True)
    from ingestion.pipeline_flow import build_flow_book
    book, _ = build_flow_book(
        args.uri, corpus_path=args.corpus_path, annotate=not args.skip_annotate
    )
    dump_dir = Path(args.dump)
    dump_dir.mkdir(parents=True, exist_ok=True)
    out = dump_dir / f"{args.uri}.flow.json"
    out.write_text(book.model_dump_json(indent=2), encoding="utf-8")
    logger.info(f"Wrote: {out}")


def main():
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "ingest":
        run_ingest(args)
    elif args.command == "parse":
        run_parse(args)
    elif args.command == "tagged":
        run_tagged(args)
    elif args.command == "flow":
        run_flow(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
