# Word-Tap Agents in the Reader — Design

Date: 2026-06-02
Branch: `group-b-agents`

## Goal

Let a reader tap any Arabic word in the reader view and get a popover with three
tabs: **I'rab** (grammar analysis), **Translation** (sentence translation plus
root-derived vocabulary), and **Ask AI** (a short scoped chat about the word).
The feature must feel native to the reader, not bolted on.

## Scope

In scope:

- Word-tap interaction in **reader mode only** (inspector keeps its existing
  copy-token-id click behavior).
- Three agent calls wired end to end: i'rab, translation, ask-ai.
- A tabbed, anchored popover with per-tab lazy loading, loading, and error states.
- Deriving the "sentence" context a word sits in, from the reader's flat tokens.

Explicitly out of scope (deferred):

- Caching (local or global). Each tap calls the model fresh.
- Auth and subscription gating. Group 0 (`group0-foundation`) owns auth; this
  feature stays open in the internal reader and adds a gating seam later.
- CAMeL sarf pre-computation, GPT-4o escalation, segmented multi-part analysis,
  and the richer `result_json` schema described in `docs/agents/irab.md`. Those
  remain the longer-term vision; this task uses the agents' current flat shapes.
- The iOS app and Supabase-edge-function delivery path.

## Key Decision: Next.js routes, not Supabase edge functions

The existing `supabase/functions/{irab,translate,ask-ai}` bodies only take input,
call the Anthropic API, and return JSON. For a web-only feature with no caching
and no shared iOS client yet, that logic belongs in **Next.js route handlers**
colocated with the reader.

Rationale:

- Uses the `ANTHROPIC_API_KEY` already available to the Next.js server; no second
  deploy target, no CORS, no public Supabase env.
- Typed end to end between the route and the client wrapper.
- The route is the backend, so there is no browser-to-edge proxy question.

Tradeoff: Next routes are web-only; the Supabase edge functions would be reusable
by a future iOS app. That reuse only pays off alongside the deferred shared global
cache, so the Supabase versions can be revived then. The route logic is ported
directly from the current edge function bodies, so nothing is lost.

The `supabase/functions/*` files are left in place as the record of the
longer-term vision; they are not deleted by this task.

## Architecture

Five focused units:

### 1. Sentence segmentation util

A pure module under `web/src/lib/reader/` that groups a block's flat token list
into sentences by splitting on Arabic terminal punctuation (full stop, question
mark, exclamation, colon, Arabic semicolon), falling back to the whole block when
a block has no such punctuation. Given a tapped token id it returns the sentence
text and the word's position within that sentence — the two context fields the
agents need. Pure and unit-tested.

### 2. Agent route handlers

`web/src/app/api/agents/{irab,translate,ask-ai}/route.ts`. Each validates the
request body, calls the Anthropic API with the prompt ported from the matching
edge function, and returns the parsed JSON. They own model choice, prompts, and
error mapping. No caching, no auth.

### 3. Agent client

A typed client module under `web/src/lib/agents/` exposing one function per agent
plus TypeScript types for the request and response of each. It owns fetch and
JSON handling so components never touch `fetch` directly.

### 4. Popover state provider

A reader-shell-level context (mirroring the existing `RecitationProvider`
pattern) that holds the active selection — the tapped token, its derived sentence
and position, and the anchor element — and exposes open/close. Reader-mode tokens
open it; everything else reads from it.

### 5. Popover UI

An anchored, tabbed floating panel (I'rab / Translation / Ask AI) positioned next
to the tapped word using **Floating UI** (`@floating-ui/react`), chosen as the
idiomatic, RTL-aware default for anchored popovers. Each tab fetches lazily on
first open so a tap does not fire three calls at once. Each tab has its own
loading and error state and a retry. The header shows the tapped word. Ask AI is
a short chat thread that keeps history client-side and sends the full thread each
turn. The popover closes on outside click and on Escape.

## Data flow

1. Reader renders tokens. In reader mode each token is tappable.
2. On tap, the hosting block resolves the tapped token to its sentence and
   position via the segmentation util, and opens the popover with that selection.
3. The popover renders three tabs. The active tab, on first view, calls the agent
   client, which calls the matching Next.js route, which calls Anthropic.
4. Results render in place. Switching tabs fetches the others lazily. Ask AI
   appends turns to a local thread and re-sends.

## Touch points in existing code

- `web/src/components/reader/TokenText.tsx` — add a reader-mode tap handler that
  opens the popover; inspector-mode behavior unchanged.
- `web/src/components/reader/Block.tsx` — precompute sentence segmentation for its
  tokens and supply the selection payload when a token is tapped.
- The reader page / theme shell — wrap content in the popover provider and render
  the popover, the same way recitation is wrapped today.

## Error handling

- Routes return a clear status and message on bad input or upstream failure; the
  client surfaces a friendly per-tab error with retry.
- Model output that fails to parse as expected JSON is reported as an error in the
  affected tab rather than crashing the popover.
- A tap with no resolvable sentence falls back to the whole block.

## Testing

- Unit tests for sentence segmentation (punctuation splits, no-punctuation
  fallback, position math) alongside the existing reader lib tests.
- Unit tests for the agent client with mocked fetch (success, non-OK, malformed
  body).
- Route handler tests in the style of the existing recitation token route test.
- Manual reader verification through the dev loop: tap words across prose, hadith,
  and poetry blocks; confirm each tab loads, errors recover, and the popover
  anchors correctly under RTL.

## Future seams (not built here)

- A single gating check point in the routes for Group 0 to fill in.
- Swapping the client's backend from Next routes to cached Supabase edge functions
  when the shared cache and iOS client land.
