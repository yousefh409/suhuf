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
