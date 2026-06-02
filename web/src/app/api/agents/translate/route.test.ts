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
