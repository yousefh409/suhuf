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
  const ORIGINAL = process.env.OPENROUTER_API_KEY;
  beforeEach(() => {
    process.env.OPENROUTER_API_KEY = "test-key";
  });
  afterEach(() => {
    if (ORIGINAL === undefined) delete process.env.OPENROUTER_API_KEY;
    else process.env.OPENROUTER_API_KEY = ORIGINAL;
    vi.restoreAllMocks();
  });

  it("returns the parsed translation JSON on success", async () => {
    const result = { translation: "In the name of God", related_words: [{ word: "رحمن", root: "ر ح م", meaning: "merciful" }] };
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ content: [{ type: "text", text: JSON.stringify(result) }] }),
    }) as unknown as typeof fetch;
    const res = await POST(req({ word: "الرحمن", sentence: "بسم الله الرحمن الرحيم" }));
    expect(res.status).toBe(200);
    expect(await res.json()).toEqual(result);
  });

  it("forwards the focus word to the model", async () => {
    const spy = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ content: [{ type: "text", text: JSON.stringify({ translation: "x", related_words: [] }) }] }),
    });
    global.fetch = spy as unknown as typeof fetch;
    await POST(req({ word: "الْعَالَمِينَ", sentence: "الحمد لله رب العالمين" }));
    const sent = JSON.parse(spy.mock.calls[0][1].body);
    const userMsg = sent.messages.find((m: { role: string }) => m.role === "user").content;
    expect(userMsg).toContain("الْعَالَمِينَ");
  });

  it("returns 400 when sentence is missing", async () => {
    const res = await POST(req({ word: "x" }));
    expect(res.status).toBe(400);
  });

  it("returns 400 when word is missing", async () => {
    const res = await POST(req({ sentence: "بسم الله" }));
    expect(res.status).toBe(400);
  });
});
