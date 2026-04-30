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
  error?: string;
};

export const initialRecitationState: RecitationState = {
  connectionState: "idle",
  status: new Map(),
  cursorTokenId: null,
  matchedPhraseIdx: null,
  wordIndexToTokenId: [],
};

export type Action =
  | { type: "score"; event: ScoreEvent }
  | { type: "connection"; state: ConnectionState }
  | { type: "error"; event: ServerErrorEvent }
  | { type: "passage_loaded"; wordIndexToTokenId: string[] }
  | { type: "reset" };

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
    case "connection":
      return { ...s, connectionState: a.state };
    case "error":
      return { ...s, error: a.event.message, connectionState: "error" };
    case "reset":
      return { ...initialRecitationState };
  }
}
