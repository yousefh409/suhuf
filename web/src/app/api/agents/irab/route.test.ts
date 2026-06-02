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
