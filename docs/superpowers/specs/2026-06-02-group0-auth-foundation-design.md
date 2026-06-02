# Group 0 — Foundation: Auth + Reader Gating

Date: 2026-06-02
Status: Approved (brainstorming)

## Goal

Add Supabase email + password authentication (login + signup), and gate the
reader behind it. There is currently no auth anywhere in `web/src`. The reader
is effectively ungated — middleware only rate-limits `/api/*`.

This is the foundation only. It deliberately does **not** change where the
reader gets its data.

## Scope

In scope:

- Email + password auth via Supabase (login + signup, instant session).
- A single `/login` page with a login / signup toggle.
- A minimal `/dashboard` landing page (post-login home).
- Move the reader surfaces out of `/internal` to the site root.
- Gate the reader surfaces behind auth via middleware.

Out of scope (deferred to a later group):

- Moving reader data to Supabase / Postgres. The reader keeps reading local
  files from `web/data/<openiti_id>.*.json` via `web/src/lib/reader/queries.ts`.
  Reason: a separate workstream is iterating on the book/ingestion JSON format,
  and the dev loop is intentionally local-file-driven. Reading from Postgres now
  would force a re-upload on every format change.
- Book uploads, profile management, persisting user library / bookmarks /
  reading positions (the tables exist but stay unused here).

## Decisions

- **Gate covers all reader surfaces** — reader, library, and inspector all
  require login.
- **Open signup** — anyone with the URL can sign up with email + password. Can
  be locked down later before going public.
- **Email confirmation disabled** — signup returns a session immediately and
  redirects into the app. No confirmation callback route or email templates.
- **One `/login` page** with a login / signup tab toggle on a shared form.
- **`/internal` is renamed by moving to the site root** — it is no longer
  "internal", it is the real (gated) app. The "INTERNAL" banner is dropped.
- **Post-login landing is `/dashboard`** — a new minimal page showing
  "Hi {email}" plus a sign-out button. Deep links are honored: a logged-out
  user sent to login from a protected URL is returned there after login
  (via `?redirectTo`), otherwise they land on `/dashboard`.
- **Auth wiring uses `@supabase/ssr`** — the standard Supabase + Next.js
  pattern. Cookie-based sessions are readable in middleware and server
  components, so the server-rendered reader is gated with no content flash.
- **Sign-out** lives only on `/dashboard` for now (not in the reader chrome).

## Architecture

### Supabase clients

Three clients, each with one purpose:

- `web/src/lib/supabase.ts` — existing service-role client, server-only, for
  privileged data ops. Unchanged.
- `web/src/lib/supabase/client.ts` — browser client (anon key), used by the
  login form for `signInWithPassword` / `signUp`.
- `web/src/lib/supabase/server.ts` — server client (anon key, cookie-bound),
  used by middleware and server components to read the session.

New env vars (added to `.env.local` and `.env.local.example`):

- `NEXT_PUBLIC_SUPABASE_URL`
- `NEXT_PUBLIC_SUPABASE_ANON_KEY`

The anon key is pasted from the Supabase dashboard. These are safe to expose to
the browser (anon key is public by design; row-level security protects data).

### Routing

Reader surfaces move from `/internal/*` to a route group `(app)` so they share a
layout without adding a URL segment:

| Today                              | After                       |
| ---------------------------------- | --------------------------- |
| `/internal/reader/[openiti_id]`    | `/reader/[openiti_id]`      |
| `/internal/library`                | `/library`                  |
| `/internal/inspector/[openiti_id]` | `/inspector/[openiti_id]`   |
| —                                  | `/dashboard` (new)          |

The 5 in-app `/internal` link references (ModeToggle, library page, reader page,
inspector page) are updated to the new paths.

`/login` lives outside the `(app)` group (it must be reachable while logged out).

### Gating (middleware)

`web/src/middleware.ts` keeps its existing rate-limiting for `/api/*` and adds
auth handling:

- On every matched request, refresh the Supabase session from cookies.
- For protected paths (`/reader`, `/library`, `/inspector`, `/dashboard`): if
  there is no session, redirect to `/login?redirectTo=<original-path>`.
- Public paths stay open: `/`, `/welcome`, `/r/*`, `/login`, `/api/*`.

### Auth flows

- **Login:** submit email + password → `signInWithPassword` → on success
  redirect to `redirectTo` or `/dashboard`; on error show an inline message.
- **Signup:** submit email + password → `signUp` → session returned immediately
  (confirmation disabled) → redirect to `/dashboard`.
- **Sign-out:** button on `/dashboard` → `signOut` → redirect to `/login`.

## Error handling

- Login/signup surface Supabase auth errors inline on the form (wrong password,
  email already registered, weak password). No silent failures.
- Missing `NEXT_PUBLIC_SUPABASE_*` env vars fail loudly at client construction,
  mirroring the existing `getSupabase()` behavior.
- Middleware: if session refresh throws, treat the user as logged out and send
  protected requests to `/login` rather than 500-ing.

## Testing

- Follow existing `web/` test conventions (vitest). Cover: middleware
  redirect logic (protected vs public paths, redirectTo construction) and the
  login form's login/signup/error branches where practical.
- Manual verification via the dev server: signup → land on dashboard; sign out →
  `/login`; hit `/reader/<id>` logged out → redirected to login then back to the
  reader after login; reader still renders from local files.

## Risks / notes

- Next.js 16.2.3 is a non-standard build (see `web/AGENTS.md`). Consult
  `node_modules/next/dist/docs/` before writing middleware / server-component
  auth code, since middleware and cookie APIs may differ from upstream.
- Moving routes out of `/internal` removes the `nocache` / `noindex` metadata
  that lived on the internal layout. Re-apply appropriate robots metadata on the
  gated routes if indexing is a concern.
