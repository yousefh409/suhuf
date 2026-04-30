# Recitation ↔ Reader Integration — Design

## Overview

Connect the standalone recitation framework (`recitation/`, Python + FastAPI + fine-tuned XLS-R CTC + Whisper) to the Suhuf reader (`web/`, Next.js) so a user reading a chapter can tap **Recite**, read aloud, and get live word-level error highlighting on the same tokens the reader already renders.

The integration is built so:
- The recitation engine and its models stay **untouched** — only the WS protocol mouth widens.
- The reader stays modular: a self-contained `web/src/lib/recitation/` module is the entire integration surface; rendering changes are a context provider plus a CSS class on `TokenText`.
- **Token IDs are the contract.** The reader maps engine word indices to token IDs at the boundary; the engine never learns about IDs, blocks, pages, or chapters.
- **Production-deployable from day one.** Local dev is the v1 target, but every architectural decision considers what the production deployment looks like — auth, CORS, WSS, session caps, observability — and `NEXT_PUBLIC_RECITATION_WS_URL` plus a few server env vars are the only flip from dev to prod.

## Goals

1. A user reading any tashkeeled chapter in `/internal/reader/[openiti_id]/[ch_index]` can tap **Recite**, read aloud, and see real-time word-level highlighting (correct / wrong word / i3rab error / tashkeel error / skipped).
2. The user starts reading from whatever is on screen at the moment they tap **Recite**. No verse/phrase picker, no scroll-position coupling.
3. Re-reading the last 1–2 phrases is supported gracefully — the engine retreats the cursor and re-scores.
4. The recitation engine's model and scoring logic are unchanged. Only the WS protocol surface widens (inline passage, `append_phrases`, optional auth).
5. The integration ships local-only first; deploying the Python service to a GPU host and flipping the reader env var is the entire prod migration.

## Non-goals

- Public reader integration. v1 lives in `/internal/reader/...` only.
- Persistence of recitation results across sessions or reloads.
- Re-reading from more than 2 phrases back, or jumping forward by re-tapping mid-session.
- Beautiful UI. The reader gets a basic Recite toggle and CSS classes for status; deep visual polish is a future task.
- Bundling the model into the reader. The Python service stays separate.
- Mobile-specific audio handling beyond what AudioWorklet gives us out of the box.

## System Architecture

```
┌──────────────────────────────────────────────────────────┐
│  Reader (Next.js, web/)                                  │
│  /internal/reader/[openiti_id]/[ch_index]                │
├──────────────────────────────────────────────────────────┤
│  web/src/lib/recitation/                                 │
│   ├ passage.ts   (blocks → phrases + wordIndexToTokenId) │
│   ├ audio.ts     (AudioWorklet → 16 kHz PCM float32)     │
│   ├ client.ts    (WS client, reconnect, ping/pong)       │
│   ├ token.ts     (fetches /api/recitation/token in prod) │
│   ├ useRecitation.ts  (React hook, state machine)        │
│   └ types.ts                                             │
├──────────────────────────────────────────────────────────┤
│  web/src/components/reader/recite/                       │
│   ├ RecitationProvider.tsx  (context: status map)        │
│   └ ReciteToggle.tsx        (header button)              │
│  TokenText reads context.status.get(token.id)            │
├──────────────────────────────────────────────────────────┤
│  web/src/app/api/recitation/token/route.ts (prod only)   │
│  HMAC-signed JWT, ~5 min TTL, origin embedded            │
└──────────────────────────────────────────────────────────┘
                           │
                  WSS (prod) / WS (dev)
                           │
┌──────────────────────────────────────────────────────────┐
│  Recitation server (Python, recitation/)                 │
│  FastAPI: /ws/score                                      │
│  ├ accepts inline passage (new) OR passage_id (existing) │
│  ├ accepts append_phrases mid-session (new)              │
│  ├ optional auth_token validation (new, env-gated)       │
│  ├ origin allowlist (new, env-gated)                     │
│  └ session caps + structured logs (new)                  │
├──────────────────────────────────────────────────────────┤
│  engine.RecitationEngine + StreamingSession              │
│  ├ extend_phrases(more)         (new)                    │
│  ├ candidate window: cursor-2 .. cursor+5  (was -1..+5)  │
│  ├ retreat-with-unlock for re-reading      (new)         │
│  └ everything else unchanged                             │
├──────────────────────────────────────────────────────────┤
│  Whisper (position) + XLS-R CTC (scoring) — unchanged    │
└──────────────────────────────────────────────────────────┘
```

## The contract: WebSocket protocol

The recitation server exposes one WebSocket endpoint, `/ws/score`. The protocol is a small superset of what exists today.

### Init message (client → server, first message)

```jsonc
{
  "passage": {
    "id": "<arbitrary-string>",
    "phrases": ["...", "...", "..."]
  },
  "lookbehind_count": 2,        // optional, default 0; index in `phrases` where the
                                //  user actually starts (phrases at indices below
                                //  it are kept only so the cursor can retreat)
  "auth_token": "...",          // required iff RECITATION_AUTH_SECRET is set on server
  "debug": false                // refused unless RECITATION_ALLOW_DEBUG=1 on server
}
```

The existing `passage_id` form continues to work (used by the recitation team's static test UI). The reader uses the `passage` form exclusively.

### Audio (client → server)

Binary WebSocket frames, raw PCM float32 little-endian @ 16 kHz mono. Same as today.

### Append phrases (client → server, mid-session)

```jsonc
{ "type": "append_phrases", "phrases": ["...", "..."] }
```

The reader sends this when the engine's cursor crosses ~70 % of the current phrase list. The server appends to `StreamingSession.phrases` and updates the internal word-index map. Cursor and audio state are preserved.

### Score events (server → client)

Unchanged from today:

```jsonc
{
  "words": [
    { "idx": 0, "word": "...", "status": "correct" | "error",
      "error_type": "wrong" | "skipped" | "i3rab" | "tashkeel" | null,
      "error_detail": "...", "expected_word": "...", "greedy": "...",
      "debug": { ... } },
    ...
  ],
  "matched_phrase_idx": 3
}
```

`idx` is the global word index across the engine's phrases (same indexing as today; the reader translates via `wordIndexToTokenId[]`).

### Done / final (client → server, then server → client)

Client sends text frame `"done"`. Server runs final scoring with batch thresholds, replies with `{ "words": [...], "matched_phrase_idx": N, "final": true }`, then closes.

### Error / control events (server → client)

```jsonc
{ "type": "error", "code": "auth_failed" | "origin_denied" | "session_too_long",
                   "message": "..." }
{ "type": "ping" }    // every 30s; client replies with text frame "pong"
```

## Reader side: `web/src/lib/recitation/`

### `passage.ts` — pure function

```ts
buildPassage(input: {
  chapterBlocks: Block[],         // all blocks in the current chapter (already loaded)
  anchorBlockKey: string,         // topmost-visible block at Recite-tap time
  lookbehindCount?: number,       // default 2 — phrases before the anchor
  lookaheadPhraseCount?: number,  // default 15 — phrases after the anchor
}) → {
  phrases: string[],              // [lookbehind … anchor … lookahead]
  wordIndexToTokenId: string[],   // flat array, indexed by engine word idx
  startCursor: number,            // === lookbehindCount: index of anchor in phrases
} | null
```

- One block = one phrase by default.
- If a block exceeds **40 words**, split at Arabic pause markers (`. ، ؛ : !`). If a chunk is still over 40, split at word boundaries.
- Headings, page boundaries, and empty blocks are skipped (not phrases).
- Poetry: each hemistich = one phrase.
- For each phrase, the reader tokenizes the same way the engine will (`phrase.split()`). The resulting flat array of token IDs is `wordIndexToTokenId`.
- The **lookbehind** comes from the chapter's blocks immediately before the anchor (so the engine can retreat the cursor when the user re-reads). The **lookahead** comes from blocks immediately after; when the user reads past most of it, the hook calls `client.appendPhrases(...)` with more from the chapter.
- `startCursor` is exactly `lookbehindCount` — the index in `phrases` corresponding to the anchor block. The reader passes this as `lookbehind_count` in the WS init message so the engine starts the cursor at the right place.
- Returns `null` if no phrases produced (empty chapter or fully un-tashkeeled). The Recite button is disabled in that case.

### `audio.ts` — AudioWorklet capture

- Mic capture via `AudioWorklet` (with `ScriptProcessorNode` fallback for older browsers).
- Resamples to 16 kHz mono float32 (browser native sample rate is usually 44.1 / 48 kHz).
- Yields `Float32Array` chunks ready to ship as binary WS frames.
- Pattern lifted from `recitation/static/index.html` into a clean module — no new dependencies.

### `client.ts` — WS wrapper

- Knows the protocol above. No React, no audio.
- Constructor takes a `tokenProvider?: () => Promise<string>` (called before connect when set; in dev it's unset).
- Public API: `connect(passage, lookbehindCount)`, `sendAudio(buf)`, `appendPhrases(phrases)`, `done()`, `close()`. Emits events: `score`, `final`, `error`, `connectionState`.
- Reconnect with exponential backoff (1s / 2s / 4s / 8s, cap 30s) on transient errors. No reconnect on auth/origin failures.
- Heartbeat: responds to server pings; aborts if no message for 60s.

### `token.ts` — auth token fetcher (prod only)

- Hits `/api/recitation/token` (Next.js API route), returns the JWT.
- In dev (no `RECITATION_AUTH_SECRET` set on server) the reader skips this call entirely — env flag.

### `useRecitation.ts` — React hook

```ts
useRecitation({ blocks: Block[] }) → {
  start: () => void
  stop: () => void
  status: Map<string, RecitationStatus>   // tokenId → status
  cursor: string | null                    // tokenId of current word
  connectionState: 'idle' | 'connecting' | 'connected' | 'reconnecting' | 'error'
  error?: string
}
```

- Internally: identifies the **anchor block** (topmost-visible block at start time, via `IntersectionObserver` over `[data-block-key]` elements within the `ChapterScroll`), builds the passage via `passage.ts`, opens `client.ts`, captures audio via `audio.ts`, translates engine word indices to token IDs through `wordIndexToTokenId[]`, exposes a stable `Map<string, RecitationStatus>`.
- `RecitationStatus = 'correct' | 'wrong_word' | 'i3rab' | 'tashkeel' | 'skipped' | 'current'`.
- Watches `matched_phrase_idx`; when the engine crosses the 70 % watermark of the current window, automatically calls `client.appendPhrases(...)` with the next batch from the chapter's phrase list.

### `types.ts`

TypeScript mirrors of all WS messages and the public types of the hook.

## Reader side: rendering changes

### `RecitationProvider`

A React context wrapping `ChapterScroll`. Holds the `Map<tokenId, status>` and the cursor token ID. Updates re-render via context (or via Zustand if perf demands it later).

### `TokenText`

Reads `useContext(RecitationContext)`. If a status exists for `token.id`, applies a CSS class:

```
.tok--correct     { color: green }      (subtle)
.tok--wrong_word  { text-decoration: line-through; color: red }
.tok--i3rab       { border-bottom: 2px solid blue }
.tok--tashkeel    { border-bottom: 2px solid orange }
.tok--skipped     { color: #aaa; border-bottom: 2px dashed gray }
.tok--current     { background: rgba(yellow, 0.2) }
```

(Final colors per the existing recitation prototype's palette; see `static/index.html`.)

No prop drilling. The existing `ChapterScroll` and `Block` components are untouched.

### `ReciteToggle`

A button in the chapter page header (next to `TashkeelToggle` / `ModeToggle`). Disabled with tooltip when:
- `buildPassage` returns `null` (no recitable text in this chapter), or
- `book.has_tashkeel === false`.

When enabled: tap → starts session, button becomes a pulsing **Stop**. Tap again → stops.

## Engine side: `recitation/`

### `engine.py` — `StreamingSession` additions

1. **`extend_phrases(new_phrases: list[str]) -> None`**
   Append to `self.phrases`, regenerate `self._phrase_words`, extend `self._best_spoken` watermarks. Audio ring buffer and cursor preserved.

2. **Candidate window expanded backward**
   `_get_candidates()` returns indices `[cursor-2, cursor-1, cursor, cursor+1, ..., cursor+5]` instead of `[cursor-1, ..., cursor+5]`. Already-bounded; existing match logic filters by score threshold.

3. **Cursor retreat for re-reading**
   In `score_cycle`, when `best_idx ∈ {cursor-1, cursor-2}` *and* the score margin over the current cursor is large (configurable threshold, e.g. `score(best) - score(cursor) > 0.20`):
   - Retreat `cursor_phrase` to `best_idx`.
   - Unlock all words in the retreated-to phrase (clear their lock counters in `_scored_words`) so re-reading produces fresh verdicts.
   - Forward `_best_spoken` watermarks for phrases ahead of `best_idx` are preserved.
4. **Per-cycle log entry** emitting structured JSON to stdout when `LOG_STREAMING=1`: `{session_id, audio_bytes, cursor_phrase, retreat_count, append_count, score_count}`.

The candidate-window change is a one-line edit. Retreat is ~10 lines plus the unlock logic. Everything else (CTC scoring, classification, Whisper position, score locking, etc.) is unchanged.

### `server.py` — `/ws/score` additions

1. **Parse init**: accept `passage` (inline) form alongside `passage_id`. Build the same `phrases` list.
2. **Auth**: if `RECITATION_AUTH_SECRET` is set, validate `init.auth_token` (HMAC SHA-256 over `{origin, exp}`). Reject with `code: "auth_failed"` on failure.
3. **Origin allowlist**: if `RECITATION_ALLOWED_ORIGINS` is set, check the WS handshake `Origin` header. Reject with `code: "origin_denied"`.
4. **Debug gate**: refuse `init.debug=true` unless `RECITATION_ALLOW_DEBUG=1`.
5. **Session caps**: enforce `RECITATION_MAX_SESSION_SEC` (default 600). On expiry: send `error: session_too_long`, then close.
6. **Pings**: every 30 s server sends `{type: "ping"}`. If no client message for 60 s, close.
7. **Append handler**: on `{type: "append_phrases", phrases: [...]}`, call `session.extend_phrases(phrases)` and ack with the next score cycle.
8. **Structured logging**: emit JSON log lines per session (start, end, error, byte counts, durations).
9. **CORS**: Already implicit for WS via origin check; add explicit middleware for the existing HTTP endpoints (`/api/passages` etc.) so the same allowlist applies if the reader ever calls them.

### Production server config (env)

| Var | Default | Purpose |
|---|---|---|
| `RECITATION_AUTH_SECRET` | unset | If set, require valid HMAC token |
| `RECITATION_ALLOWED_ORIGINS` | unset | Comma-separated origins; if set, enforce |
| `RECITATION_ALLOW_DEBUG` | `0` | Gate the audio-saving debug flag |
| `RECITATION_MAX_SESSION_SEC` | `600` | Per-session hard cap |
| `LOG_STREAMING` | `0` | Emit per-cycle JSON log lines |

### Dockerfile

A `recitation/Dockerfile` that:
- Bases on `nvidia/cuda` image when GPU is desired (or slim Python when CPU).
- Installs `requirements.txt`.
- Copies the model directory `models/ssl_xls_r_v5/` into the image (or downloads at boot from a configured URL).
- Runs `uvicorn server:app --host 0.0.0.0 --port 8000`.

Production deployment target (out of scope to operate in v1): Modal, Railway-with-GPU, or a managed container host. The Dockerfile is the contract; ops happen later.

## Reader-side production config

| Var | Default | Purpose |
|---|---|---|
| `NEXT_PUBLIC_RECITATION_WS_URL` | `ws://localhost:8000/ws/score` | WS endpoint |
| `RECITATION_AUTH_SECRET` | unset (server-side only) | Same secret as Python server, used by token-mint route |
| `RECITATION_TOKEN_TTL_SEC` | `300` | JWT TTL |

The token-mint API route (`web/src/app/api/recitation/token/route.ts`) signs a JWT containing `{origin, exp}` with `RECITATION_AUTH_SECRET`. In dev, the secret is unset; the reader skips minting and the server skips validating.

## Failure modes

| Mode | Detection | Behavior |
|---|---|---|
| Mic permission denied | Browser API rejects | Hook surfaces `error: 'mic_denied'`; toggle returns to idle |
| WS connect fails | `client.ts` | Exponential backoff; surface `connectionState: 'reconnecting'` |
| Auth/origin rejected | Server `error` event | Stop reconnecting; surface terminal error |
| Session timeout | Server `error: session_too_long` | Surface to user; user can re-tap Recite |
| User scrolls during session | n/a | Engine state unchanged; cursor follows audio, not eyes |
| Cursor approaches end of window | Reader watermark | Auto-`appendPhrases` |
| Cursor reaches end of chapter | No more phrases to append | Engine reports `final=true` shape on next cycle; reader stops auto-append; user can stop |
| Network drop mid-session | Heartbeat timeout | Reconnect attempt; lost audio is lost (no replay in v1) |
| Re-reading detected wrong (false retreat) | Margin guard | Retreat is gated behind a margin threshold to prevent false positives |
| Un-tashkeeled chapter | `buildPassage` returns null | Recite button disabled |

## Testing

- **`passage.ts`**: pure-function unit tests covering block-to-phrase conversion, hemistich handling, long-block splitting, headings skipped, empty inputs, un-tashkeeled inputs.
- **`client.ts`**: tests against a fake WS (mock).
- **`useRecitation.ts`**: React Testing Library + a mocked client.
- **Engine `extend_phrases`**: Python unit test that appends mid-session and verifies cursor + watermark integrity.
- **Engine retreat**: Python test that synthesizes a re-read scenario and verifies cursor retreats + words unlock + forward watermarks preserved.
- **Server protocol**: integration test that connects to `/ws/score` with the inline-passage form, sends a saved audio file, asserts shape of word events.
- **Local dev smoke test**: a manual loop documented in `docs/reader/dev-loop.md` (or a new `docs/recitation/dev-loop.md`) — start Python server, start reader, open a tashkeeled chapter, recite, verify highlighting.

## Migration / rollout

1. Land engine-side WS additions (`extend_phrases`, retreat, candidate window, env-gated auth/CORS, session caps, logs). Existing `passage_id` flow continues to work for the team's static UI.
2. Land `web/src/lib/recitation/` module + reader UI (toggle, provider, CSS classes).
3. Wire to local Python server. Test on a tashkeeled chapter.
4. Iterate on the experience using existing test recordings + ad-hoc sessions.
5. Production: build the Dockerfile, deploy the Python server to a GPU host, set the reader's `NEXT_PUBLIC_RECITATION_WS_URL` to `wss://...`, set the shared `RECITATION_AUTH_SECRET` on both sides, ship.

## Open questions deferred to implementation

- Exact retreat margin threshold for re-reading (calibrate against test recordings).
- Whether the reader auto-stops the session at end-of-chapter or waits for the user.
- Append batch size: send 10 phrases at a time? 20? Tune empirically.
- How quickly the reader re-renders status updates for very long chapters (perf check; may need memoization on `TokenText`).
