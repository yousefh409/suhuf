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
  // Paused = mic stopped but the socket + server-side position are kept alive
  // and the highlights stay on screen. Distinct from "idle" (fully torn down).
  paused: boolean;
  error?: string;
};

export const initialRecitationState: RecitationState = {
  connectionState: "idle",
  status: new Map(),
  cursorTokenId: null,
  matchedPhraseIdx: null,
  wordIndexToTokenId: [],
  paused: false,
};

export type Action =
  | { type: "score"; event: ScoreEvent }
  | { type: "connection"; state: ConnectionState }
  | { type: "error"; event: ServerErrorEvent }
  | { type: "passage_loaded"; wordIndexToTokenId: string[] }
  | { type: "extend_passage"; wordIndexToTokenId: string[] }
  | { type: "pause" }
  | { type: "resume" }
  | { type: "reset" };

/** UI phase for the recite controls, derived from the connection + paused flag. */
export type RecitePhase = "idle" | "connecting" | "listening" | "paused" | "error";

export function recitePhase(
  connectionState: ConnectionState,
  paused: boolean,
): RecitePhase {
  if (connectionState === "error") return "error";
  if (connectionState === "connecting" || connectionState === "reconnecting") {
    return "connecting";
  }
  if (paused) return "paused";
  if (connectionState === "connected") return "listening";
  return "idle";
}

/**
 * Hide-text "reveal as read": a word is concealed (blurred) only while the
 * hide-text toggle is on AND a session is active AND the word hasn't been
 * scored yet (no status, or it's the current word being read). Once the engine
 * scores it, the blur clears and its colour shows.
 */
export function isConcealed(
  hideText: boolean,
  sessionActive: boolean,
  status: RecitationStatus | null,
): boolean {
  if (!hideText || !sessionActive) return false;
  return status === null || status === "current";
}

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
    case "extend_passage":
      return { ...s, wordIndexToTokenId: a.wordIndexToTokenId };
    case "pause":
      return { ...s, paused: true };
    case "resume":
      return { ...s, paused: false };
    case "connection":
      return { ...s, connectionState: a.state };
    case "error":
      return { ...s, error: a.event.message, connectionState: "error" };
    case "reset":
      return { ...initialRecitationState };
  }
}
