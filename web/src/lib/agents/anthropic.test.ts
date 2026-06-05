import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { callAnthropic, AgentError } from "./anthropic";

describe("callAnthropic", () => {
  const ORIGINAL = process.env.OPENROUTER_API_KEY;
  beforeEach(() => {
    process.env.OPENROUTER_API_KEY = "test-key";
  });
  afterEach(() => {
    if (ORIGINAL === undefined) delete process.env.OPENROUTER_API_KEY;
    else process.env.OPENROUTER_API_KEY = ORIGINAL;
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
    delete process.env.OPENROUTER_API_KEY;
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
