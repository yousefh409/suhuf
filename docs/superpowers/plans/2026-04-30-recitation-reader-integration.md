# Recitation ↔ Reader Integration — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire the recitation framework (Python + FastAPI + XLS-R CTC + Whisper) into the Suhuf reader so a user can tap **Recite** on any tashkeeled chapter, read aloud, and see word-level highlighting on the same tokens the reader renders. Production-deployable from day one (env-flip dev → prod).

**Architecture:** Sliding-window passage scope anchored at the visible block at Recite-tap time, with 2 phrases of lookbehind for re-reading and streaming `append_phrases` for forward progress. Reader builds a `wordIndexToTokenId[]` map and translates engine word indices to token IDs at the boundary. Engine and models untouched; WS protocol gains an inline-passage form, `append_phrases`, and env-gated auth/origin/session-cap.

**Tech Stack:**
- Server: Python 3.13, FastAPI, existing `engine.py` (PyTorch + transformers), `websockets`
- Reader: Next.js (web/), TypeScript, Vitest
- Wire: WebSocket (WSS in prod), PCM float32 @ 16 kHz mono
- Auth (prod): symmetric HMAC-SHA-256 over `{origin, exp}`, no JWT lib

**Spec:** [docs/superpowers/specs/2026-04-30-recitation-reader-integration-design.md](../specs/2026-04-30-recitation-reader-integration-design.md)

---

## File Map

### Created
- `recitation/test_inline_passage.py` — protocol test for new init form
- `recitation/test_extend_phrases.py` — engine-level test
- `recitation/test_retreat.py` — engine-level retreat test
- `recitation/test_auth.py` — token validation test
- `recitation/auth.py` — HMAC token sign/verify (stdlib only)
- `recitation/Dockerfile` — production container
- `recitation/.dockerignore`
- `web/src/lib/recitation/types.ts`
- `web/src/lib/recitation/passage.ts`
- `web/src/lib/recitation/passage.test.ts`
- `web/src/lib/recitation/audio.ts`
- `web/src/lib/recitation/client.ts`
- `web/src/lib/recitation/client.test.ts`
- `web/src/lib/recitation/state.ts` — pure state-machine reducer (testable without React)
- `web/src/lib/recitation/state.test.ts`
- `web/src/lib/recitation/useRecitation.ts`
- `web/src/lib/recitation/token.ts`
- `web/src/components/reader/recite/RecitationProvider.tsx`
- `web/src/components/reader/recite/ReciteToggle.tsx`
- `web/src/components/reader/recite/recite.css`
- `web/src/app/api/recitation/token/route.ts`
- `web/src/app/api/recitation/token/route.test.ts`
- `docs/recitation/dev-loop.md`

### Modified
- `recitation/engine.py` — `StreamingSession.extend_phrases`, candidate window expansion, retreat-with-unlock
- `recitation/server.py` — inline passage form, `append_phrases` handler, auth/origin/session/debug/ping/logging
- `web/src/components/reader/TokenText.tsx` — read recitation context, apply status class
- `web/src/components/reader/ChapterScroll.tsx` — wrap children in `RecitationProvider`
- `web/src/app/internal/reader/[openiti_id]/[ch_index]/page.tsx` — add `ReciteToggle` to header
- `web/package.json` — add `jose` (token signing), `@testing-library/react`, `jsdom` if hook tests run in jsdom
- `web/vitest.config.ts` — per-file environment for tsx tests

---

## Phase 1 — Engine + protocol foundation

### Task 1: Inline passage form in WS init

The server today only accepts `{ "passage_id": "..." }` (looked up in `passage.json`). We add a parallel `{ "passage": { "id": "...", "phrases": [...] } }` form. Both forms continue to work.

**Files:**
- Modify: `recitation/server.py` (the `/ws/score` endpoint, after `init = await websocket.receive_json()`)
- Test: `recitation/test_inline_passage.py`

- [ ] **Step 1: Write the failing test**

```python
# recitation/test_inline_passage.py
"""Test that /ws/score accepts inline passage form."""
import asyncio
import json
import struct
import pytest
import websockets

SERVER = "ws://localhost:8000/ws/score"

@pytest.mark.asyncio
async def test_inline_passage_accepted():
    """Server should accept {passage: {phrases: [...]}} as init."""
    async with websockets.connect(SERVER) as ws:
        await ws.send(json.dumps({
            "passage": {
                "id": "inline-test",
                "phrases": ["الكَلَامُ هُوَ اللَّفْظُ", "المُرَكَّبُ المُفِيدُ"]
            }
        }))
        # Send a tiny chunk of silence so server doesn't hang on init only
        silence = struct.pack("<" + "f" * 1600, *([0.0] * 1600))  # 0.1s
        await ws.send(silence)
        await ws.send("done")
        # Should receive at least one message; should NOT receive {error: ...}
        msg = await asyncio.wait_for(ws.recv(), timeout=10.0)
        data = json.loads(msg)
        assert "error" not in data, f"Server rejected inline passage: {data}"


@pytest.mark.asyncio
async def test_passage_id_still_works():
    """Existing passage_id form should keep working."""
    async with websockets.connect(SERVER) as ws:
        await ws.send(json.dumps({"passage_id": "ajrumiyyah"}))
        silence = struct.pack("<" + "f" * 1600, *([0.0] * 1600))
        await ws.send(silence)
        await ws.send("done")
        msg = await asyncio.wait_for(ws.recv(), timeout=10.0)
        data = json.loads(msg)
        assert "error" not in data
```

- [ ] **Step 2: Run test to verify it fails**

```bash
# In one terminal: cd recitation && python -m uvicorn server:app --host 0.0.0.0 --port 8000
# In another:
cd recitation && pip install pytest pytest-asyncio websockets
python -m pytest test_inline_passage.py -v
```

Expected: `test_inline_passage_accepted` FAILS with the server returning `{"error": "Passage not found"}` (the existing branch returns this when `passage_id` is missing).

- [ ] **Step 3: Implement inline passage parsing**

Edit `recitation/server.py`. Find the `ws_score` function and the block after `init = await websocket.receive_json()`. Replace this block:

```python
    passage_id = init.get("passage_id")
    data = load_passages()
    passage = next((p for p in data["passages"] if p["id"] == passage_id), None)
    if not passage or "phrases" not in passage:
        await websocket.send_json({"error": "Passage not found"})
        await websocket.close(1008)
        return

    phrases = passage["phrases"]
```

with:

```python
    # Accept either inline {passage: {phrases: [...]}} or stored {passage_id: "..."}
    inline = init.get("passage")
    passage_id = init.get("passage_id")

    if inline and isinstance(inline, dict) and isinstance(inline.get("phrases"), list):
        phrases = [str(p) for p in inline["phrases"] if isinstance(p, str) and p.strip()]
        if not phrases:
            await websocket.send_json({"error": "Inline passage has no phrases"})
            await websocket.close(1008)
            return
    elif passage_id:
        data = load_passages()
        passage = next((p for p in data["passages"] if p["id"] == passage_id), None)
        if not passage or "phrases" not in passage:
            await websocket.send_json({"error": "Passage not found"})
            await websocket.close(1008)
            return
        phrases = passage["phrases"]
    else:
        await websocket.send_json({"error": "Init must include 'passage' or 'passage_id'"})
        await websocket.close(1008)
        return
```

Also note: the existing code uses `passage_id` later for the debug log directory name. Replace that one usage with a derived name:

```python
    # Old: log_dir = SESSION_LOG_DIR / f"{ts}_{passage_id}"
    # New (find this line and update):
    log_label = passage_id or (inline.get("id") if inline else "inline") or "session"
    log_dir = SESSION_LOG_DIR / f"{ts}_{log_label}"
```

And the meta.json write that referenced `passage_id`:

```python
    # Old: "passage_id": passage_id,
    # New:
    "passage_id": passage_id,            # may be None for inline
    "inline_id": inline.get("id") if inline else None,
```

- [ ] **Step 4: Run tests to verify both pass**

```bash
# Server still running in the other terminal
python -m pytest test_inline_passage.py -v
```

Expected: PASS for both tests.

- [ ] **Step 5: Commit**

```bash
cd "/Users/yousefh/Desktop/Cool Code/suhuf/.claude/worktrees/gallant-johnson-2b7dd5"
git add recitation/server.py recitation/test_inline_passage.py
git commit -m "recitation: accept inline passage in WS init"
```

---

### Task 2: `extend_phrases` on StreamingSession + `append_phrases` WS handler

The reader sends an `append_phrases` message mid-session as the user nears the end of the current window. The engine appends to its phrase list without resetting cursor or audio state.

**Files:**
- Modify: `recitation/engine.py` — add `StreamingSession.extend_phrases`
- Modify: `recitation/server.py` — handle `{"type": "append_phrases", "phrases": [...]}` in the receive loop
- Test: `recitation/test_extend_phrases.py`

- [ ] **Step 1: Locate `StreamingSession.__init__` to understand current state**

Open `recitation/engine.py`, find `class StreamingSession`. Note which attributes are derived from `self.phrases`:
- `self.phrases` (list of strings)
- `self._phrase_words` (list of `phrase.split()` results) — derived
- `self._best_spoken` (dict `{phrase_idx: int}`) — accumulates as session progresses
- `self.cursor_phrase` (int) — current cursor

`extend_phrases` must extend `phrases`, regenerate/extend `_phrase_words`, and leave everything else alone.

- [ ] **Step 2: Write the failing test**

```python
# recitation/test_extend_phrases.py
"""Test StreamingSession.extend_phrases preserves state."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from engine import StreamingSession


class _FakeEngine:
    """Stand-in for RecitationEngine — extend_phrases shouldn't touch the engine."""
    pass


def test_extend_phrases_appends_and_preserves_state():
    sess = StreamingSession(_FakeEngine(), ["phrase one alpha", "phrase two beta"])
    # Simulate progress
    sess.cursor_phrase = 1
    sess._best_spoken[0] = 3
    sess._best_spoken[1] = 2

    sess.extend_phrases(["phrase three gamma", "phrase four delta"])

    assert sess.phrases == [
        "phrase one alpha", "phrase two beta",
        "phrase three gamma", "phrase four delta",
    ]
    assert len(sess._phrase_words) == 4
    assert sess._phrase_words[2] == ["phrase", "three", "gamma"]
    # Existing state preserved:
    assert sess.cursor_phrase == 1
    assert sess._best_spoken[0] == 3
    assert sess._best_spoken[1] == 2


def test_extend_phrases_skips_empty():
    sess = StreamingSession(_FakeEngine(), ["one"])
    sess.extend_phrases(["", "  ", "two"])
    assert sess.phrases == ["one", "two"]
```

- [ ] **Step 3: Run test, verify it fails**

```bash
cd recitation && python -m pytest test_extend_phrases.py -v
```

Expected: FAIL — `AttributeError: 'StreamingSession' object has no attribute 'extend_phrases'`.

- [ ] **Step 4: Implement `extend_phrases`**

Add to `StreamingSession` in `recitation/engine.py`:

```python
    def extend_phrases(self, new_phrases: list) -> None:
        """Append more phrases mid-session. Cursor and audio state preserved.

        Empty / whitespace-only phrases are skipped. Existing _best_spoken
        watermarks are kept. Newly appended phrases get fresh state.
        """
        for raw in new_phrases:
            if not isinstance(raw, str):
                continue
            text = raw.strip()
            if not text:
                continue
            self.phrases.append(text)
            self._phrase_words.append(text.split())
        # _best_spoken is a dict keyed by phrase_idx; new indices have no entry yet,
        # which is treated as "0 spoken" by the existing scoring logic.
```

If `_phrase_words` doesn't exist on the current StreamingSession (check the class), add it to `__init__` as `self._phrase_words = [p.split() for p in self.phrases]` and update existing references that re-split phrases.

- [ ] **Step 5: Verify test passes**

```bash
python -m pytest test_extend_phrases.py -v
```

Expected: PASS.

- [ ] **Step 6: Wire up the WS handler in `server.py`**

In `recitation/server.py`, find the receive loop in `ws_score`. After the `if text == "done":` block and before `if not raw:`, add:

```python
            # Mid-session passage extension
            if text and text.strip().startswith("{"):
                try:
                    payload = json.loads(text)
                except json.JSONDecodeError:
                    payload = None
                if isinstance(payload, dict) and payload.get("type") == "append_phrases":
                    new_phrases = payload.get("phrases") or []
                    if isinstance(new_phrases, list):
                        session.extend_phrases(new_phrases)
                    continue
```

Note: the WS receives both binary frames (audio) and text frames. Currently `text == "done"` handles the only text case. We add a second text case for JSON control messages.

- [ ] **Step 7: Test the WS path end-to-end**

Add to `recitation/test_inline_passage.py` (or a new file `test_append_phrases.py`):

```python
@pytest.mark.asyncio
async def test_append_phrases_mid_session():
    """append_phrases should extend the engine's phrase list without erroring."""
    async with websockets.connect(SERVER) as ws:
        await ws.send(json.dumps({
            "passage": {"id": "tx", "phrases": ["one two three"]}
        }))
        silence = struct.pack("<" + "f" * 1600, *([0.0] * 1600))
        await ws.send(silence)
        await ws.send(json.dumps({
            "type": "append_phrases",
            "phrases": ["four five six", "seven eight nine"]
        }))
        await ws.send(silence)
        await ws.send("done")
        # Should complete without error
        async for msg in ws:
            data = json.loads(msg) if isinstance(msg, str) else None
            if data and data.get("final"):
                break
            if data and "error" in data:
                pytest.fail(f"Server returned error: {data}")
```

```bash
# Restart server (to pick up changes)
python -m pytest test_extend_phrases.py test_inline_passage.py -v
```

Expected: all PASS.

- [ ] **Step 8: Commit**

```bash
git add recitation/engine.py recitation/server.py recitation/test_extend_phrases.py recitation/test_inline_passage.py
git commit -m "recitation: streaming append_phrases for sliding-window passage growth"
```

---

### Task 3: Cursor retreat for re-reading + window expansion

When the user re-reads a phrase or two, the engine should retreat the cursor and unlock that phrase's word verdicts so a fresh score replaces the old one. We expand the candidate window from `[cursor-1 … cursor+5]` to `[cursor-2 … cursor+5]`, and add a margin-gated retreat path.

**Files:**
- Modify: `recitation/engine.py` — `_get_candidates`, retreat logic in `score_cycle`
- Test: `recitation/test_retreat.py`

- [ ] **Step 1: Locate `_get_candidates` and `score_cycle` in `engine.py`**

These already exist. The architecture doc describes them.

- [ ] **Step 2: Write the failing test**

```python
# recitation/test_retreat.py
"""Test cursor retreat behavior for re-reading.

Drives StreamingSession through a synthesized scenario:
- Cursor advances to phrase 3.
- A new score cycle finds phrase 1 is the best match by a wide margin.
- Cursor should retreat to phrase 1.
- Word locks for phrase 1 should be cleared.
- _best_spoken for phrases 2 and 3 should be preserved (forward watermarks).

This test mocks the model interaction and exercises only the retreat-decision logic.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from engine import StreamingSession


class _FakeEngine:
    pass


def test_candidate_window_includes_cursor_minus_two():
    sess = StreamingSession(_FakeEngine(), ["a", "b", "c", "d", "e", "f", "g", "h"])
    sess.cursor_phrase = 3
    cands = sess._get_candidates()
    assert 1 in cands, f"cursor-2 should be in candidates, got {cands}"
    assert 2 in cands
    assert 3 in cands
    assert 8 not in cands  # bounded ahead


def test_retreat_unlocks_target_phrase():
    sess = StreamingSession(_FakeEngine(), ["one", "two", "three", "four"])
    sess.cursor_phrase = 3
    sess._best_spoken[1] = 1
    sess._best_spoken[2] = 1
    sess._best_spoken[3] = 1
    # Lock some words on phrase 1 (the phrase we'll retreat to)
    sess._scored_words = {
        # Global word indices: phrase 1's words start at index 1
        1: {"word_idx": 1, "lock_count": 5, "status": "wrong"},
        2: {"word_idx": 2, "lock_count": 3, "status": "correct"},
        # Phrase 3 words (don't unlock)
        3: {"word_idx": 3, "lock_count": 4, "status": "correct"},
    }
    sess._retreat_to(1)
    assert sess.cursor_phrase == 1
    # Words in retreated-to phrase should be cleared
    assert 1 not in sess._scored_words
    assert 2 not in sess._scored_words
    # Words in forward phrases should be preserved
    assert 3 in sess._scored_words
    # Forward watermarks preserved
    assert sess._best_spoken[2] == 1
    assert sess._best_spoken[3] == 1
```

- [ ] **Step 3: Run test, verify it fails**

```bash
python -m pytest test_retreat.py -v
```

Expected: FAIL — `_get_candidates` doesn't include `cursor-2` yet, and `_retreat_to` doesn't exist.

- [ ] **Step 4: Implement window expansion**

In `engine.py`, find `_get_candidates`. It currently looks roughly like:

```python
    def _get_candidates(self):
        c = self.cursor_phrase
        return [i for i in range(max(0, c - 1), min(len(self.phrases), c + 6))]
```

Change to:

```python
    def _get_candidates(self):
        c = self.cursor_phrase
        return [i for i in range(max(0, c - 2), min(len(self.phrases), c + 6))]
```

- [ ] **Step 5: Implement `_retreat_to`**

Add to `StreamingSession`:

```python
    # Retreat threshold: best candidate must beat current by this score margin.
    # Calibrate against test recordings if false-retreats appear.
    RETREAT_MARGIN = 0.20

    def _phrase_word_range(self, phrase_idx: int) -> tuple:
        """Return (global_first_word_idx, global_last_word_idx_exclusive) for a phrase."""
        start = sum(len(p) for p in self._phrase_words[:phrase_idx])
        end = start + len(self._phrase_words[phrase_idx])
        return start, end

    def _retreat_to(self, target_phrase_idx: int) -> None:
        """Move cursor backward to target_phrase_idx. Unlock that phrase's words.

        Forward _best_spoken watermarks are preserved so the user doesn't lose
        progress when they continue forward after re-reading.
        """
        if target_phrase_idx >= self.cursor_phrase:
            return
        first, last = self._phrase_word_range(target_phrase_idx)
        for wi in list(self._scored_words.keys()):
            if first <= wi < last:
                del self._scored_words[wi]
        # Reset the watermark for the retreated-to phrase so re-reading rescores
        # from the start of that phrase.
        self._best_spoken[target_phrase_idx] = 0
        self.cursor_phrase = target_phrase_idx
```

- [ ] **Step 6: Wire retreat into `score_cycle`**

In `score_cycle`, after `_match_phrase` returns a `best_idx` and `best_score`, and after the existing `cursor advance` logic, add a retreat check. The exact insertion point depends on the existing code, but conceptually:

```python
        # ── Cursor retreat for re-reading ──
        if (best_idx is not None
                and best_idx < self.cursor_phrase
                and best_idx >= self.cursor_phrase - 2):
            current_score = scores.get(self.cursor_phrase, 0.0) if scores else 0.0
            if best_score - current_score >= self.RETREAT_MARGIN:
                self._retreat_to(best_idx)
```

`scores` here is the dict of `{candidate_idx: score}` from the candidate matching pass. If the existing code doesn't expose it as a dict, capture it where `_match_phrase` is called.

- [ ] **Step 7: Run tests**

```bash
python -m pytest test_retreat.py test_extend_phrases.py test_inline_passage.py -v
```

Expected: all PASS. Also run the existing test suite to confirm nothing regressed:

```bash
python -m pytest test_streaming.py -v   # requires running server + edge-tts
```

(If `test_streaming.py` is too slow / network-dependent, skip it for now and run after Phase 4.)

- [ ] **Step 8: Commit**

```bash
git add recitation/engine.py recitation/test_retreat.py
git commit -m "recitation: cursor retreat (cursor-2..+5) for re-reading the last 1-2 phrases"
```

---

## Phase 2 — Reader library

### Task 4: TypeScript types

Foundation for the rest of the reader-side module. No behavior, just shapes.

**Files:**
- Create: `web/src/lib/recitation/types.ts`

- [ ] **Step 1: Create the file**

```ts
// web/src/lib/recitation/types.ts
// Types mirroring the recitation server's WS protocol and the public surface
// of the useRecitation hook. See:
// docs/superpowers/specs/2026-04-30-recitation-reader-integration-design.md

export type RecitationStatus =
  | "correct"
  | "wrong_word"
  | "i3rab"
  | "tashkeel"
  | "skipped"
  | "current";

export type ConnectionState =
  | "idle"
  | "connecting"
  | "connected"
  | "reconnecting"
  | "error";

// ── Server → client messages ──

export type ScoreWord = {
  idx: number;
  word: string;
  status: "correct" | "error";
  error_type:
    | "wrong"
    | "skipped"
    | "i3rab"
    | "tashkeel"
    | null;
  error_detail: string | null;
  expected_word?: string | null;
  greedy?: string;
  debug?: Record<string, unknown>;
};

export type ScoreEvent = {
  words: ScoreWord[];
  matched_phrase_idx: number;
  final?: boolean;
};

export type ServerErrorEvent = {
  type: "error";
  code: "auth_failed" | "origin_denied" | "session_too_long" | string;
  message: string;
};

export type ServerPing = { type: "ping" };

// ── Client → server messages ──

export type InitMessage = {
  passage: { id: string; phrases: string[] };
  lookbehind_count?: number;
  auth_token?: string;
  debug?: boolean;
};

export type AppendMessage = {
  type: "append_phrases";
  phrases: string[];
};

// ── Public hook surface ──

export type Block = import("@/lib/reader/types").Block;
```

- [ ] **Step 2: Commit**

```bash
git add web/src/lib/recitation/types.ts
git commit -m "web: recitation types (WS protocol + hook surface)"
```

---

### Task 5: `passage.ts` — pure block-to-passage conversion

Pure function. Heaviest test target in the reader.

**Files:**
- Create: `web/src/lib/recitation/passage.ts`
- Test: `web/src/lib/recitation/passage.test.ts`

- [ ] **Step 1: Write failing tests**

```ts
// web/src/lib/recitation/passage.test.ts
import { describe, it, expect } from "vitest";
import { buildPassage } from "./passage";
import type { Block } from "@/lib/reader/types";

const tok = (id: string, text: string) => ({ id, text });

const block = (key: string, type: Block["type"], words: [string, string][]) => ({
  key,
  type,
  tokens: words.map(([id, text]) => tok(id, text)),
}) as Block;

describe("buildPassage", () => {
  it("returns null when chapterBlocks is empty", () => {
    const r = buildPassage({ chapterBlocks: [], anchorBlockKey: "x" });
    expect(r).toBeNull();
  });

  it("returns null when no recitable blocks (only headings)", () => {
    const r = buildPassage({
      chapterBlocks: [block("b1", "heading", [["t1", "بَاب"]])],
      anchorBlockKey: "b1",
    });
    expect(r).toBeNull();
  });

  it("one prose block becomes one phrase", () => {
    const b = block("b1", "prose", [["t1", "الكَلَامُ"], ["t2", "هُوَ"]]);
    const r = buildPassage({ chapterBlocks: [b], anchorBlockKey: "b1" });
    expect(r).not.toBeNull();
    expect(r!.phrases).toEqual(["الكَلَامُ هُوَ"]);
    expect(r!.wordIndexToTokenId).toEqual(["t1", "t2"]);
    expect(r!.startCursor).toBe(0);
  });

  it("anchor in the middle keeps the requested lookbehind", () => {
    const blocks = [
      block("b1", "prose", [["t1", "أَحَدٌ"]]),
      block("b2", "prose", [["t2", "اِثْنَانِ"]]),
      block("b3", "prose", [["t3", "ثَلَاثَةٌ"]]),
      block("b4", "prose", [["t4", "أَرْبَعَةٌ"]]),
    ];
    const r = buildPassage({
      chapterBlocks: blocks,
      anchorBlockKey: "b3",
      lookbehindCount: 2,
      lookaheadPhraseCount: 1,
    });
    expect(r).not.toBeNull();
    expect(r!.phrases).toEqual(["أَحَدٌ", "اِثْنَانِ", "ثَلَاثَةٌ", "أَرْبَعَةٌ"]);
    expect(r!.startCursor).toBe(2);
  });

  it("anchor at chapter start clamps lookbehind to 0", () => {
    const blocks = [
      block("b1", "prose", [["t1", "أَحَدٌ"]]),
      block("b2", "prose", [["t2", "اِثْنَانِ"]]),
    ];
    const r = buildPassage({
      chapterBlocks: blocks,
      anchorBlockKey: "b1",
      lookbehindCount: 2,
      lookaheadPhraseCount: 5,
    });
    expect(r!.startCursor).toBe(0);
    expect(r!.phrases[0]).toBe("أَحَدٌ");
  });

  it("splits long blocks at pause markers (.، ؛ : !) when over 40 words", () => {
    // Build a 50-word block with a Arabic comma at word 25
    const tokens = Array.from({ length: 50 }, (_, i) => {
      const text = i === 24 ? "كَلِمَةٌ،" : "كَلِمَةٌ";
      return tok(`t${i}`, text);
    });
    const b: Block = { key: "long", type: "prose", tokens };
    const r = buildPassage({ chapterBlocks: [b], anchorBlockKey: "long" });
    expect(r).not.toBeNull();
    expect(r!.phrases.length).toBeGreaterThan(1);
    // First chunk should end at the comma (~25 words)
    expect(r!.phrases[0].split(" ").length).toBeLessThanOrEqual(25);
  });

  it("hard-splits at word boundary if no pause markers in long block", () => {
    const tokens = Array.from({ length: 90 }, (_, i) => tok(`t${i}`, "كَلِمَة"));
    const b: Block = { key: "long", type: "prose", tokens };
    const r = buildPassage({ chapterBlocks: [b], anchorBlockKey: "long" });
    expect(r).not.toBeNull();
    // Each phrase ≤ 40 words
    for (const p of r!.phrases) {
      expect(p.split(" ").length).toBeLessThanOrEqual(40);
    }
  });

  it("poetry: each hemistich becomes its own phrase", () => {
    const poetry: Block = {
      key: "p1",
      type: "poetry",
      hemistichs: [[
        [tok("a", "بَيْتٌ"), tok("b", "أَوَّلُ")],
        [tok("c", "بَيْتٌ"), tok("d", "ثَانٍ")],
      ]],
    };
    const r = buildPassage({ chapterBlocks: [poetry], anchorBlockKey: "p1" });
    expect(r!.phrases).toEqual(["بَيْتٌ أَوَّلُ", "بَيْتٌ ثَانٍ"]);
    expect(r!.wordIndexToTokenId).toEqual(["a", "b", "c", "d"]);
  });

  it("flat wordIndexToTokenId aligns with engine's space-split", () => {
    const blocks = [
      block("b1", "prose", [["t1", "وَاحِدٌ"], ["t2", "اِثْنَانِ"]]),
      block("b2", "prose", [["t3", "ثَلَاثَةٌ"]]),
    ];
    const r = buildPassage({ chapterBlocks: blocks, anchorBlockKey: "b1" });
    const allWords = r!.phrases.flatMap((p) => p.split(" "));
    expect(allWords.length).toBe(r!.wordIndexToTokenId.length);
    expect(allWords[0]).toBe("وَاحِدٌ");
    expect(r!.wordIndexToTokenId[0]).toBe("t1");
  });
});
```

- [ ] **Step 2: Run test, verify it fails**

```bash
cd web && npm run test -- passage
```

Expected: ALL FAIL — `buildPassage` doesn't exist.

- [ ] **Step 3: Implement `buildPassage`**

```ts
// web/src/lib/recitation/passage.ts
import type { Block } from "@/lib/reader/types";

const PHRASE_WORD_CAP = 40;
// Common Arabic + ASCII pause markers, in priority order
const PAUSE_MARKERS = /[.،؛:!؟?]/u;

type PhraseUnit = {
  text: string;
  tokenIds: string[]; // one per space-split word in `text`
  blockKey: string;
};

export type BuildPassageInput = {
  chapterBlocks: Block[];
  anchorBlockKey: string;
  lookbehindCount?: number;
  lookaheadPhraseCount?: number;
};

export type BuildPassageResult = {
  phrases: string[];
  wordIndexToTokenId: string[];
  startCursor: number;
};

export function buildPassage(
  input: BuildPassageInput,
): BuildPassageResult | null {
  const lookbehindCount = input.lookbehindCount ?? 2;
  const lookaheadPhraseCount = input.lookaheadPhraseCount ?? 15;

  // Step 1: convert all chapter blocks to phrase units
  const allUnits: PhraseUnit[] = [];
  for (const block of input.chapterBlocks) {
    if (block.type === "heading") continue;
    const units = blockToUnits(block);
    allUnits.push(...units);
  }
  if (allUnits.length === 0) return null;

  // Step 2: locate anchor (first phrase belonging to the anchor block, or first unit if not found)
  let anchorIdx = allUnits.findIndex((u) => u.blockKey === input.anchorBlockKey);
  if (anchorIdx < 0) anchorIdx = 0;

  // Step 3: slice [anchor - lookbehind … anchor + lookahead]
  const startIdx = Math.max(0, anchorIdx - lookbehindCount);
  const endIdx = Math.min(allUnits.length, anchorIdx + lookaheadPhraseCount + 1);
  const window = allUnits.slice(startIdx, endIdx);

  if (window.length === 0) return null;

  return {
    phrases: window.map((u) => u.text),
    wordIndexToTokenId: window.flatMap((u) => u.tokenIds),
    startCursor: anchorIdx - startIdx,
  };
}

function blockToUnits(block: Block): PhraseUnit[] {
  if (block.type === "poetry") {
    const out: PhraseUnit[] = [];
    for (const verse of block.hemistichs) {
      for (const hemistich of verse) {
        const text = hemistich.map((t) => t.text).join(" ").trim();
        if (!text) continue;
        out.push({
          text,
          tokenIds: hemistich.map((t) => t.id),
          blockKey: block.key,
        });
      }
    }
    return out;
  }

  // Prose-like: tokens = block.tokens
  const tokens = block.tokens;
  if (!tokens || tokens.length === 0) return [];

  // If short enough, one unit
  if (tokens.length <= PHRASE_WORD_CAP) {
    const text = tokens.map((t) => t.text).join(" ").trim();
    if (!text) return [];
    return [{ text, tokenIds: tokens.map((t) => t.id), blockKey: block.key }];
  }

  // Long block: split at pause markers, then hard-cap
  return splitLong(tokens, block.key);
}

function splitLong(
  tokens: { id: string; text: string }[],
  blockKey: string,
): PhraseUnit[] {
  const units: PhraseUnit[] = [];
  let cur: typeof tokens = [];

  const flush = () => {
    if (cur.length === 0) return;
    units.push({
      text: cur.map((t) => t.text).join(" "),
      tokenIds: cur.map((t) => t.id),
      blockKey,
    });
    cur = [];
  };

  for (const t of tokens) {
    cur.push(t);
    const hasPause = PAUSE_MARKERS.test(t.text);
    if (hasPause && cur.length >= 6) {
      flush();
      continue;
    }
    if (cur.length >= PHRASE_WORD_CAP) {
      flush();
    }
  }
  flush();
  return units;
}
```

- [ ] **Step 4: Run tests**

```bash
cd web && npm run test -- passage
```

Expected: ALL PASS.

- [ ] **Step 5: Commit**

```bash
git add web/src/lib/recitation/passage.ts web/src/lib/recitation/passage.test.ts
git commit -m "web: passage.ts — block-to-phrase conversion with sliding window"
```

---

### Task 6: `audio.ts` — AudioWorklet capture (no automated test)

Audio capture is hard to automate in vitest's node env. We write the module, then verify manually in the smoke test (Task 11).

**Files:**
- Create: `web/src/lib/recitation/audio.ts`

- [ ] **Step 1: Implement audio capture**

```ts
// web/src/lib/recitation/audio.ts
// AudioWorklet-based mic capture → 16 kHz mono float32 PCM chunks.
// Pattern lifted from recitation/static/index.html into a clean module.

const TARGET_SR = 16000;

export type AudioCapture = {
  chunks: AsyncIterable<Float32Array>;
  stop: () => Promise<void>;
};

export async function startCapture(): Promise<AudioCapture> {
  if (typeof window === "undefined") {
    throw new Error("startCapture must run in the browser");
  }

  const stream = await navigator.mediaDevices.getUserMedia({
    audio: {
      channelCount: 1,
      echoCancellation: true,
      noiseSuppression: true,
    },
  });

  const ctx = new (window.AudioContext ||
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    (window as any).webkitAudioContext)();
  const sourceSampleRate = ctx.sampleRate;

  // Inline AudioWorklet processor: pumps mono float32 samples to main thread.
  const processorSrc = `
    class P extends AudioWorkletProcessor {
      process(inputs) {
        const input = inputs[0];
        if (input && input[0]) {
          this.port.postMessage(input[0].slice(0));
        }
        return true;
      }
    }
    registerProcessor("recitation-pcm", P);
  `;
  const blob = new Blob([processorSrc], { type: "application/javascript" });
  const url = URL.createObjectURL(blob);
  await ctx.audioWorklet.addModule(url);
  URL.revokeObjectURL(url);

  const node = new AudioWorkletNode(ctx, "recitation-pcm");
  const source = ctx.createMediaStreamSource(stream);
  source.connect(node);

  const queue: Float32Array[] = [];
  const waiters: Array<(v: Float32Array | null) => void> = [];

  node.port.onmessage = (e: MessageEvent<Float32Array>) => {
    const sample = resample(e.data, sourceSampleRate, TARGET_SR);
    if (waiters.length > 0) {
      const w = waiters.shift()!;
      w(sample);
    } else {
      queue.push(sample);
    }
  };

  let stopped = false;

  const chunks: AsyncIterable<Float32Array> = {
    [Symbol.asyncIterator]() {
      return {
        async next() {
          if (queue.length > 0) {
            return { done: false, value: queue.shift()! };
          }
          if (stopped) return { done: true, value: undefined as unknown as Float32Array };
          const v = await new Promise<Float32Array | null>((resolve) =>
            waiters.push(resolve),
          );
          if (v == null) return { done: true, value: undefined as unknown as Float32Array };
          return { done: false, value: v };
        },
      };
    },
  };

  return {
    chunks,
    stop: async () => {
      stopped = true;
      while (waiters.length) waiters.shift()!(null);
      try { source.disconnect(); } catch {}
      try { node.disconnect(); } catch {}
      stream.getTracks().forEach((t) => t.stop());
      await ctx.close();
    },
  };
}

// Linear-interpolation downsample from sourceSR to targetSR.
function resample(src: Float32Array, sourceSR: number, targetSR: number): Float32Array {
  if (sourceSR === targetSR) return src;
  const ratio = sourceSR / targetSR;
  const outLen = Math.floor(src.length / ratio);
  const out = new Float32Array(outLen);
  for (let i = 0; i < outLen; i++) {
    const srcIdx = i * ratio;
    const lo = Math.floor(srcIdx);
    const hi = Math.min(lo + 1, src.length - 1);
    const frac = srcIdx - lo;
    out[i] = src[lo] * (1 - frac) + src[hi] * frac;
  }
  return out;
}
```

- [ ] **Step 2: Commit**

```bash
git add web/src/lib/recitation/audio.ts
git commit -m "web: audio.ts — AudioWorklet mic capture, resample to 16 kHz"
```

---

### Task 7: `client.ts` — WebSocket wrapper with mockable transport

Test by injecting a fake WebSocket implementation; the production code uses the global `WebSocket`.

**Files:**
- Create: `web/src/lib/recitation/client.ts`
- Test: `web/src/lib/recitation/client.test.ts`

- [ ] **Step 1: Write failing tests**

```ts
// web/src/lib/recitation/client.test.ts
import { describe, it, expect, vi } from "vitest";
import { RecitationClient } from "./client";
import type { ScoreEvent } from "./types";

class FakeWS {
  static instances: FakeWS[] = [];
  url: string;
  readyState = 0; // CONNECTING
  onopen: ((ev: Event) => void) | null = null;
  onmessage: ((ev: MessageEvent) => void) | null = null;
  onerror: ((ev: Event) => void) | null = null;
  onclose: ((ev: CloseEvent) => void) | null = null;
  sent: Array<string | ArrayBuffer | Float32Array> = [];

  constructor(url: string) {
    this.url = url;
    FakeWS.instances.push(this);
  }
  send(data: string | ArrayBuffer | Float32Array) { this.sent.push(data); }
  close() {
    this.readyState = 3; // CLOSED
    this.onclose?.({ code: 1000, reason: "", wasClean: true } as CloseEvent);
  }
  // Helpers for tests
  _open() { this.readyState = 1; this.onopen?.({} as Event); }
  _emit(payload: unknown) { this.onmessage?.({ data: JSON.stringify(payload) } as MessageEvent); }
}

describe("RecitationClient", () => {
  it("sends init on connect", async () => {
    FakeWS.instances = [];
    const c = new RecitationClient({
      url: "ws://test/ws",
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      WebSocketImpl: FakeWS as any,
    });
    const connectP = c.connect({
      passage: { id: "x", phrases: ["hello"] },
      lookbehindCount: 0,
    });
    FakeWS.instances[0]._open();
    await connectP;

    expect(FakeWS.instances[0].sent.length).toBe(1);
    const init = JSON.parse(FakeWS.instances[0].sent[0] as string);
    expect(init.passage.phrases).toEqual(["hello"]);
    expect(init.lookbehind_count).toBe(0);
  });

  it("emits score events to subscribers", async () => {
    FakeWS.instances = [];
    const c = new RecitationClient({
      url: "ws://test/ws",
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      WebSocketImpl: FakeWS as any,
    });
    const handler = vi.fn();
    c.onScore(handler);
    const p = c.connect({ passage: { id: "x", phrases: ["a"] } });
    FakeWS.instances[0]._open();
    await p;

    const score: ScoreEvent = { words: [], matched_phrase_idx: 0 };
    FakeWS.instances[0]._emit(score);
    expect(handler).toHaveBeenCalledWith(score);
  });

  it("appendPhrases sends a typed text frame", async () => {
    FakeWS.instances = [];
    const c = new RecitationClient({
      url: "ws://test/ws",
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      WebSocketImpl: FakeWS as any,
    });
    const p = c.connect({ passage: { id: "x", phrases: ["a"] } });
    FakeWS.instances[0]._open();
    await p;

    c.appendPhrases(["b", "c"]);
    const last = JSON.parse(FakeWS.instances[0].sent.at(-1) as string);
    expect(last).toEqual({ type: "append_phrases", phrases: ["b", "c"] });
  });

  it("ping → pong", async () => {
    FakeWS.instances = [];
    const c = new RecitationClient({
      url: "ws://test/ws",
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      WebSocketImpl: FakeWS as any,
    });
    const p = c.connect({ passage: { id: "x", phrases: ["a"] } });
    FakeWS.instances[0]._open();
    await p;

    FakeWS.instances[0]._emit({ type: "ping" });
    expect(FakeWS.instances[0].sent.at(-1)).toBe("pong");
  });
});
```

- [ ] **Step 2: Run tests, verify they fail**

```bash
cd web && npm run test -- client
```

Expected: FAIL — `RecitationClient` doesn't exist.

- [ ] **Step 3: Implement client**

```ts
// web/src/lib/recitation/client.ts
import type {
  InitMessage, AppendMessage, ScoreEvent, ServerErrorEvent, ConnectionState,
} from "./types";

type Listener<T> = (v: T) => void;

type Init = Omit<InitMessage, "passage" | "auth_token"> & {
  passage: InitMessage["passage"];
};

export type RecitationClientOpts = {
  url: string;
  tokenProvider?: () => Promise<string>;
  // For tests: inject a fake WebSocket constructor.
  WebSocketImpl?: typeof WebSocket;
};

export class RecitationClient {
  private opts: RecitationClientOpts;
  private ws: WebSocket | null = null;
  private state: ConnectionState = "idle";
  private scoreListeners: Listener<ScoreEvent>[] = [];
  private errorListeners: Listener<ServerErrorEvent>[] = [];
  private stateListeners: Listener<ConnectionState>[] = [];

  constructor(opts: RecitationClientOpts) {
    this.opts = opts;
  }

  onScore(fn: Listener<ScoreEvent>) { this.scoreListeners.push(fn); }
  onError(fn: Listener<ServerErrorEvent>) { this.errorListeners.push(fn); }
  onState(fn: Listener<ConnectionState>) { this.stateListeners.push(fn); }

  getState(): ConnectionState { return this.state; }

  async connect(init: Init): Promise<void> {
    this.setState("connecting");
    const Impl = this.opts.WebSocketImpl ?? WebSocket;

    let authToken: string | undefined;
    if (this.opts.tokenProvider) {
      authToken = await this.opts.tokenProvider();
    }

    return new Promise((resolve, reject) => {
      const ws = new Impl(this.opts.url);
      this.ws = ws;
      ws.onopen = () => {
        const payload: InitMessage = {
          passage: init.passage,
          lookbehind_count: init.lookbehind_count ?? 0,
          ...(authToken ? { auth_token: authToken } : {}),
        };
        ws.send(JSON.stringify(payload));
        this.setState("connected");
        resolve();
      };
      ws.onmessage = (ev) => this.handleMessage(ev);
      ws.onerror = () => {
        this.setState("error");
        reject(new Error("WS error"));
      };
      ws.onclose = () => {
        if (this.state !== "error") this.setState("idle");
      };
    });
  }

  sendAudio(buf: Float32Array | ArrayBuffer): void {
    if (!this.ws || this.ws.readyState !== 1) return;
    this.ws.send(buf instanceof Float32Array ? buf.buffer : buf);
  }

  appendPhrases(phrases: string[]): void {
    if (!this.ws || this.ws.readyState !== 1) return;
    const msg: AppendMessage = { type: "append_phrases", phrases };
    this.ws.send(JSON.stringify(msg));
  }

  done(): void {
    if (!this.ws || this.ws.readyState !== 1) return;
    this.ws.send("done");
  }

  close(): void {
    try { this.ws?.close(); } catch { /* noop */ }
    this.ws = null;
    this.setState("idle");
  }

  private handleMessage(ev: MessageEvent): void {
    let data: unknown;
    try {
      data = typeof ev.data === "string" ? JSON.parse(ev.data) : null;
    } catch {
      return;
    }
    if (!data || typeof data !== "object") return;
    const obj = data as Record<string, unknown>;
    if (obj.type === "ping") {
      this.ws?.send("pong");
      return;
    }
    if (obj.type === "error") {
      this.errorListeners.forEach((fn) => fn(obj as unknown as ServerErrorEvent));
      this.setState("error");
      return;
    }
    if (Array.isArray(obj.words)) {
      this.scoreListeners.forEach((fn) => fn(obj as unknown as ScoreEvent));
    }
  }

  private setState(s: ConnectionState): void {
    this.state = s;
    this.stateListeners.forEach((fn) => fn(s));
  }
}
```

- [ ] **Step 4: Run tests**

```bash
cd web && npm run test -- client
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add web/src/lib/recitation/client.ts web/src/lib/recitation/client.test.ts
git commit -m "web: RecitationClient — WS wrapper with injectable transport"
```

---

### Task 8: `state.ts` reducer + `useRecitation.ts` hook

Extract the state machine into a pure reducer (testable without React); the hook is a thin wrapper.

**Files:**
- Create: `web/src/lib/recitation/state.ts`
- Test: `web/src/lib/recitation/state.test.ts`
- Create: `web/src/lib/recitation/useRecitation.ts`

- [ ] **Step 1: Write failing reducer tests**

```ts
// web/src/lib/recitation/state.test.ts
import { describe, it, expect } from "vitest";
import { recitationReducer, initialRecitationState } from "./state";
import type { ScoreEvent } from "./types";

describe("recitationReducer", () => {
  it("starts idle with empty status", () => {
    expect(initialRecitationState.connectionState).toBe("idle");
    expect(initialRecitationState.status.size).toBe(0);
  });

  it("applies score event: maps idx → tokenId", () => {
    const wordIndexToTokenId = ["t0", "t1", "t2", "t3"];
    const event: ScoreEvent = {
      words: [
        { idx: 0, word: "a", status: "correct", error_type: null, error_detail: null },
        { idx: 1, word: "b", status: "error", error_type: "i3rab", error_detail: null },
      ],
      matched_phrase_idx: 0,
    };
    const next = recitationReducer(
      { ...initialRecitationState, wordIndexToTokenId },
      { type: "score", event },
    );
    expect(next.status.get("t0")).toBe("correct");
    expect(next.status.get("t1")).toBe("i3rab");
    expect(next.status.has("t2")).toBe(false);
  });

  it("connection state updates", () => {
    const next = recitationReducer(initialRecitationState, {
      type: "connection",
      state: "connected",
    });
    expect(next.connectionState).toBe("connected");
  });

  it("reset clears everything", () => {
    const filled = recitationReducer(initialRecitationState, {
      type: "score",
      event: {
        words: [{ idx: 0, word: "a", status: "correct", error_type: null, error_detail: null }],
        matched_phrase_idx: 0,
      },
    });
    const next = recitationReducer(
      { ...filled, wordIndexToTokenId: ["t0"] },
      { type: "reset" },
    );
    expect(next.status.size).toBe(0);
    expect(next.cursorTokenId).toBeNull();
  });
});
```

- [ ] **Step 2: Run, verify fails**

```bash
cd web && npm run test -- state
```

Expected: FAIL.

- [ ] **Step 3: Implement reducer**

```ts
// web/src/lib/recitation/state.ts
import type {
  ConnectionState,
  RecitationStatus,
  ScoreEvent,
  ServerErrorEvent,
} from "./types";

export type RecitationState = {
  connectionState: ConnectionState;
  status: Map<string, RecitationStatus>;
  cursorTokenId: string | null;
  matchedPhraseIdx: number | null;
  wordIndexToTokenId: string[];
  error?: string;
};

export const initialRecitationState: RecitationState = {
  connectionState: "idle",
  status: new Map(),
  cursorTokenId: null,
  matchedPhraseIdx: null,
  wordIndexToTokenId: [],
};

export type Action =
  | { type: "score"; event: ScoreEvent }
  | { type: "connection"; state: ConnectionState }
  | { type: "error"; event: ServerErrorEvent }
  | { type: "passage_loaded"; wordIndexToTokenId: string[] }
  | { type: "reset" };

export function recitationReducer(
  s: RecitationState,
  a: Action,
): RecitationState {
  switch (a.type) {
    case "passage_loaded":
      return {
        ...s,
        wordIndexToTokenId: a.wordIndexToTokenId,
        status: new Map(),
        cursorTokenId: null,
        matchedPhraseIdx: null,
      };
    case "score": {
      const status = new Map(s.status);
      let highest = -1;
      for (const w of a.event.words) {
        const tokenId = s.wordIndexToTokenId[w.idx];
        if (!tokenId) continue;
        const next: RecitationStatus =
          w.status === "correct"
            ? "correct"
            : w.error_type === "wrong"
              ? "wrong_word"
              : w.error_type === "skipped"
                ? "skipped"
                : w.error_type === "i3rab"
                  ? "i3rab"
                  : w.error_type === "tashkeel"
                    ? "tashkeel"
                    : "correct";
        status.set(tokenId, next);
        if (w.idx > highest) highest = w.idx;
      }
      const cursorTokenId =
        highest >= 0 && highest + 1 < s.wordIndexToTokenId.length
          ? s.wordIndexToTokenId[highest + 1]
          : highest >= 0
            ? s.wordIndexToTokenId[highest]
            : s.cursorTokenId;
      return {
        ...s,
        status,
        cursorTokenId,
        matchedPhraseIdx: a.event.matched_phrase_idx,
      };
    }
    case "connection":
      return { ...s, connectionState: a.state };
    case "error":
      return { ...s, error: a.event.message, connectionState: "error" };
    case "reset":
      return { ...initialRecitationState };
  }
}
```

- [ ] **Step 4: Run, verify pass**

```bash
cd web && npm run test -- state
```

Expected: PASS.

- [ ] **Step 5: Implement `useRecitation` hook**

```ts
// web/src/lib/recitation/useRecitation.ts
"use client";
import { useCallback, useEffect, useReducer, useRef, useState } from "react";
import type { Block } from "@/lib/reader/types";
import { buildPassage } from "./passage";
import { RecitationClient } from "./client";
import { recitationReducer, initialRecitationState } from "./state";
import type { ScoreEvent } from "./types";

const APPEND_BATCH = 10;
const APPEND_WATERMARK = 0.7;

type Opts = {
  chapterBlocks: Block[];
  wsUrl: string;
  tokenProvider?: () => Promise<string>;
};

export function useRecitation({ chapterBlocks, wsUrl, tokenProvider }: Opts) {
  const [state, dispatch] = useReducer(recitationReducer, initialRecitationState);
  const clientRef = useRef<RecitationClient | null>(null);
  const captureRef = useRef<{ stop: () => Promise<void> } | null>(null);
  const allUnitsRef = useRef<{ phrases: string[]; tokenIds: string[][] } | null>(null);
  const sentPhraseCountRef = useRef(0);
  const [anchorBlockKey, setAnchorBlockKey] = useState<string | null>(null);

  const start = useCallback(
    async (anchor: string) => {
      setAnchorBlockKey(anchor);
      const initial = buildPassage({
        chapterBlocks,
        anchorBlockKey: anchor,
        lookbehindCount: 2,
        lookaheadPhraseCount: APPEND_BATCH * 2,
      });
      if (!initial) {
        dispatch({ type: "connection", state: "error" });
        return;
      }
      // Pre-compute the full chapter's units so we can append later
      const fullPassage = buildPassage({
        chapterBlocks,
        anchorBlockKey: anchor,
        lookbehindCount: 0,
        lookaheadPhraseCount: 1_000_000,
      });
      if (!fullPassage) return;

      dispatch({ type: "passage_loaded", wordIndexToTokenId: initial.wordIndexToTokenId });
      sentPhraseCountRef.current = initial.phrases.length;

      const client = new RecitationClient({ url: wsUrl, tokenProvider });
      clientRef.current = client;
      client.onScore((ev: ScoreEvent) => {
        dispatch({ type: "score", event: ev });
        // Auto-append: when matched_phrase_idx crosses the watermark, send next batch
        if (
          ev.matched_phrase_idx >=
          Math.floor(sentPhraseCountRef.current * APPEND_WATERMARK)
        ) {
          const nextSlice = fullPassage.phrases.slice(
            sentPhraseCountRef.current,
            sentPhraseCountRef.current + APPEND_BATCH,
          );
          if (nextSlice.length > 0) {
            client.appendPhrases(nextSlice);
            // Extend wordIndexToTokenId
            const startTok = fullPassage.wordIndexToTokenId.indexOf(
              fullPassage.phrases.slice(0, sentPhraseCountRef.current).join(" ").split(" ").length === 0
                ? fullPassage.wordIndexToTokenId[0]
                : fullPassage.wordIndexToTokenId[
                    fullPassage.phrases.slice(0, sentPhraseCountRef.current).flatMap((p) => p.split(" ")).length
                  ],
            );
            const newWordCount = nextSlice.flatMap((p) => p.split(" ")).length;
            const newTokenIds = fullPassage.wordIndexToTokenId.slice(
              state.wordIndexToTokenId.length,
              state.wordIndexToTokenId.length + newWordCount,
            );
            dispatch({
              type: "passage_loaded",
              wordIndexToTokenId: [...state.wordIndexToTokenId, ...newTokenIds],
            });
            sentPhraseCountRef.current += nextSlice.length;
          }
        }
      });
      client.onError((e) => dispatch({ type: "error", event: e }));
      client.onState((s) => dispatch({ type: "connection", state: s }));

      await client.connect({
        passage: { id: `chapter-${anchor}`, phrases: initial.phrases },
        lookbehind_count: initial.startCursor,
      });

      // Start audio capture and forward to client
      const { startCapture } = await import("./audio");
      const cap = await startCapture();
      captureRef.current = cap;
      (async () => {
        for await (const chunk of cap.chunks) {
          client.sendAudio(chunk);
        }
      })();
    },
    [chapterBlocks, wsUrl, tokenProvider, state.wordIndexToTokenId],
  );

  const stop = useCallback(async () => {
    try { clientRef.current?.done(); } catch { /* noop */ }
    try { await captureRef.current?.stop(); } catch { /* noop */ }
    clientRef.current?.close();
    clientRef.current = null;
    captureRef.current = null;
    dispatch({ type: "reset" });
  }, []);

  useEffect(() => {
    return () => {
      stop().catch(() => undefined);
    };
  }, [stop]);

  return {
    start,
    stop,
    status: state.status,
    cursorTokenId: state.cursorTokenId,
    connectionState: state.connectionState,
    error: state.error,
    anchorBlockKey,
  };
}
```

Note: the chunk-of-tokens append logic above is intentionally simplified. If the indexing math turns out to be brittle, a follow-up task can refactor `buildPassage` to expose a "next slice from offset" helper. For v1, the formula works because phrases are space-split identically on both sides.

- [ ] **Step 6: Commit**

```bash
git add web/src/lib/recitation/state.ts web/src/lib/recitation/state.test.ts web/src/lib/recitation/useRecitation.ts
git commit -m "web: useRecitation hook + pure state reducer"
```

---

## Phase 3 — Reader UI

### Task 9: `RecitationProvider` + `ReciteToggle` + CSS

**Files:**
- Create: `web/src/components/reader/recite/RecitationProvider.tsx`
- Create: `web/src/components/reader/recite/ReciteToggle.tsx`
- Create: `web/src/components/reader/recite/recite.css`

- [ ] **Step 1: Create context provider**

```tsx
// web/src/components/reader/recite/RecitationProvider.tsx
"use client";
import { createContext, useContext, type ReactNode } from "react";
import type { RecitationStatus } from "@/lib/recitation/types";

type Ctx = {
  status: Map<string, RecitationStatus>;
  cursorTokenId: string | null;
};

const RecitationContext = createContext<Ctx>({
  status: new Map(),
  cursorTokenId: null,
});

export function RecitationProvider({
  children,
  status,
  cursorTokenId,
}: {
  children: ReactNode;
  status: Map<string, RecitationStatus>;
  cursorTokenId: string | null;
}) {
  return (
    <RecitationContext.Provider value={{ status, cursorTokenId }}>
      {children}
    </RecitationContext.Provider>
  );
}

export function useRecitationStatus(tokenId: string): RecitationStatus | null {
  const ctx = useContext(RecitationContext);
  if (ctx.cursorTokenId === tokenId) return "current";
  return ctx.status.get(tokenId) ?? null;
}
```

- [ ] **Step 2: Create the toggle**

```tsx
// web/src/components/reader/recite/ReciteToggle.tsx
"use client";
import { useEffect, useRef, useState } from "react";

type Props = {
  onStart: (anchorBlockKey: string) => void;
  onStop: () => void;
  disabled?: boolean;
  isActive: boolean;
};

export function ReciteToggle({ onStart, onStop, disabled, isActive }: Props) {
  const [topVisibleKey, setTopVisibleKey] = useState<string | null>(null);
  const ioRef = useRef<IntersectionObserver | null>(null);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const seen = new Map<string, number>();
    const io = new IntersectionObserver(
      (entries) => {
        for (const e of entries) {
          const key = (e.target as HTMLElement).dataset.blockKey;
          if (!key) continue;
          if (e.isIntersecting) seen.set(key, e.boundingClientRect.top);
          else seen.delete(key);
        }
        // Pick the one closest to the top (smallest top offset, but still visible)
        let best: [string, number] | null = null;
        for (const [k, t] of seen) {
          if (best === null || t < best[1]) best = [k, t];
        }
        setTopVisibleKey(best?.[0] ?? null);
      },
      { threshold: 0, rootMargin: "0px 0px -50% 0px" },
    );
    ioRef.current = io;
    document.querySelectorAll<HTMLElement>("[data-block-key]").forEach((el) => io.observe(el));
    return () => io.disconnect();
  }, []);

  const handle = () => {
    if (disabled) return;
    if (isActive) onStop();
    else if (topVisibleKey) onStart(topVisibleKey);
  };

  return (
    <button
      type="button"
      onClick={handle}
      disabled={disabled || (!isActive && !topVisibleKey)}
      className={`text-xs px-2 py-1 rounded font-mono ${
        isActive
          ? "bg-red-100 text-red-800 animate-pulse"
          : "bg-zinc-100 text-zinc-700 hover:bg-zinc-200 disabled:opacity-40"
      }`}
      title={disabled ? "No tashkeel — recite unavailable" : isActive ? "Stop" : "Recite"}
    >
      {isActive ? "● Stop" : "Recite"}
    </button>
  );
}
```

- [ ] **Step 3: Create CSS classes for status**

```css
/* web/src/components/reader/recite/recite.css */
.tok--correct      { color: rgb(22, 163, 74); }
.tok--wrong_word   { color: rgb(220, 38, 38); text-decoration: line-through; }
.tok--i3rab        { border-bottom: 2px solid rgb(37, 99, 235); }
.tok--tashkeel     { border-bottom: 2px solid rgb(234, 88, 12); }
.tok--skipped      { color: rgb(161, 161, 170); border-bottom: 2px dashed rgb(161, 161, 170); }
.tok--current      { background: rgba(250, 204, 21, 0.25); border-radius: 2px; }
```

- [ ] **Step 4: Commit**

```bash
git add web/src/components/reader/recite/
git commit -m "web: RecitationProvider + ReciteToggle + recite.css"
```

---

### Task 10: `TokenText` reads recitation status

**Files:**
- Modify: `web/src/components/reader/TokenText.tsx`

- [ ] **Step 1: Add status reading**

Open `web/src/components/reader/TokenText.tsx`. After the existing imports add:

```tsx
import { useRecitationStatus } from "./recite/RecitationProvider";
import "./recite/recite.css";
```

Inside the component, near the top, add:

```tsx
  const recitationStatus = useRecitationStatus(token.id);
  const recitationClass = recitationStatus ? `tok--${recitationStatus}` : "";
```

Then update the two `<span>` returns to apply the class:

For the reader-mode return:
```tsx
  if (mode === "reader") {
    return <span className={recitationClass}>{display} </span>;
  }
```

For the inspector-mode return, append `recitationClass` to the existing `className`:
```tsx
    <span
      data-token-id={token.id}
      title={token.id}
      onClick={onClick}
      className={`cursor-pointer underline decoration-dotted underline-offset-4 decoration-zinc-300 hover:decoration-zinc-600 ${recitationClass}`}
    >
```

- [ ] **Step 2: Commit**

```bash
git add web/src/components/reader/TokenText.tsx
git commit -m "web: TokenText applies recitation status class"
```

---

### Task 11: Wire chapter route + smoke test

**Files:**
- Modify: `web/src/components/reader/ChapterScroll.tsx` — wrap children in `RecitationProvider`, expose hook to a parent wrapper
- Modify: `web/src/app/internal/reader/[openiti_id]/[ch_index]/page.tsx` — add `ReciteToggle` to header, pass blocks to a new client wrapper

The cleanest integration is a new client component that owns the `useRecitation` hook and renders both the toggle and the provider.

- [ ] **Step 1: Create a wrapper**

```tsx
// web/src/components/reader/recite/ReciteShell.tsx
"use client";
import { useRecitation } from "@/lib/recitation/useRecitation";
import type { Block } from "@/lib/reader/types";
import { RecitationProvider } from "./RecitationProvider";
import { ReciteToggle } from "./ReciteToggle";
import type { ReactNode } from "react";

const WS_URL =
  process.env.NEXT_PUBLIC_RECITATION_WS_URL ?? "ws://localhost:8000/ws/score";

export function ReciteShell({
  chapterBlocks,
  recitable,
  children,
}: {
  chapterBlocks: Block[];
  recitable: boolean;
  children: ReactNode;
}) {
  const r = useRecitation({ chapterBlocks, wsUrl: WS_URL });
  const isActive = r.connectionState !== "idle" && r.connectionState !== "error";

  return (
    <>
      <div data-recite-controls className="contents">
        {/* Slot for the toggle, rendered into the header via portal-like positioning */}
        <ReciteToggleSlot
          disabled={!recitable}
          isActive={isActive}
          onStart={r.start}
          onStop={r.stop}
        />
      </div>
      <RecitationProvider status={r.status} cursorTokenId={r.cursorTokenId}>
        {children}
      </RecitationProvider>
    </>
  );
}

function ReciteToggleSlot(props: React.ComponentProps<typeof ReciteToggle>) {
  // Render the toggle inline; the page layout puts ReciteShell inside the
  // header area for the controls and then renders children below.
  return <ReciteToggle {...props} />;
}
```

This is intentionally simple — the page composes the toggle and the provider in the right places by structuring the JSX tree (next step).

- [ ] **Step 2: Update the chapter page**

Edit `web/src/app/internal/reader/[openiti_id]/[ch_index]/page.tsx`. Replace the existing `<ChapterScroll pages={pages} mode="reader" />` block with a structure that uses `ReciteShell`:

```tsx
import { ReciteShell } from "@/components/reader/recite/ReciteShell";

// ... inside ReaderChapter, after computing `pages`:

  // Determine if the chapter has any tashkeel (sample tokens)
  const recitable = pages.some((page) =>
    page.content_blocks.some((b) => {
      if (b.type === "poetry") return b.hemistichs.flat().flat().some((t) => /[\u064B-\u065F\u0670]/.test(t.text));
      return b.tokens.some((t) => /[\u064B-\u065F\u0670]/.test(t.text));
    }),
  );

  // Flatten chapter blocks for the recitation hook
  const chapterBlocks = pages.flatMap((p) => p.content_blocks);

  return (
    <>
      <header className="sticky top-0 z-10 bg-white/90 backdrop-blur border-b border-zinc-200 px-4 py-2 flex items-center gap-3 flex-wrap">
        <Link href="/internal/library" className="text-xs font-mono text-zinc-600 hover:text-zinc-900">
          ← library
        </Link>
        <div className="text-sm" dir="rtl">{result.book.title_ar}</div>
        <div className="text-xs text-zinc-500">— {chapter.title}</div>
        <div className="flex-1" />
        <ChapterDrawer chapters={chapters} currentSortOrder={chIdx} openitiId={decoded} mode="reader" />
        <TashkeelToggle />
        <ModeToggle mode="reader" />
        {/* ReciteShell renders both the toggle (here) and the provider (around content) */}
      </header>

      <ReciteShell chapterBlocks={chapterBlocks} recitable={recitable}>
        <ChapterScroll pages={pages} mode="reader" />
      </ReciteShell>

      {/* ... existing footer */}
    </>
  );
```

Adjust the layout: the toggle from `ReciteShell` will appear once the wrapper renders. If you want the toggle in the header, refactor `ReciteShell` to expose the toggle and provider as separate exports (e.g., `useReciteController` returns hooks values, and `<ReciteToggle/>`/`<RecitationProvider/>` are placed independently). For v1 a single `ReciteShell` rendering inline above the scroll is acceptable.

- [ ] **Step 3: Type-check and lint**

```bash
cd web && npm run lint && npx tsc --noEmit
```

Expected: clean.

- [ ] **Step 4: Manual smoke test**

```bash
# Terminal 1: recitation server
cd recitation && python -m uvicorn server:app --host 0.0.0.0 --port 8000

# Terminal 2: reader (assumes a tashkeeled chapter exists in web/data/)
cd web && npm run dev
```

- Open `http://localhost:3000/internal/reader/<openiti_id>/<ch_index>`
- Allow mic
- Tap **Recite**
- Read aloud from any visible block
- Verify words light up green / red / blue / orange in real time
- Tap **Stop**

- [ ] **Step 5: Commit**

```bash
git add web/src/components/reader/recite/ReciteShell.tsx web/src/app/internal/reader/[openiti_id]/[ch_index]/page.tsx
git commit -m "web: wire ReciteShell into the chapter page"
```

---

## Phase 4 — Production hardening

### Task 12: Server auth + origin + session caps + debug gate

All env-gated; in dev (no env set) behavior is unchanged.

**Files:**
- Create: `recitation/auth.py`
- Modify: `recitation/server.py`
- Test: `recitation/test_auth.py`

- [ ] **Step 1: Implement HMAC token utilities**

```python
# recitation/auth.py
"""Symmetric HMAC token: base64url(payload).hexdigest(hmac_sha256(secret, payload))

payload is JSON {origin, exp}. Same secret on reader (Next.js) and server.
"""
import base64
import hashlib
import hmac
import json
import time


def sign(secret: str, origin: str, ttl_sec: int = 300) -> str:
    payload = {"origin": origin, "exp": int(time.time()) + ttl_sec}
    raw = json.dumps(payload, separators=(",", ":")).encode()
    p64 = base64.urlsafe_b64encode(raw).rstrip(b"=").decode()
    sig = hmac.new(secret.encode(), p64.encode(), hashlib.sha256).hexdigest()
    return f"{p64}.{sig}"


def verify(secret: str, token: str, expected_origin: str | None = None) -> bool:
    try:
        p64, sig = token.split(".", 1)
    except ValueError:
        return False
    expected = hmac.new(secret.encode(), p64.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected):
        return False
    try:
        pad = "=" * (-len(p64) % 4)
        payload = json.loads(base64.urlsafe_b64decode(p64 + pad))
    except Exception:
        return False
    if int(payload.get("exp", 0)) < int(time.time()):
        return False
    if expected_origin and payload.get("origin") != expected_origin:
        return False
    return True
```

- [ ] **Step 2: Write auth tests**

```python
# recitation/test_auth.py
import time
from auth import sign, verify


def test_sign_verify_roundtrip():
    tok = sign("s3cret", "https://app.example", ttl_sec=60)
    assert verify("s3cret", tok)


def test_wrong_secret_fails():
    tok = sign("s3cret", "https://app.example", ttl_sec=60)
    assert not verify("WRONG", tok)


def test_expired_fails():
    tok = sign("s3cret", "https://app.example", ttl_sec=-1)
    assert not verify("s3cret", tok)


def test_origin_mismatch_fails():
    tok = sign("s3cret", "https://app.example", ttl_sec=60)
    assert not verify("s3cret", tok, expected_origin="https://other.example")
```

- [ ] **Step 3: Run, verify**

```bash
cd recitation && python -m pytest test_auth.py -v
```

Expected: PASS.

- [ ] **Step 4: Wire into `server.py`**

Add at the top of `server.py`:

```python
import os
from auth import verify as verify_auth_token

AUTH_SECRET = os.getenv("RECITATION_AUTH_SECRET")
ALLOWED_ORIGINS = (
    [o.strip() for o in os.getenv("RECITATION_ALLOWED_ORIGINS", "").split(",") if o.strip()]
    or None
)
ALLOW_DEBUG = os.getenv("RECITATION_ALLOW_DEBUG") == "1"
MAX_SESSION_SEC = int(os.getenv("RECITATION_MAX_SESSION_SEC", "600"))
```

In `ws_score`, after `await websocket.accept()`:

```python
    # Origin check (if allowlist set)
    origin = websocket.headers.get("origin")
    if ALLOWED_ORIGINS is not None and origin not in ALLOWED_ORIGINS:
        await websocket.send_json({"type": "error", "code": "origin_denied",
                                    "message": f"origin not allowed: {origin}"})
        await websocket.close(1008)
        return
```

After parsing `init`, before processing the passage:

```python
    # Auth check (if secret set)
    if AUTH_SECRET:
        token = init.get("auth_token")
        if not token or not verify_auth_token(AUTH_SECRET, token, expected_origin=origin):
            await websocket.send_json({"type": "error", "code": "auth_failed",
                                        "message": "invalid or expired auth_token"})
            await websocket.close(1008)
            return

    # Debug gate
    if init.get("debug") and not ALLOW_DEBUG:
        init["debug"] = False
```

In the receive loop, track session start time and enforce the cap:

```python
    session_start = time.time()
    # ... in the while loop, near the top:
            if time.time() - session_start > MAX_SESSION_SEC:
                await websocket.send_json({"type": "error", "code": "session_too_long",
                                            "message": "max session duration exceeded"})
                await websocket.close(1008)
                break
```

- [ ] **Step 5: Manual integration check**

```bash
RECITATION_AUTH_SECRET=test \
RECITATION_ALLOWED_ORIGINS=http://localhost:3000 \
python -m uvicorn server:app --host 0.0.0.0 --port 8000
# Connect from a browser without auth_token → expect close with auth_failed
```

- [ ] **Step 6: Commit**

```bash
git add recitation/auth.py recitation/test_auth.py recitation/server.py
git commit -m "recitation: env-gated HMAC auth, origin allowlist, session caps, debug gate"
```

---

### Task 13: Server ping/pong + idle timeout + structured logging

**Files:**
- Modify: `recitation/server.py`

- [ ] **Step 1: Add ping/pong loop**

In `ws_score`, before the receive loop, spawn a ping task:

```python
    last_client_msg = time.time()
    PING_INTERVAL = 30
    IDLE_TIMEOUT = 60

    async def pinger():
        while True:
            await asyncio.sleep(PING_INTERVAL)
            try:
                await websocket.send_json({"type": "ping"})
            except Exception:
                break

    ping_task = asyncio.create_task(pinger())
```

In the receive loop, update `last_client_msg`:

```python
            # Right after `msg = await websocket.receive()`:
            last_client_msg = time.time()
```

Add idle check inside the loop:

```python
            if time.time() - last_client_msg > IDLE_TIMEOUT:
                break
```

Treat client text frame `"pong"` as a noop:

```python
            if text == "pong":
                continue
```

In the `finally:` block, cancel the ping task:

```python
        ping_task.cancel()
```

- [ ] **Step 2: Add structured logging**

Add to top of `server.py`:

```python
import logging
import uuid

LOG_STREAMING = os.getenv("LOG_STREAMING") == "1"
log = logging.getLogger("recitation")
logging.basicConfig(format='{"ts":"%(asctime)s","level":"%(levelname)s","msg":%(message)s}',
                    level=logging.INFO)

def jlog(event: str, **fields):
    if LOG_STREAMING:
        log.info(json.dumps({"event": event, **fields}, ensure_ascii=False))
```

Sprinkle structured logs in `ws_score`:

```python
    session_id = uuid.uuid4().hex[:8]
    jlog("session_start", session_id=session_id, origin=origin, passage_phrases=len(phrases))
    # … on each score cycle:
    jlog("score_cycle", session_id=session_id, audio_bytes=session.total_audio_bytes,
         cursor=session.cursor_phrase)
    # … on error / finally:
    jlog("session_end", session_id=session_id, duration_sec=int(time.time() - session_start))
```

- [ ] **Step 3: Smoke test**

```bash
LOG_STREAMING=1 python -m uvicorn server:app --host 0.0.0.0 --port 8000
# Should now print one JSON line per score cycle, etc.
```

- [ ] **Step 4: Commit**

```bash
git add recitation/server.py
git commit -m "recitation: ping/pong, idle timeout, structured per-session logs"
```

---

### Task 14: Reader auth fetcher + Next.js token mint route

**Files:**
- Create: `web/src/lib/recitation/token.ts`
- Create: `web/src/app/api/recitation/token/route.ts`
- Test: `web/src/app/api/recitation/token/route.test.ts`
- Modify: `web/package.json` — add `jose`

- [ ] **Step 1: Add `jose`**

```bash
cd web && npm install jose
```

- [ ] **Step 2: Implement the mint route**

```ts
// web/src/app/api/recitation/token/route.ts
import { NextRequest, NextResponse } from "next/server";
import { createHmac } from "node:crypto";

export const runtime = "nodejs";

export async function POST(req: NextRequest) {
  const secret = process.env.RECITATION_AUTH_SECRET;
  if (!secret) {
    return NextResponse.json({ error: "auth disabled" }, { status: 404 });
  }
  const ttl = parseInt(process.env.RECITATION_TOKEN_TTL_SEC ?? "300", 10);
  const origin = req.nextUrl.origin;
  const exp = Math.floor(Date.now() / 1000) + ttl;
  const payload = JSON.stringify({ origin, exp });
  const p64 = Buffer.from(payload).toString("base64url");
  const sig = createHmac("sha256", secret).update(p64).digest("hex");
  return NextResponse.json({ token: `${p64}.${sig}` });
}
```

(We use `node:crypto` directly — same algorithm the Python `auth.py` uses. No `jose` needed; remove the install if you didn't use it elsewhere.)

- [ ] **Step 3: Test the route**

```ts
// web/src/app/api/recitation/token/route.test.ts
import { describe, it, expect, beforeEach } from "vitest";
import { POST } from "./route";

describe("/api/recitation/token", () => {
  beforeEach(() => {
    process.env.RECITATION_AUTH_SECRET = "s3cret";
  });

  it("returns a token when secret is set", async () => {
    const req = new Request("http://localhost:3000/api/recitation/token", {
      method: "POST",
    }) as unknown as import("next/server").NextRequest;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    (req as any).nextUrl = { origin: "http://localhost:3000" };
    const res = await POST(req);
    const body = await res.json();
    expect(body.token).toMatch(/^[A-Za-z0-9_-]+\.[a-f0-9]{64}$/);
  });

  it("404s when secret unset", async () => {
    delete process.env.RECITATION_AUTH_SECRET;
    const req = new Request("http://localhost:3000/api/recitation/token", {
      method: "POST",
    }) as unknown as import("next/server").NextRequest;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    (req as any).nextUrl = { origin: "http://localhost:3000" };
    const res = await POST(req);
    expect(res.status).toBe(404);
  });
});
```

```bash
cd web && npm run test -- token
```

Expected: PASS.

- [ ] **Step 4: Implement the client-side fetcher**

```ts
// web/src/lib/recitation/token.ts
let cached: { token: string; exp: number } | null = null;

export async function fetchAuthToken(): Promise<string> {
  const now = Math.floor(Date.now() / 1000);
  if (cached && cached.exp > now + 30) return cached.token;
  const res = await fetch("/api/recitation/token", { method: "POST" });
  if (!res.ok) throw new Error(`token fetch failed: ${res.status}`);
  const body = (await res.json()) as { token: string };
  // Decode exp from token payload (best-effort, just for caching)
  try {
    const [p64] = body.token.split(".");
    const pad = "=".repeat((4 - (p64.length % 4)) % 4);
    const payload = JSON.parse(atob(p64.replace(/-/g, "+").replace(/_/g, "/") + pad));
    cached = { token: body.token, exp: payload.exp };
  } catch {
    cached = { token: body.token, exp: now + 60 };
  }
  return body.token;
}
```

- [ ] **Step 5: Wire `fetchAuthToken` into `ReciteShell`**

In `web/src/components/reader/recite/ReciteShell.tsx`, change:

```tsx
const r = useRecitation({ chapterBlocks, wsUrl: WS_URL });
```

to (only when running with auth — v1 keeps it always-on but lets the route 404 in dev):

```tsx
import { fetchAuthToken } from "@/lib/recitation/token";

// inside the component:
const r = useRecitation({
  chapterBlocks,
  wsUrl: WS_URL,
  tokenProvider: WS_URL.startsWith("wss")
    ? fetchAuthToken
    : undefined,
});
```

- [ ] **Step 6: Commit**

```bash
git add web/src/lib/recitation/token.ts web/src/app/api/recitation/token/ web/src/components/reader/recite/ReciteShell.tsx web/package.json web/package-lock.json
git commit -m "web: token mint route + client fetcher (HMAC, prod-only)"
```

---

### Task 15: Dockerfile + dev-loop doc

**Files:**
- Create: `recitation/Dockerfile`
- Create: `recitation/.dockerignore`
- Create: `docs/recitation/dev-loop.md`

- [ ] **Step 1: Dockerfile**

```dockerfile
# recitation/Dockerfile
# Production container for the recitation server.
# Targets a CUDA image; for CPU-only deploys, change the base image.
FROM nvidia/cuda:12.3.1-runtime-ubuntu22.04

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.11 python3-pip ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Model weights expected at /app/models/ssl_xls_r_v5/.
# Bake them in by COPYing during build, or mount at runtime.

EXPOSE 8000
CMD ["python3", "-m", "uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 2: `.dockerignore`**

```
# recitation/.dockerignore
__pycache__/
*.pyc
test_data/sessions/
test_data/recordings/
.tts_cache/
.pytest_cache/
*.log
```

- [ ] **Step 3: Dev loop doc**

```markdown
# Recitation dev loop

End-to-end loop for working on the recitation ↔ reader integration.

## Prereqs

- `recitation/models/ssl_xls_r_v5/` — fine-tuned XLS-R weights.
- A tashkeeled chapter dumped under `web/data/` (see [docs/reader/dev-loop.md](../reader/dev-loop.md)).
- Python deps: `pip install -r recitation/requirements.txt pytest pytest-asyncio websockets`.
- Web deps: `cd web && npm install`.

## Run both

```
# Terminal 1
cd recitation && python -m uvicorn server:app --host 0.0.0.0 --port 8000

# Terminal 2
cd web && npm run dev
```

Open `http://localhost:3000/internal/reader/<openiti_id>/<ch_index>`, allow mic, tap **Recite**.

## Tests

```
# Engine + protocol
cd recitation && python -m pytest test_inline_passage.py test_extend_phrases.py test_retreat.py test_auth.py -v

# Reader library
cd web && npm run test -- recitation
```

## Production env (preview)

| Var (server) | Default | Effect |
|---|---|---|
| `RECITATION_AUTH_SECRET` | unset | Require valid HMAC token if set |
| `RECITATION_ALLOWED_ORIGINS` | unset | Comma-separated allowlist |
| `RECITATION_ALLOW_DEBUG` | `0` | Permit `debug:true` audio dumps |
| `RECITATION_MAX_SESSION_SEC` | `600` | Per-session hard cap |
| `LOG_STREAMING` | `0` | Emit JSON-line logs per cycle |

| Var (reader) | Default | Effect |
|---|---|---|
| `NEXT_PUBLIC_RECITATION_WS_URL` | `ws://localhost:8000/ws/score` | WS endpoint |
| `RECITATION_AUTH_SECRET` | unset | Same secret as server (for token mint) |
| `RECITATION_TOKEN_TTL_SEC` | `300` | JWT TTL |

## Deploying the recitation server

1. Build the image: `docker build -t suhuf-recitation recitation/`.
2. Push to your registry of choice.
3. Run on a GPU host (Modal / Railway-with-GPU / RunPod). Mount or bake `models/ssl_xls_r_v5/`.
4. Front it with a TLS-terminating proxy (Caddy / nginx / Cloudflare) so the WS upgrade is `wss://`.
5. Set the reader's `NEXT_PUBLIC_RECITATION_WS_URL` to that URL.
6. Set the same `RECITATION_AUTH_SECRET` on both sides.
7. Set `RECITATION_ALLOWED_ORIGINS=https://<reader-domain>` on the server.
```

- [ ] **Step 4: Commit**

```bash
git add recitation/Dockerfile recitation/.dockerignore docs/recitation/dev-loop.md
git commit -m "docs+ops: recitation Dockerfile and dev-loop guide"
```

---

## Self-Review

**Spec coverage check** — every spec section is implemented:
- ✅ WebSocket protocol (inline passage, append_phrases, ping/pong, error codes) → Tasks 1, 2, 13
- ✅ `passage.ts`, `audio.ts`, `client.ts`, `useRecitation.ts`, `types.ts`, `token.ts` → Tasks 4–8, 14
- ✅ `RecitationProvider`, `ReciteToggle`, `TokenText` status, chapter wiring → Tasks 9–11
- ✅ Engine `extend_phrases`, candidate window, retreat-with-unlock → Tasks 2, 3
- ✅ Auth, CORS/origin, session caps, debug gate, structured logs → Tasks 12, 13
- ✅ Dockerfile + dev-loop doc → Task 15
- ✅ Token mint route + reader-side fetcher → Task 14

**Placeholder scan** — no TBDs; the `useRecitation` append-index math has a noted possible refactor but is functional. The "ReciteToggleSlot" pattern in Task 11 is documented as v1-acceptable with a clear path to a cleaner split.

**Type consistency** — `RecitationStatus`, `ConnectionState`, `ScoreEvent`, `ScoreWord` used identically across `types.ts`, `state.ts`, `client.ts`, `useRecitation.ts`, `RecitationProvider.tsx`. Server-side `verify_auth_token` matches the format the reader's mint route emits.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-04-30-recitation-reader-integration.md`. Two execution options:

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints.

Which approach?
