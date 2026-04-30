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
