# Suhuf

Suhuf is a reading and recitation platform for classical Arabic and Islamic texts. It combines a catalog of fully-diacritized books with a live read-along engine that corrects mistakes in tashkeel, i'rab, and wrong words as a student reads aloud.

Think Tarteel, but for any Arabic text — not just Quran.

## Monorepo layout

| Package | Stack | Purpose |
|---|---|---|
| [`web/`](web) | Next.js 16, React 19, Tailwind, Cloudflare (OpenNext) | Marketing site + future web surfaces. |
| [`ingestion/`](ingestion) | Python | Pipeline that parses OpenITI mARkdown → adds tashkeel (Mishkal/Shakkala) → AI enrichment → uploads to Supabase. |
| [`recitation/`](recitation) | Python, PyTorch, FastAPI | Live read-along engine built on a fine-tuned XLS-R 300M CTC model (`models/ssl_xls_r_v5/`). Scores audio against known diacritized text to flag wrong words, i'rab errors, and tashkeel errors. |
| [`supabase/`](supabase) | SQL | Schema and migrations for the shared backend. |
| [`scripts/suhuf/`](scripts/suhuf) | Node | Internal shipping CLI (see below). |

Recitation product brief: [`recitation/ONE-PAGER.md`](recitation/ONE-PAGER.md).
Longer-form docs: [`docs/`](docs).

## The `suhuf` CLI

All shipping goes through `./bin/suhuf`. Raw `git push` on main is blocked by a hook.

```
suhuf ship             Rebase feature branch onto origin/main, verify, force-with-lease push
suhuf quickfix "msg"   Commit on main, push quickfix/<ts> branch, wait for CI green, fast-forward main
suhuf verify           Run lint / typecheck / test for packages affected by diff vs origin/main
suhuf verify --all     Run every package
suhuf status           Branch + worktree + drift summary
suhuf worktree new <branch>   Create worktree at .claude/worktrees/<branch>/ off origin/main
suhuf worktree finish         Ship the current worktree
suhuf worktree prune          Remove merged worktrees
suhuf sync-worktrees          Rebase every non-current worktree onto origin/main
```

`quickfix` never touches `main` until `.github/workflows/verify.yml` passes on the temporary branch.

## Verify

Per-package steps are declared in [`scripts/suhuf/src/lib/packages.mjs`](scripts/suhuf/src/lib/packages.mjs):

- `web/` — `npm run lint`, `tsc --noEmit`, `npm run build`
- `ingestion/` — `python -m compileall`, `pytest --co`
- `recitation/` — `python -m compileall`, `pytest --co`

Python packages tolerate `pytest` exit code 5 (no tests collected) until real tests land.

## Getting started

```bash
# Web
cd web && npm install && npm run dev

# Ingestion / recitation
cd ingestion    # or recitation
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
```

Supabase credentials (`SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`) and other service keys are read from `.env`. See `.env.example`.

## Project rules

See [`CLAUDE.md`](CLAUDE.md) for the enforced rules — especially that shipping to `main` only happens through `suhuf quickfix`, and destructive operations require confirmation.
