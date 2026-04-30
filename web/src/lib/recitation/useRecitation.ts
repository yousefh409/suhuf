// web/src/lib/recitation/useRecitation.ts
"use client";
import { useCallback, useEffect, useReducer, useRef, useState } from "react";
import type { Block } from "@/lib/reader/types";
import { buildPassage } from "./passage";
import { RecitationClient } from "./client";
import { recitationReducer, initialRecitationState } from "./state";
import type { ScoreEvent } from "./types";

const APPEND_BATCH = 10;
const APPEND_WATERMARK = 0.7;

type Opts = {
  chapterBlocks: Block[];
  wsUrl: string;
  tokenProvider?: () => Promise<string>;
};

export function useRecitation({ chapterBlocks, wsUrl, tokenProvider }: Opts) {
  const [state, dispatch] = useReducer(recitationReducer, initialRecitationState);
  const clientRef = useRef<RecitationClient | null>(null);
  const captureRef = useRef<{ stop: () => Promise<void> } | null>(null);
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const allUnitsRef = useRef<{ phrases: string[]; tokenIds: string[][] } | null>(null);
  const sentPhraseCountRef = useRef(0);
  const [anchorBlockKey, setAnchorBlockKey] = useState<string | null>(null);

  const start = useCallback(
    async (anchor: string) => {
      setAnchorBlockKey(anchor);
      const initial = buildPassage({
        chapterBlocks,
        anchorBlockKey: anchor,
        lookbehindCount: 2,
        lookaheadPhraseCount: APPEND_BATCH * 2,
      });
      if (!initial) {
        dispatch({ type: "connection", state: "error" });
        return;
      }
      // Pre-compute the full chapter's units so we can append later
      const fullPassage = buildPassage({
        chapterBlocks,
        anchorBlockKey: anchor,
        lookbehindCount: 0,
        lookaheadPhraseCount: 1_000_000,
      });
      if (!fullPassage) return;

      dispatch({ type: "passage_loaded", wordIndexToTokenId: initial.wordIndexToTokenId });
      sentPhraseCountRef.current = initial.phrases.length;

      const client = new RecitationClient({ url: wsUrl, tokenProvider });
      clientRef.current = client;
      client.onScore((ev: ScoreEvent) => {
        dispatch({ type: "score", event: ev });
        // Auto-append: when matched_phrase_idx crosses the watermark, send next batch
        if (
          ev.matched_phrase_idx >=
          Math.floor(sentPhraseCountRef.current * APPEND_WATERMARK)
        ) {
          const nextSlice = fullPassage.phrases.slice(
            sentPhraseCountRef.current,
            sentPhraseCountRef.current + APPEND_BATCH,
          );
          if (nextSlice.length > 0) {
            client.appendPhrases(nextSlice);
            // Extend wordIndexToTokenId
            // eslint-disable-next-line @typescript-eslint/no-unused-vars
            const startTok = fullPassage.wordIndexToTokenId.indexOf(
              fullPassage.phrases.slice(0, sentPhraseCountRef.current).join(" ").split(" ").length === 0
                ? fullPassage.wordIndexToTokenId[0]
                : fullPassage.wordIndexToTokenId[
                    fullPassage.phrases.slice(0, sentPhraseCountRef.current).flatMap((p) => p.split(" ")).length
                  ],
            );
            const newWordCount = nextSlice.flatMap((p) => p.split(" ")).length;
            const newTokenIds = fullPassage.wordIndexToTokenId.slice(
              state.wordIndexToTokenId.length,
              state.wordIndexToTokenId.length + newWordCount,
            );
            dispatch({
              type: "passage_loaded",
              wordIndexToTokenId: [...state.wordIndexToTokenId, ...newTokenIds],
            });
            sentPhraseCountRef.current += nextSlice.length;
          }
        }
      });
      client.onError((e) => dispatch({ type: "error", event: e }));
      client.onState((s) => dispatch({ type: "connection", state: s }));

      await client.connect({
        passage: { id: `chapter-${anchor}`, phrases: initial.phrases },
        lookbehind_count: initial.startCursor,
      });

      // Start audio capture and forward to client
      const { startCapture } = await import("./audio");
      const cap = await startCapture();
      captureRef.current = cap;
      (async () => {
        for await (const chunk of cap.chunks) {
          client.sendAudio(chunk);
        }
      })();
    },
    [chapterBlocks, wsUrl, tokenProvider, state.wordIndexToTokenId],
  );

  const stop = useCallback(async () => {
    try { clientRef.current?.done(); } catch { /* noop */ }
    try { await captureRef.current?.stop(); } catch { /* noop */ }
    clientRef.current?.close();
    clientRef.current = null;
    captureRef.current = null;
    dispatch({ type: "reset" });
  }, []);

  useEffect(() => {
    return () => {
      stop().catch(() => undefined);
    };
  }, [stop]);

  return {
    start,
    stop,
    status: state.status,
    cursorTokenId: state.cursorTokenId,
    connectionState: state.connectionState,
    error: state.error,
    anchorBlockKey,
  };
}
