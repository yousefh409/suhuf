// web/src/lib/recitation/state.test.ts
import { describe, it, expect } from "vitest";
import {
  recitationReducer,
  initialRecitationState,
  recitePhase,
  isConcealed,
} from "./state";
import type { ScoreEvent } from "./types";

function filledState() {
  return recitationReducer(
    { ...initialRecitationState, wordIndexToTokenId: ["t0", "t1", "t2"] },
    {
      type: "score",
      event: {
        words: [{ idx: 0, word: "a", status: "correct", error_type: null, error_detail: null }],
        matched_phrase_idx: 0,
      },
    },
  );
}

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

  it("pause keeps status, cursor and connection — only flips paused", () => {
    const filled = { ...filledState(), connectionState: "connected" as const };
    expect(filled.paused).toBe(false);
    const paused = recitationReducer(filled, { type: "pause" });
    expect(paused.paused).toBe(true);
    expect(paused.status.get("t0")).toBe("correct"); // feedback survives
    expect(paused.cursorTokenId).toBe(filled.cursorTokenId);
    expect(paused.connectionState).toBe("connected"); // socket stays "up"
  });

  it("resume clears paused, keeps feedback", () => {
    const paused = recitationReducer(
      { ...filledState(), connectionState: "connected" as const },
      { type: "pause" },
    );
    const resumed = recitationReducer(paused, { type: "resume" });
    expect(resumed.paused).toBe(false);
    expect(resumed.status.get("t0")).toBe("correct");
  });

  it("reset clears the paused flag too", () => {
    const paused = recitationReducer(filledState(), { type: "pause" });
    const next = recitationReducer(paused, { type: "reset" });
    expect(next.paused).toBe(false);
    expect(next.status.size).toBe(0);
  });

  describe("recitePhase", () => {
    it("maps connection + paused to a UI phase", () => {
      expect(recitePhase("idle", false)).toBe("idle");
      expect(recitePhase("connecting", false)).toBe("connecting");
      expect(recitePhase("connected", false)).toBe("listening");
      expect(recitePhase("connected", true)).toBe("paused");
      expect(recitePhase("error", false)).toBe("error");
    });
    it("error wins over paused", () => {
      expect(recitePhase("error", true)).toBe("error");
    });
  });

  describe("isConcealed (hide-text reveal-as-read)", () => {
    it("conceals unread words only while hide-text is on AND a session is active", () => {
      expect(isConcealed(true, true, null)).toBe(true); // not yet reached
      expect(isConcealed(true, true, "current")).toBe(true); // the word being read
    });
    it("reveals a word once it has been scored", () => {
      expect(isConcealed(true, true, "correct")).toBe(false);
      expect(isConcealed(true, true, "i3rab")).toBe(false);
      expect(isConcealed(true, true, "wrong_word")).toBe(false);
    });
    it("never conceals when hide-text is off or no active session", () => {
      expect(isConcealed(false, true, null)).toBe(false);
      expect(isConcealed(true, false, null)).toBe(false);
    });
  });

  it("extend_passage extends token ids without clearing status", () => {
    // Score a word to populate status
    const withScore = recitationReducer(
      { ...initialRecitationState, wordIndexToTokenId: ["t0", "t1"] },
      {
        type: "score",
        event: {
          words: [{ idx: 0, word: "a", status: "correct", error_type: null, error_detail: null }],
          matched_phrase_idx: 0,
        },
      },
    );
    expect(withScore.status.get("t0")).toBe("correct");

    // Now extend the passage
    const extended = recitationReducer(withScore, {
      type: "extend_passage",
      wordIndexToTokenId: ["t0", "t1", "t2", "t3"],
    });

    // Tokens are extended
    expect(extended.wordIndexToTokenId).toEqual(["t0", "t1", "t2", "t3"]);
    // Status is preserved — score highlights not wiped
    expect(extended.status.get("t0")).toBe("correct");
    // Cursor is preserved
    expect(extended.cursorTokenId).toBe(withScore.cursorTokenId);
  });
});
