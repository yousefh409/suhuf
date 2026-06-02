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
