# Word-Tap Agents in the Reader — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a reader tap any Arabic word in reader mode and open a tabbed popover (I'rab / Translation / Ask AI) backed by Next.js route handlers that call the Anthropic API.

**Architecture:** A pure util segments a block's flat tokens into sentences so each tapped word carries its sentence context. Three Next.js route handlers (`/api/agents/{irab,translate,ask-ai}`) port the existing Supabase edge-function prompts and call Anthropic via a shared `fetch` helper. A typed client wraps the routes. A reader-shell-level context holds the active word selection; a Floating-UI-anchored popover renders three lazily-fetched tabs. No caching, no auth (deferred to Group 0).

**Tech Stack:** Next.js (App Router, route handlers), React client components, TypeScript, Vitest (node environment), `@floating-ui/react`, Anthropic Messages API over `fetch`. Web deploys to Cloudflare via OpenNext, so routes must use `fetch` (no Node-only Anthropic SDK).

---

## Working directory

All paths below are relative to the `group-b-agents` worktree root:
`/Users/yousefh/Desktop/Cool Code/suhuf/.claude/worktrees/group-b-agents`

All `npm` / test commands run inside `web/`:
```bash
cd "/Users/yousefh/Desktop/Cool Code/suhuf/.claude/worktrees/group-b-agents/web"
```

Shipping is via `./bin/suhuf ship` from the worktree root — never raw `git push`. Per-task commits are plain `git commit`.

## File structure

Created:
- `web/src/lib/reader/sentences.ts` — pure sentence segmentation + selection map.
- `web/src/lib/reader/sentences.test.ts` — unit tests for segmentation.
- `web/src/lib/agents/types.ts` — request/response types shared by client + routes.
- `web/src/lib/agents/anthropic.ts` — shared server-side Anthropic `fetch` helper.
- `web/src/lib/agents/client.ts` — typed browser client over the routes.
- `web/src/lib/agents/client.test.ts` — unit tests for the client (mocked fetch).
- `web/src/app/api/agents/irab/route.ts` (+ `route.test.ts`)
- `web/src/app/api/agents/translate/route.ts` (+ `route.test.ts`)
- `web/src/app/api/agents/ask-ai/route.ts` (+ `route.test.ts`)
- `web/src/components/reader/word/WordPopoverProvider.tsx` — selection context.
- `web/src/components/reader/word/WordPopover.tsx` — tabbed anchored popover UI.
- `web/src/components/reader/word/WordPopoverShell.tsx` — provider + popover wrapper.
- `web/src/components/reader/word/word-popover.css` — popover styles.

Modified:
- `web/src/components/reader/TokenText.tsx` — reader-mode tap handler.
- `web/src/components/reader/Block.tsx` — build + pass per-token selection.
- `web/src/app/internal/reader/[openiti_id]/page.tsx` — wrap scroll in the shell.
- `web/package.json` / `web/package-lock.json` — add `@floating-ui/react`.

---

## Task 1: Sentence segmentation util

**Files:**
- Create: `web/src/lib/reader/sentences.ts`
- Test: `web/src/lib/reader/sentences.test.ts`

A block's tokens are flat. We group them into sentences by splitting after any token whose visible text ends in Arabic terminal punctuation (`.`, `؟`, `!`, `:`, `؛`). A block with no such punctuation yields a single sentence (the whole block). `buildSelectionMap` returns, for each token id, the word plus the full sentence text and the word's 0-based index within that sentence.

- [ ] **Step 1: Write the failing test**

```ts
// web/src/lib/reader/sentences.test.ts
import { describe, it, expect } from "vitest";
import { segmentSentences, buildSelectionMap } from "./sentences";
import type { Token } from "./types";

const tok = (id: string, text: string): Token => ({ id, text });

describe("segmentSentences", () => {
  it("splits on Arabic full stop, keeping the punctuation token in the sentence", () => {
    const tokens = [tok("a", "بسم"), tok("b", "الله."), tok("c", "الحمد"), tok("d", "لله")];
    const out = segmentSentences(tokens);
    expect(out.map((s) => s.tokenIds)).toEqual([["a", "b"], ["c", "d"]]);
    expect(out[0].text).toBe("بسم الله.");
    expect(out[1].text).toBe("الحمد لله");
  });

  it("splits on question mark and Arabic semicolon", () => {
    const tokens = [tok("a", "كيف"), tok("b", "حالك؟"), tok("c", "بخير؛"), tok("d", "والحمد")];
    expect(segmentSentences(tokens).map((s) => s.tokenIds)).toEqual([
      ["a", "b"],
      ["c"],
      ["d"],
    ]);
  });

  it("returns the whole block as one sentence when no terminal punctuation", () => {
    const tokens = [tok("a", "قال"), tok("b", "رسول"), tok("c", "الله")];
    const out = segmentSentences(tokens);
    expect(out).toHaveLength(1);
    expect(out[0].tokenIds).toEqual(["a", "b", "c"]);
  });

  it("handles empty token list", () => {
    expect(segmentSentences([])).toEqual([]);
  });
});

describe("buildSelectionMap", () => {
  it("maps each token to its sentence text and position within the sentence", () => {
    const tokens = [tok("a", "بسم"), tok("b", "الله."), tok("c", "الحمد"), tok("d", "لله")];
    const map = buildSelectionMap(tokens);
    expect(map.get("a")).toEqual({ word: "بسم", sentence: "بسم الله.", position: 0 });
    expect(map.get("b")).toEqual({ word: "الله.", sentence: "بسم الله.", position: 1 });
    expect(map.get("c")).toEqual({ word: "الحمد", sentence: "الحمد لله", position: 0 });
    expect(map.get("d")).toEqual({ word: "لله", sentence: "الحمد لله", position: 1 });
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npx vitest run src/lib/reader/sentences.test.ts`
Expected: FAIL — cannot find module `./sentences`.

- [ ] **Step 3: Write the implementation**

```ts
// web/src/lib/reader/sentences.ts
import type { Token } from "./types";

export type ReaderSentence = { tokenIds: string[]; text: string };

export type WordSelection = {
  word: string; // token surface form (with tashkeel)
  sentence: string; // full sentence text the word sits in
  position: number; // 0-based index of the word within its sentence
};

// Arabic + ASCII terminal punctuation that ends a sentence.
const TERMINALS = [".", "؟", "!", ":", "؛", "?"];

function endsSentence(text: string): boolean {
  const trimmed = text.trimEnd();
  return TERMINALS.some((p) => trimmed.endsWith(p));
}

export function segmentSentences(tokens: Token[]): ReaderSentence[] {
  const out: ReaderSentence[] = [];
  let current: Token[] = [];
  for (const t of tokens) {
    current.push(t);
    if (endsSentence(t.text)) {
      out.push(toSentence(current));
      current = [];
    }
  }
  if (current.length > 0) out.push(toSentence(current));
  return out;
}

function toSentence(tokens: Token[]): ReaderSentence {
  return {
    tokenIds: tokens.map((t) => t.id),
    text: tokens.map((t) => t.text).join(" "),
  };
}

export function buildSelectionMap(tokens: Token[]): Map<string, WordSelection> {
  const map = new Map<string, WordSelection>();
  for (const sentence of segmentSentences(tokens)) {
    sentence.tokenIds.forEach((id, position) => {
      const word = tokens.find((t) => t.id === id)!.text;
      map.set(id, { word, sentence: sentence.text, position });
    });
  }
  return map;
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npx vitest run src/lib/reader/sentences.test.ts`
Expected: PASS (all cases).

- [ ] **Step 5: Commit**

```bash
git add web/src/lib/reader/sentences.ts web/src/lib/reader/sentences.test.ts
git commit -m "feat(reader): sentence segmentation + word selection map"
```

---

## Task 2: Shared Anthropic fetch helper

**Files:**
- Create: `web/src/lib/agents/anthropic.ts`
- Test: `web/src/lib/agents/anthropic.test.ts`

One server-side helper all three routes share. Reads `ANTHROPIC_API_KEY`, POSTs to the Messages API via `fetch` (Cloudflare-safe), returns the first text block. Throws a typed error when the key is missing or the API call fails.

- [ ] **Step 1: Write the failing test**

```ts
// web/src/lib/agents/anthropic.test.ts
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { callAnthropic, AgentError } from "./anthropic";

describe("callAnthropic", () => {
  const ORIGINAL = process.env.ANTHROPIC_API_KEY;
  beforeEach(() => {
    process.env.ANTHROPIC_API_KEY = "test-key";
  });
  afterEach(() => {
    if (ORIGINAL === undefined) delete process.env.ANTHROPIC_API_KEY;
    else process.env.ANTHROPIC_API_KEY = ORIGINAL;
    vi.restoreAllMocks();
  });

  it("returns the first text block on success", async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ content: [{ type: "text", text: "hello" }] }),
    }) as unknown as typeof fetch;
    const text = await callAnthropic({ system: "sys", messages: [{ role: "user", content: "hi" }], maxTokens: 10 });
    expect(text).toBe("hello");
  });

  it("throws AgentError when the key is missing", async () => {
    delete process.env.ANTHROPIC_API_KEY;
    await expect(
      callAnthropic({ system: "s", messages: [{ role: "user", content: "x" }], maxTokens: 10 }),
    ).rejects.toThrow(AgentError);
  });

  it("throws AgentError when the API responds non-OK", async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 500,
      text: async () => "upstream boom",
    }) as unknown as typeof fetch;
    await expect(
      callAnthropic({ system: "s", messages: [{ role: "user", content: "x" }], maxTokens: 10 }),
    ).rejects.toThrow(AgentError);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npx vitest run src/lib/agents/anthropic.test.ts`
Expected: FAIL — cannot find module `./anthropic`.

- [ ] **Step 3: Write the implementation**

```ts
// web/src/lib/agents/anthropic.ts
// Model matches the current Supabase edge functions; bump deliberately when the
// prompt or model changes.
const MODEL = "claude-sonnet-4-20250514";

export class AgentError extends Error {
  status: number;
  constructor(message: string, status = 500) {
    super(message);
    this.name = "AgentError";
    this.status = status;
  }
}

type Message = { role: "user" | "assistant"; content: string };

export async function callAnthropic(opts: {
  system: string;
  messages: Message[];
  maxTokens: number;
}): Promise<string> {
  const key = process.env.ANTHROPIC_API_KEY;
  if (!key) throw new AgentError("ANTHROPIC_API_KEY is not set", 500);

  const res = await fetch("https://api.anthropic.com/v1/messages", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "x-api-key": key,
      "anthropic-version": "2023-06-01",
    },
    body: JSON.stringify({
      model: MODEL,
      max_tokens: opts.maxTokens,
      system: opts.system,
      messages: opts.messages,
    }),
  });

  if (!res.ok) {
    const detail = await res.text().catch(() => "");
    throw new AgentError(`Anthropic API error ${res.status}: ${detail}`, 502);
  }

  const data = await res.json();
  const text = data?.content?.[0]?.text;
  if (typeof text !== "string") throw new AgentError("Malformed Anthropic response", 502);
  return text;
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npx vitest run src/lib/agents/anthropic.test.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add web/src/lib/agents/anthropic.ts web/src/lib/agents/anthropic.test.ts
git commit -m "feat(agents): shared Anthropic fetch helper"
```

---

## Task 3: Agent types + browser client

**Files:**
- Create: `web/src/lib/agents/types.ts`
- Create: `web/src/lib/agents/client.ts`
- Test: `web/src/lib/agents/client.test.ts`

Shared request/response types and a thin browser client that POSTs to the routes and parses JSON. The client owns all `fetch` so components never touch it.

- [ ] **Step 1: Write the types**

```ts
// web/src/lib/agents/types.ts
export type IrabRequest = { word: string; sentence: string; position: number };
export type IrabResult = {
  pos: string;
  role: string;
  role_ar: string;
  case: string;
  case_ar: string;
  marker: string;
  marker_ar: string;
  why: string;
  meaning: string;
};

export type TranslateRequest = { sentence: string };
export type RelatedWord = { word: string; root: string; meaning: string };
export type TranslateResult = { translation: string; related_words: RelatedWord[] };

export type ChatTurn = { role: "user" | "assistant"; content: string };
export type AskAiRequest = {
  word: string;
  sentence: string;
  question: string;
  history?: ChatTurn[];
};
export type AskAiResult = { response: string };
```

- [ ] **Step 2: Write the failing client test**

```ts
// web/src/lib/agents/client.test.ts
import { describe, it, expect, afterEach, vi } from "vitest";
import { fetchIrab, fetchTranslation, askAi } from "./client";

afterEach(() => vi.restoreAllMocks());

function mockJson(body: unknown, ok = true, status = 200) {
  global.fetch = vi.fn().mockResolvedValue({
    ok,
    status,
    json: async () => body,
    text: async () => JSON.stringify(body),
  }) as unknown as typeof fetch;
}

describe("agent client", () => {
  it("fetchIrab posts to /api/agents/irab and returns parsed result", async () => {
    const result = { pos: "noun", role: "subject", role_ar: "مبتدأ", case: "marfu", case_ar: "مرفوع", marker: "damma", marker_ar: "ضمة", why: "because", meaning: "book" };
    mockJson(result);
    const out = await fetchIrab({ word: "كتاب", sentence: "كتاب جديد", position: 0 });
    expect(out).toEqual(result);
    const call = (global.fetch as unknown as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(call[0]).toBe("/api/agents/irab");
    expect(JSON.parse(call[1].body)).toEqual({ word: "كتاب", sentence: "كتاب جديد", position: 0 });
  });

  it("fetchTranslation returns parsed translation", async () => {
    const result = { translation: "A new book", related_words: [] };
    mockJson(result);
    const out = await fetchTranslation({ sentence: "كتاب جديد" });
    expect(out).toEqual(result);
  });

  it("askAi returns the response text", async () => {
    mockJson({ response: "Here is why..." });
    const out = await askAi({ word: "كتاب", sentence: "كتاب جديد", question: "why?" });
    expect(out.response).toBe("Here is why...");
  });

  it("throws on non-OK response", async () => {
    mockJson({ error: "bad" }, false, 500);
    await expect(fetchTranslation({ sentence: "x" })).rejects.toThrow();
  });
});
```

- [ ] **Step 3: Run test to verify it fails**

Run: `npx vitest run src/lib/agents/client.test.ts`
Expected: FAIL — cannot find module `./client`.

- [ ] **Step 4: Write the client**

```ts
// web/src/lib/agents/client.ts
import type {
  IrabRequest,
  IrabResult,
  TranslateRequest,
  TranslateResult,
  AskAiRequest,
  AskAiResult,
} from "./types";

async function postJson<TReq, TRes>(path: string, body: TReq): Promise<TRes> {
  const res = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    let detail = "";
    try {
      const j = await res.json();
      detail = j?.error ?? "";
    } catch {
      detail = await res.text().catch(() => "");
    }
    throw new Error(detail || `Request to ${path} failed (${res.status})`);
  }
  return (await res.json()) as TRes;
}

export function fetchIrab(input: IrabRequest): Promise<IrabResult> {
  return postJson<IrabRequest, IrabResult>("/api/agents/irab", input);
}

export function fetchTranslation(input: TranslateRequest): Promise<TranslateResult> {
  return postJson<TranslateRequest, TranslateResult>("/api/agents/translate", input);
}

export function askAi(input: AskAiRequest): Promise<AskAiResult> {
  return postJson<AskAiRequest, AskAiResult>("/api/agents/ask-ai", input);
}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `npx vitest run src/lib/agents/client.test.ts`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add web/src/lib/agents/types.ts web/src/lib/agents/client.ts web/src/lib/agents/client.test.ts
git commit -m "feat(agents): typed request/response types + browser client"
```

---

## Task 4: I'rab route handler

**Files:**
- Create: `web/src/app/api/agents/irab/route.ts`
- Test: `web/src/app/api/agents/irab/route.test.ts`

Validates `{ word, sentence, position }`, calls Anthropic with the prompt ported from `supabase/functions/irab/index.ts`, parses the JSON reply, returns it. Maps bad input to 400 and upstream/parse failures to the `AgentError` status.

- [ ] **Step 1: Write the failing test**

```ts
// web/src/app/api/agents/irab/route.test.ts
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { POST } from "./route";

function req(body: unknown) {
  return new Request("http://localhost:3000/api/agents/irab", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

describe("/api/agents/irab", () => {
  const ORIGINAL = process.env.ANTHROPIC_API_KEY;
  beforeEach(() => {
    process.env.ANTHROPIC_API_KEY = "test-key";
  });
  afterEach(() => {
    if (ORIGINAL === undefined) delete process.env.ANTHROPIC_API_KEY;
    else process.env.ANTHROPIC_API_KEY = ORIGINAL;
    vi.restoreAllMocks();
  });

  it("returns the parsed i'rab JSON on success", async () => {
    const result = { pos: "noun", role: "subject", role_ar: "مبتدأ", case: "marfu", case_ar: "مرفوع", marker: "damma", marker_ar: "ضمة", why: "because", meaning: "book" };
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ content: [{ type: "text", text: JSON.stringify(result) }] }),
    }) as unknown as typeof fetch;
    const res = await POST(req({ word: "كتاب", sentence: "كتاب جديد", position: 0 }));
    expect(res.status).toBe(200);
    expect(await res.json()).toEqual(result);
  });

  it("returns 400 when word or sentence is missing", async () => {
    const res = await POST(req({ sentence: "كتاب جديد" }));
    expect(res.status).toBe(400);
  });

  it("returns 502 when the model returns non-JSON", async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ content: [{ type: "text", text: "not json" }] }),
    }) as unknown as typeof fetch;
    const res = await POST(req({ word: "كتاب", sentence: "كتاب جديد", position: 0 }));
    expect(res.status).toBe(502);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npx vitest run src/app/api/agents/irab/route.test.ts`
Expected: FAIL — cannot find module `./route`.

- [ ] **Step 3: Write the route**

```ts
// web/src/app/api/agents/irab/route.ts
import { NextResponse } from "next/server";
import { callAnthropic, AgentError } from "@/lib/agents/anthropic";
import type { IrabRequest } from "@/lib/agents/types";

const SYSTEM = `You are an expert Arabic grammarian (نحوي). You analyze Arabic words in their sentence context and return grammatical analysis (إعراب).

Return a JSON object with these exact fields:
- pos: part of speech in English (noun, verb, particle, adjective, pronoun, etc.)
- role: grammatical role in English (subject, object, predicate, mudaf_ilayh, khabar, mubtada, etc.)
- role_ar: grammatical role in Arabic (مبتدأ، خبر، فاعل، مفعول به، مضاف إليه، etc.)
- case: grammatical case in English (marfu, mansub, majrur, majzum, mabni)
- case_ar: grammatical case in Arabic (مرفوع، منصوب، مجرور، مجزوم، مبني)
- marker: case marker in English (damma, fatha, kasra, sukun, tanween_damma, tanween_fatha, tanween_kasra)
- marker_ar: case marker in Arabic (ضمة، فتحة، كسرة، سكون، تنوين ضم، تنوين فتح، تنوين كسر)
- why: 1-2 sentence explanation mixing Arabic grammar terms with English explanation of WHY this word has this case in this sentence. Reference the specific grammar rule.
- meaning: brief English dictionary meaning of the word

Return ONLY valid JSON, no markdown fences.`;

export async function POST(request: Request): Promise<Response> {
  let body: Partial<IrabRequest>;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "invalid JSON body" }, { status: 400 });
  }

  const { word, sentence, position } = body;
  if (!word || !sentence) {
    return NextResponse.json({ error: "word and sentence are required" }, { status: 400 });
  }

  const userPrompt = `Analyze this word in context:

Word: ${word}
Full sentence: ${sentence}
Position in sentence: ${position ?? 0}

Provide the full إعراب analysis as JSON.`;

  try {
    const text = await callAnthropic({
      system: SYSTEM,
      messages: [{ role: "user", content: userPrompt }],
      maxTokens: 500,
    });
    let result: unknown;
    try {
      result = JSON.parse(text);
    } catch {
      throw new AgentError("Model did not return valid JSON", 502);
    }
    return NextResponse.json(result);
  } catch (e) {
    const status = e instanceof AgentError ? e.status : 500;
    return NextResponse.json({ error: (e as Error).message }, { status });
  }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npx vitest run src/app/api/agents/irab/route.test.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add web/src/app/api/agents/irab/route.ts web/src/app/api/agents/irab/route.test.ts
git commit -m "feat(agents): i'rab route handler"
```

---

## Task 5: Translation route handler

**Files:**
- Create: `web/src/app/api/agents/translate/route.ts`
- Test: `web/src/app/api/agents/translate/route.test.ts`

Validates `{ sentence }`, calls Anthropic with the prompt ported from `supabase/functions/translate/index.ts`, parses and returns the JSON.

- [ ] **Step 1: Write the failing test**

```ts
// web/src/app/api/agents/translate/route.test.ts
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { POST } from "./route";

function req(body: unknown) {
  return new Request("http://localhost:3000/api/agents/translate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

describe("/api/agents/translate", () => {
  const ORIGINAL = process.env.ANTHROPIC_API_KEY;
  beforeEach(() => {
    process.env.ANTHROPIC_API_KEY = "test-key";
  });
  afterEach(() => {
    if (ORIGINAL === undefined) delete process.env.ANTHROPIC_API_KEY;
    else process.env.ANTHROPIC_API_KEY = ORIGINAL;
    vi.restoreAllMocks();
  });

  it("returns the parsed translation JSON on success", async () => {
    const result = { translation: "In the name of God", related_words: [{ word: "رحمن", root: "ر ح م", meaning: "merciful" }] };
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ content: [{ type: "text", text: JSON.stringify(result) }] }),
    }) as unknown as typeof fetch;
    const res = await POST(req({ sentence: "بسم الله" }));
    expect(res.status).toBe(200);
    expect(await res.json()).toEqual(result);
  });

  it("returns 400 when sentence is missing", async () => {
    const res = await POST(req({}));
    expect(res.status).toBe(400);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npx vitest run src/app/api/agents/translate/route.test.ts`
Expected: FAIL — cannot find module `./route`.

- [ ] **Step 3: Write the route**

```ts
// web/src/app/api/agents/translate/route.ts
import { NextResponse } from "next/server";
import { callAnthropic, AgentError } from "@/lib/agents/anthropic";
import type { TranslateRequest } from "@/lib/agents/types";

const SYSTEM = `You are an expert translator of classical Arabic texts. Translate the given Arabic sentence to English, preserving the scholarly register.

Also identify the primary root (جذر) of the most significant content word in the sentence and provide 4-6 related words from the same root.

For Islamic/Arabic terms that are commonly transliterated (e.g., hadith, fiqh, sunnah, i'rab), transliterate them and add a brief parenthetical gloss on first use.

Return a JSON object with:
- translation: the English translation
- related_words: array of objects with { word (Arabic with tashkeel), root (Arabic letters spaced), meaning (English) }

Return ONLY valid JSON, no markdown fences.`;

export async function POST(request: Request): Promise<Response> {
  let body: Partial<TranslateRequest>;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "invalid JSON body" }, { status: 400 });
  }

  const { sentence } = body;
  if (!sentence) {
    return NextResponse.json({ error: "sentence is required" }, { status: 400 });
  }

  try {
    const text = await callAnthropic({
      system: SYSTEM,
      messages: [
        { role: "user", content: `Translate this Arabic sentence and provide related vocabulary:\n\n${sentence}` },
      ],
      maxTokens: 600,
    });
    let result: unknown;
    try {
      result = JSON.parse(text);
    } catch {
      throw new AgentError("Model did not return valid JSON", 502);
    }
    return NextResponse.json(result);
  } catch (e) {
    const status = e instanceof AgentError ? e.status : 500;
    return NextResponse.json({ error: (e as Error).message }, { status });
  }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npx vitest run src/app/api/agents/translate/route.test.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add web/src/app/api/agents/translate/route.ts web/src/app/api/agents/translate/route.test.ts
git commit -m "feat(agents): translation route handler"
```

---

## Task 6: Ask-AI route handler

**Files:**
- Create: `web/src/app/api/agents/ask-ai/route.ts`
- Test: `web/src/app/api/agents/ask-ai/route.test.ts`

Validates `{ word, sentence, question }`, builds messages from optional `history` plus the new question, returns `{ response }` (plain text, not JSON-parsed). Prompt ported from `supabase/functions/ask-ai/index.ts`.

- [ ] **Step 1: Write the failing test**

```ts
// web/src/app/api/agents/ask-ai/route.test.ts
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { POST } from "./route";

function req(body: unknown) {
  return new Request("http://localhost:3000/api/agents/ask-ai", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

describe("/api/agents/ask-ai", () => {
  const ORIGINAL = process.env.ANTHROPIC_API_KEY;
  beforeEach(() => {
    process.env.ANTHROPIC_API_KEY = "test-key";
  });
  afterEach(() => {
    if (ORIGINAL === undefined) delete process.env.ANTHROPIC_API_KEY;
    else process.env.ANTHROPIC_API_KEY = ORIGINAL;
    vi.restoreAllMocks();
  });

  it("returns the assistant text on success", async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ content: [{ type: "text", text: "Because it is the subject." }] }),
    }) as unknown as typeof fetch;
    const res = await POST(req({ word: "كتاب", sentence: "كتاب جديد", question: "why marfu?" }));
    expect(res.status).toBe(200);
    expect(await res.json()).toEqual({ response: "Because it is the subject." });
  });

  it("forwards prior history before the new question", async () => {
    const spy = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ content: [{ type: "text", text: "ok" }] }),
    });
    global.fetch = spy as unknown as typeof fetch;
    await POST(
      req({
        word: "كتاب",
        sentence: "كتاب جديد",
        question: "and the plural?",
        history: [
          { role: "user", content: "why marfu?" },
          { role: "assistant", content: "it is the subject" },
        ],
      }),
    );
    const sent = JSON.parse(spy.mock.calls[0][1].body);
    expect(sent.messages).toEqual([
      { role: "user", content: "why marfu?" },
      { role: "assistant", content: "it is the subject" },
      { role: "user", content: "and the plural?" },
    ]);
  });

  it("returns 400 when required fields are missing", async () => {
    const res = await POST(req({ word: "كتاب", sentence: "كتاب جديد" }));
    expect(res.status).toBe(400);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npx vitest run src/app/api/agents/ask-ai/route.test.ts`
Expected: FAIL — cannot find module `./route`.

- [ ] **Step 3: Write the route**

```ts
// web/src/app/api/agents/ask-ai/route.ts
import { NextResponse } from "next/server";
import { callAnthropic, AgentError } from "@/lib/agents/anthropic";
import type { AskAiRequest, ChatTurn } from "@/lib/agents/types";

export async function POST(request: Request): Promise<Response> {
  let body: Partial<AskAiRequest>;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "invalid JSON body" }, { status: 400 });
  }

  const { word, sentence, question, history } = body;
  if (!word || !sentence || !question) {
    return NextResponse.json(
      { error: "word, sentence, and question are required" },
      { status: 400 },
    );
  }

  const system = `You are a patient, knowledgeable Arabic grammar teacher. A student is reading a classical Arabic text and has a question about a specific word.

Context:
- Word: ${word}
- Sentence: ${sentence}

Answer their question clearly, mixing Arabic grammar terminology with English explanations. Use examples when helpful. Keep answers concise (2-4 paragraphs max). When referencing Arabic grammatical terms, show them in Arabic script.`;

  const messages = [
    ...((history ?? []) as ChatTurn[]).map((m) => ({ role: m.role, content: m.content })),
    { role: "user" as const, content: question },
  ];

  try {
    const text = await callAnthropic({ system, messages, maxTokens: 800 });
    return NextResponse.json({ response: text });
  } catch (e) {
    const status = e instanceof AgentError ? e.status : 500;
    return NextResponse.json({ error: (e as Error).message }, { status });
  }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npx vitest run src/app/api/agents/ask-ai/route.test.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add web/src/app/api/agents/ask-ai/route.ts web/src/app/api/agents/ask-ai/route.test.ts
git commit -m "feat(agents): ask-ai route handler"
```

---

## Task 7: Word popover context provider

**Files:**
- Create: `web/src/components/reader/word/WordPopoverProvider.tsx`

Client context holding the active selection and its anchor element. `useWordPopover()` returns the context or `null` (so `TokenText` in inspector mode, with no provider, is safe). No automated test — vitest runs in a `node` environment with no DOM, so this is verified manually in Task 11.

- [ ] **Step 1: Write the provider**

```tsx
// web/src/components/reader/word/WordPopoverProvider.tsx
"use client";
import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";
import type { WordSelection } from "@/lib/reader/sentences";

type WordPopoverCtx = {
  selection: WordSelection | null;
  anchorEl: HTMLElement | null;
  open: (selection: WordSelection, anchorEl: HTMLElement) => void;
  close: () => void;
};

const Ctx = createContext<WordPopoverCtx | null>(null);

export function WordPopoverProvider({ children }: { children: ReactNode }) {
  const [selection, setSelection] = useState<WordSelection | null>(null);
  const [anchorEl, setAnchorEl] = useState<HTMLElement | null>(null);

  const open = useCallback((sel: WordSelection, el: HTMLElement) => {
    setSelection(sel);
    setAnchorEl(el);
  }, []);
  const close = useCallback(() => {
    setSelection(null);
    setAnchorEl(null);
  }, []);

  const value = useMemo<WordPopoverCtx>(
    () => ({ selection, anchorEl, open, close }),
    [selection, anchorEl, open, close],
  );

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useWordPopover(): WordPopoverCtx | null {
  return useContext(Ctx);
}
```

- [ ] **Step 2: Typecheck**

Run: `npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add web/src/components/reader/word/WordPopoverProvider.tsx
git commit -m "feat(reader): word popover selection context"
```

---

## Task 8: Install Floating UI + popover UI component

**Files:**
- Modify: `web/package.json`, `web/package-lock.json`
- Create: `web/src/components/reader/word/WordPopover.tsx`
- Create: `web/src/components/reader/word/word-popover.css`

The popover anchors to the tapped word, shows the three tabs, and fetches each tab lazily on first view. Each tab tracks its own loading/error/data state. Ask AI keeps a local chat thread.

- [ ] **Step 1: Add the dependency**

Run: `npm install @floating-ui/react`
Expected: `@floating-ui/react` appears in `web/package.json` dependencies; lockfile updates.

- [ ] **Step 2: Write the popover styles**

```css
/* web/src/components/reader/word/word-popover.css */
.word-popover {
  z-index: 50;
  width: 320px;
  max-width: calc(100vw - 24px);
  background: var(--reader-card-bg, #fff);
  color: var(--reader-fg, #18181b);
  border: 1px solid var(--reader-card-border, #e4e4e7);
  border-radius: 10px;
  box-shadow: 0 8px 30px rgba(0, 0, 0, 0.12);
  font-size: 14px;
  overflow: hidden;
}
.word-popover__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 12px;
  border-bottom: 1px solid var(--reader-rule, #e4e4e7);
}
.word-popover__word {
  font-family: Amiri, serif;
  font-size: 20px;
}
.word-popover__close {
  border: 0;
  background: transparent;
  cursor: pointer;
  font-size: 16px;
  line-height: 1;
  opacity: 0.6;
}
.word-popover__tabs {
  display: flex;
  border-bottom: 1px solid var(--reader-rule, #e4e4e7);
}
.word-popover__tab {
  flex: 1;
  padding: 8px;
  border: 0;
  background: transparent;
  cursor: pointer;
  font-size: 12px;
  color: var(--reader-fg-muted, #71717a);
}
.word-popover__tab--active {
  color: var(--reader-fg, #18181b);
  box-shadow: inset 0 -2px 0 var(--reader-accent, #b45309);
}
.word-popover__body {
  padding: 12px;
  max-height: 320px;
  overflow-y: auto;
}
.word-popover__row {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  padding: 3px 0;
}
.word-popover__row dt {
  color: var(--reader-fg-muted, #71717a);
}
.word-popover__error {
  color: #b91c1c;
}
.word-popover__retry {
  margin-top: 8px;
  font-size: 12px;
  text-decoration: underline;
  cursor: pointer;
  background: transparent;
  border: 0;
  color: inherit;
}
.word-popover__chat {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.word-popover__turn--user {
  font-weight: 600;
}
.word-popover__ask {
  display: flex;
  gap: 6px;
  margin-top: 8px;
}
.word-popover__ask input {
  flex: 1;
  padding: 6px 8px;
  border: 1px solid var(--reader-rule, #e4e4e7);
  border-radius: 6px;
}
```

- [ ] **Step 3: Write the popover component**

```tsx
// web/src/components/reader/word/WordPopover.tsx
"use client";
import { useEffect, useRef, useState } from "react";
import {
  useFloating,
  autoUpdate,
  offset,
  flip,
  shift,
  FloatingPortal,
} from "@floating-ui/react";
import { useWordPopover } from "./WordPopoverProvider";
import { fetchIrab, fetchTranslation, askAi } from "@/lib/agents/client";
import type { IrabResult, TranslateResult, ChatTurn } from "@/lib/agents/types";
import "./word-popover.css";

type Tab = "irab" | "translate" | "ask";

export function WordPopover() {
  const popover = useWordPopover();
  const selection = popover?.selection ?? null;
  const anchorEl = popover?.anchorEl ?? null;

  const { refs, floatingStyles } = useFloating({
    placement: "bottom",
    open: !!selection,
    middleware: [offset(6), flip(), shift({ padding: 8 })],
    whileElementsMounted: autoUpdate,
  });

  useEffect(() => {
    refs.setReference(anchorEl);
  }, [anchorEl, refs]);

  const [tab, setTab] = useState<Tab>("irab");
  useEffect(() => {
    setTab("irab"); // reset when a new word is opened
  }, [selection]);

  // Close on Escape + outside click.
  const floatingRef = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    if (!selection) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && popover?.close();
    const onDown = (e: MouseEvent) => {
      const target = e.target as Node;
      if (floatingRef.current?.contains(target)) return;
      if (anchorEl?.contains(target)) return;
      popover?.close();
    };
    document.addEventListener("keydown", onKey);
    document.addEventListener("mousedown", onDown);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("mousedown", onDown);
    };
  }, [selection, anchorEl, popover]);

  if (!popover || !selection) return null;

  return (
    <FloatingPortal>
      <div
        ref={(node) => {
          refs.setFloating(node);
          floatingRef.current = node;
        }}
        style={floatingStyles}
        className="word-popover"
        dir="ltr"
      >
        <div className="word-popover__header">
          <span className="word-popover__word" dir="rtl">{selection.word}</span>
          <button className="word-popover__close" onClick={popover.close} aria-label="Close">×</button>
        </div>
        <div className="word-popover__tabs">
          <TabButton id="irab" tab={tab} setTab={setTab}>I'rab</TabButton>
          <TabButton id="translate" tab={tab} setTab={setTab}>Translation</TabButton>
          <TabButton id="ask" tab={tab} setTab={setTab}>Ask AI</TabButton>
        </div>
        <div className="word-popover__body">
          {tab === "irab" && <IrabTab word={selection.word} sentence={selection.sentence} position={selection.position} />}
          {tab === "translate" && <TranslateTab sentence={selection.sentence} />}
          {tab === "ask" && <AskTab word={selection.word} sentence={selection.sentence} />}
        </div>
      </div>
    </FloatingPortal>
  );
}

function TabButton({ id, tab, setTab, children }: { id: Tab; tab: Tab; setTab: (t: Tab) => void; children: React.ReactNode }) {
  return (
    <button
      className={`word-popover__tab ${tab === id ? "word-popover__tab--active" : ""}`}
      onClick={() => setTab(id)}
    >
      {children}
    </button>
  );
}

// Generic lazy-loader hook keyed on a dependency list.
function useLazy<T>(load: () => Promise<T>, deps: unknown[]) {
  const [state, setState] = useState<{ data?: T; error?: string; loading: boolean }>({ loading: true });
  const [nonce, setNonce] = useState(0);
  useEffect(() => {
    let alive = true;
    setState({ loading: true });
    load()
      .then((data) => alive && setState({ data, loading: false }))
      .catch((e: Error) => alive && setState({ error: e.message, loading: false }));
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, nonce]);
  return { ...state, retry: () => setNonce((n) => n + 1) };
}

function ErrorRow({ error, retry }: { error: string; retry: () => void }) {
  return (
    <div>
      <div className="word-popover__error">{error}</div>
      <button className="word-popover__retry" onClick={retry}>Retry</button>
    </div>
  );
}

function IrabTab({ word, sentence, position }: { word: string; sentence: string; position: number }) {
  const { data, error, loading, retry } = useLazy<IrabResult>(
    () => fetchIrab({ word, sentence, position }),
    [word, sentence, position],
  );
  if (loading) return <div>Analyzing…</div>;
  if (error) return <ErrorRow error={error} retry={retry} />;
  if (!data) return null;
  return (
    <dl>
      <Row k="Part of speech" v={data.pos} />
      <Row k="Role" v={`${data.role_ar} — ${data.role}`} />
      <Row k="Case" v={`${data.case_ar} — ${data.case}`} />
      <Row k="Marker" v={`${data.marker_ar} — ${data.marker}`} />
      <Row k="Meaning" v={data.meaning} />
      <div style={{ marginTop: 8 }}>{data.why}</div>
    </dl>
  );
}

function Row({ k, v }: { k: string; v: string }) {
  return (
    <div className="word-popover__row">
      <dt>{k}</dt>
      <dd dir="auto">{v}</dd>
    </div>
  );
}

function TranslateTab({ sentence }: { sentence: string }) {
  const { data, error, loading, retry } = useLazy<TranslateResult>(
    () => fetchTranslation({ sentence }),
    [sentence],
  );
  if (loading) return <div>Translating…</div>;
  if (error) return <ErrorRow error={error} retry={retry} />;
  if (!data) return null;
  return (
    <div>
      <p>{data.translation}</p>
      {data.related_words?.length > 0 && (
        <dl style={{ marginTop: 8 }}>
          {data.related_words.map((w, i) => (
            <div className="word-popover__row" key={i}>
              <dt dir="rtl">{w.word} <span style={{ opacity: 0.6 }}>({w.root})</span></dt>
              <dd>{w.meaning}</dd>
            </div>
          ))}
        </dl>
      )}
    </div>
  );
}

function AskTab({ word, sentence }: { word: string; sentence: string }) {
  const [thread, setThread] = useState<ChatTurn[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Reset the conversation when the word changes.
  useEffect(() => {
    setThread([]);
    setInput("");
    setError(null);
  }, [word, sentence]);

  const send = async () => {
    const question = input.trim();
    if (!question || busy) return;
    setInput("");
    setError(null);
    setBusy(true);
    const history = thread;
    setThread([...history, { role: "user", content: question }]);
    try {
      const { response } = await askAi({ word, sentence, question, history });
      setThread((t) => [...t, { role: "assistant", content: response }]);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="word-popover__chat">
      {thread.map((turn, i) => (
        <div key={i} className={turn.role === "user" ? "word-popover__turn--user" : undefined} dir="auto">
          {turn.content}
        </div>
      ))}
      {busy && <div>Thinking…</div>}
      {error && <div className="word-popover__error">{error}</div>}
      <div className="word-popover__ask">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && send()}
          placeholder="Ask about this word…"
        />
        <button onClick={send} disabled={busy}>Send</button>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Typecheck**

Run: `npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 5: Commit**

```bash
git add web/package.json web/package-lock.json web/src/components/reader/word/WordPopover.tsx web/src/components/reader/word/word-popover.css
git commit -m "feat(reader): tabbed word-tap popover UI with Floating UI"
```

---

## Task 9: Wire taps through TokenText + Block

**Files:**
- Modify: `web/src/components/reader/TokenText.tsx`
- Modify: `web/src/components/reader/Block.tsx`

`Block` computes a per-token selection map (reader mode only) and passes each token its `WordSelection`. `TokenText` (reader mode) renders an interactive span that opens the popover on click. Inspector mode is untouched.

- [ ] **Step 1: Add the selection prop + tap handler to TokenText**

Edit `web/src/components/reader/TokenText.tsx`. Add the import and prop, and replace the reader-mode branch.

Add near the existing imports:
```tsx
import { useWordPopover } from "./word/WordPopoverProvider";
import type { WordSelection } from "@/lib/reader/sentences";
```

Add to the `Props` type:
```tsx
  selection?: WordSelection;   // reader-mode tap target; absent → not tappable
```

Add `selection` to the destructured props in the function signature, then replace the entire `if (mode === "reader") { ... }` block with:
```tsx
  const popover = useWordPopover();

  if (mode === "reader") {
    const tappable = !!selection && !!popover;
    const className =
      [accentClass, spanClass, recitationClass, tappable ? "reader-word" : null]
        .filter(Boolean)
        .join(" ") || undefined;
    const onClick = tappable
      ? (e: React.MouseEvent<HTMLSpanElement>) => popover!.open(selection!, e.currentTarget)
      : undefined;
    if (className || onClick) {
      return (
        <span className={className} title={title} onClick={onClick}>
          {display}{" "}
        </span>
      );
    }
    return <span>{display} </span>;
  }
```

- [ ] **Step 2: Add the `reader-word` affordance style**

Append to `web/src/components/reader/recite/recite.css` (already imported by `TokenText`):
```css
.reader-word {
  cursor: pointer;
}
.reader-word:hover {
  background: var(--reader-card-bg, rgba(0, 0, 0, 0.05));
  border-radius: 3px;
}
```

- [ ] **Step 3: Build the selection map in Block and pass it down**

Edit `web/src/components/reader/Block.tsx`. Add the import:
```tsx
import { buildSelectionMap } from "@/lib/reader/sentences";
```

In `renderInner`, for the **poetry** branch, build a per-hemistich map and pass selection. Replace each hemistich `verse[n]?.map(...)` TokenText with one that includes `selection`. For `verse[0]`:
```tsx
              {(() => {
                const selMap = mode === "reader" ? buildSelectionMap(verse[0] ?? []) : null;
                return verse[0]?.map((t) => (
                  <TokenText
                    key={t.id}
                    token={t}
                    mode={mode}
                    showTashkeel={showTashkeel}
                    showDiff={showDiff}
                    selection={selMap?.get(t.id)}
                  />
                ));
              })()}
```
Apply the same pattern to `verse[1]` (use `verse[1]`).

In the prose-like branch, replace the `const tokens = block.tokens.map(...)` block with:
```tsx
  const selMap = isReader ? buildSelectionMap(block.tokens) : null;
  const tokens = block.tokens.map((t) => {
    const span = spanIndex.get(t.id);
    return (
      <TokenText
        key={t.id}
        token={t}
        mode={mode}
        showTashkeel={showTashkeel}
        showDiff={showDiff}
        accentClass={isnadAccent && isTransmissionVerb(t) ? "reader-isnad-verb" : undefined}
        spanLabel={span?.label}
        spanRef={span?.ref ?? undefined}
        selection={selMap?.get(t.id)}
      />
    );
  });
```

- [ ] **Step 4: Typecheck + run the existing reader tests**

Run: `npx tsc --noEmit && npx vitest run src/lib/reader`
Expected: no type errors; reader lib tests pass.

- [ ] **Step 5: Commit**

```bash
git add web/src/components/reader/TokenText.tsx web/src/components/reader/Block.tsx web/src/components/reader/recite/recite.css
git commit -m "feat(reader): open word popover on reader-mode tap"
```

---

## Task 10: Mount the provider + popover in the reader page

**Files:**
- Create: `web/src/components/reader/word/WordPopoverShell.tsx`
- Modify: `web/src/app/internal/reader/[openiti_id]/page.tsx`

A small client wrapper provides the context and renders the popover once. The reader page wraps the scroll in it, inside the existing `ReciteShellContent`.

- [ ] **Step 1: Write the shell**

```tsx
// web/src/components/reader/word/WordPopoverShell.tsx
"use client";
import type { ReactNode } from "react";
import { WordPopoverProvider } from "./WordPopoverProvider";
import { WordPopover } from "./WordPopover";

export function WordPopoverShell({ children }: { children: ReactNode }) {
  return (
    <WordPopoverProvider>
      {children}
      <WordPopover />
    </WordPopoverProvider>
  );
}
```

- [ ] **Step 2: Wrap the scroll in the reader page**

Edit `web/src/app/internal/reader/[openiti_id]/page.tsx`. Add the import:
```tsx
import { WordPopoverShell } from "@/components/reader/word/WordPopoverShell";
```

Replace the `<ReciteShellContent>` block with:
```tsx
        <ReciteShellContent>
          <WordPopoverShell>
            <ChapterScroll pages={pages} chapters={chapters} mode="reader" />
          </WordPopoverShell>
        </ReciteShellContent>
```

- [ ] **Step 3: Typecheck + build**

Run: `npx tsc --noEmit && npm run build`
Expected: typecheck clean; Next build succeeds.

- [ ] **Step 4: Commit**

```bash
git add web/src/components/reader/word/WordPopoverShell.tsx web/src/app/internal/reader/[openiti_id]/page.tsx
git commit -m "feat(reader): mount word popover in the internal reader"
```

---

## Task 11: Manual verification via the dev loop

**Files:** none (verification only).

This exercises the real feature in the browser, which the node-environment unit tests cannot. Requires `ANTHROPIC_API_KEY` in `web/.env.local` and ingested data in `web/data` (see `docs/reader/dev-loop.md`).

- [ ] **Step 1: Ensure a book is dumped locally**

If `web/data` has no book, run (from repo root) the ingestion dump per `docs/reader/dev-loop.md`, e.g.:
```bash
python -m ingestion ingest <uri> --dump web/data --dry-run --tashkeel-engine shakkala
```

- [ ] **Step 2: Start the reader**

Run: `cd web && npm run dev`
Open: `http://localhost:3000/internal/library` → open a book into the reader.

- [ ] **Step 3: Verify each tab**

- Tap a word in a **prose** block → popover anchors under the word; I'rab tab loads grammar fields.
- Switch to **Translation** → the sentence (segmented by punctuation) translates; related words list shows.
- Switch to **Ask AI** → ask a question; a turn appears, then the assistant reply; ask a follow-up and confirm history carries.
- Tap a word in a **hadith** (isnad/matn) block and a **poetry** hemistich → popover still works.
- Confirm switching tabs does not re-fetch already-loaded tabs, and a fresh tap resets to the I'rab tab and clears the chat.
- Force an error (temporarily unset `ANTHROPIC_API_KEY` and restart) → tab shows the error with a working Retry.
- Press Escape and click outside → popover closes.
- Switch the reader to **inspector** mode → tapping a word still copies the token id (no popover).

- [ ] **Step 4: Final full verification**

Run from the worktree root:
```bash
./bin/suhuf verify --base origin/main
```
Expected: lint, typecheck, and tests pass for the affected `web` package.

---

## Notes for the implementer

- **Model id**: `MODEL` in `web/src/lib/agents/anthropic.ts` mirrors the current edge functions (`claude-sonnet-4-20250514`). Bump it deliberately if the team standard changes.
- **Gating seam**: Group 0 owns auth/subscription. When it lands, the single check point is the top of each route handler in `web/src/app/api/agents/*`. Nothing in this plan blocks it.
- **Edge functions**: `supabase/functions/{irab,translate,ask-ai}` are intentionally left untouched as the record of the future cached/iOS path.
- **Shipping**: commit per task; when the feature is complete and verified, ship with `./bin/suhuf ship` from the worktree root, then open a PR. Never raw `git push`.
```
