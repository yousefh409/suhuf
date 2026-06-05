# Suhuf Project Rules

## Shipping (enforced by hooks — do not bypass)

- Feature branch / worktree → `./bin/suhuf ship`. Raw `git push` is blocked by a PreToolUse hook.
- Direct to `main` → `./bin/suhuf quickfix "msg"`. Never commit on main and push directly.
- Check state any time → `./bin/suhuf status`.
- CI runs `.github/workflows/verify.yml` (`verify` job). Quickfix waits for this to pass before fast-forwarding main.

## Worktrees

- Create: `./bin/suhuf worktree new <branch>` → lands at `.claude/worktrees/<branch>/` off `origin/main`.
- Finish: `./bin/suhuf worktree finish` → runs `suhuf ship` from inside the worktree.
- Prune merged worktrees: `./bin/suhuf worktree prune`.
- Keep all non-current worktrees rebased on main: `./bin/suhuf sync-worktrees`.

## Verify

- `./bin/suhuf verify` runs lint/typecheck/test on packages affected by your diff vs `origin/main`.
- `./bin/suhuf verify --all` runs every package.
- Per-package steps are declared in `scripts/suhuf/src/lib/packages.mjs`. Add tests → they run automatically.

## Packages

- `web/` — Next.js (lint, tsc --noEmit, vitest, build)
- `ingestion/` — Python (compileall, pytest --co)
- `recitation/` — Python (compileall, pytest --co)

Python dirs currently have no real tests; `pytest --co` tolerates exit code 5 so CI stays green until tests are added.

## Current focus: ingestion + format + reader

We're iterating on the ingestion pipeline, book format, and the internal web reader together so the public reader can land on a stable foundation. Dev loop and architecture: [docs/reader/dev-loop.md](docs/reader/dev-loop.md).

TL;DR: edit ingestion → `python -m ingestion ingest <uri> --dump web/data --dry-run --tashkeel-engine shakkala` → open the dumped book directly at `/reader/<openiti_id>` (or `/inspector/<openiti_id>`). Full pipeline (parse + tashkeel + Claude enrichment) runs; `--dry-run` only skips the Supabase upload. Requires `OPENROUTER_API_KEY`.

Note: `/library` is now the product Discover screen (mock-backed catalog browse, part of the dashboard), not the old local-data book index. The dev book-list that listed `web/data/*.json` has been removed — reach an ingested book by its `openiti_id` URL as above.

## Destructive actions

Confirm with the user before: `rm`, `git reset --hard`, force-push outside of `suhuf ship`, dropping a DB, deleting branches.
