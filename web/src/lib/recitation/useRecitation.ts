// web/src/lib/recitation/useRecitation.ts
"use client";
import { useCallback, useEffect, useReducer, useRef, useState } from "react";
import type { Block } from "@/lib/reader/types";
import { buildPassage } from "./passage";
import { RecitationClient } from "./client";
import { recitationReducer, initialRecitationState, recitePhase } from "./state";
import type { ScoreEvent } from "./types";
import type { AudioCapture } from "./audio";

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
  const tokenIdsRef = useRef<string[]>([]);
  const sentPhraseCountRef = useRef(0);

  useEffect(() => {
    tokenIdsRef.current = state.wordIndexToTokenId;
  }, [state.wordIndexToTokenId]);
  const [anchorBlockKey, setAnchorBlockKey] = useState<string | null>(null);

  // Start mic capture and forward chunks to the (already-connected) client.
  // Reused by both start() and resume(). Returns false if the mic is denied.
  const beginCapture = useCallback(
    async (client: RecitationClient): Promise<boolean> => {
      const { startCapture } = await import("./audio");
      let cap: AudioCapture;
      try {
        cap = await startCapture();
      } catch {
        dispatch({
          type: "error",
          event: { type: "error", code: "mic_denied", message: "Microphone access denied." },
        });
        return false;
      }
      captureRef.current = cap;
      (async () => {
        for await (const chunk of cap.chunks) {
          client.sendAudio(chunk);
        }
      })();
      return true;
    },
    [],
  );

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
            const currentTokenIds = tokenIdsRef.current;
            const newWordCount = nextSlice.flatMap((p) => p.split(" ")).length;
            const newTokenIds = fullPassage.wordIndexToTokenId.slice(
              currentTokenIds.length,
              currentTokenIds.length + newWordCount,
            );
            dispatch({
              type: "extend_passage",
              wordIndexToTokenId: [...currentTokenIds, ...newTokenIds],
            });
            sentPhraseCountRef.current += nextSlice.length;
          }
        }
      });
      client.onError((e) => dispatch({ type: "error", event: e }));
      client.onState((s) => dispatch({ type: "connection", state: s }));

      try {
        await client.connect({
          passage: { id: `chapter-${anchor}`, phrases: initial.phrases },
          lookbehind_count: initial.startCursor,
        });
      } catch {
        dispatch({
          type: "error",
          event: {
            type: "error",
            code: "connect_failed",
            message: "Couldn't reach the recitation server.",
          },
        });
        client.close();
        return;
      }

      // Start audio capture and forward to client
      const ok = await beginCapture(client);
      if (!ok) {
        client.close();
        clientRef.current = null;
      }
    },
    [chapterBlocks, wsUrl, tokenProvider, beginCapture],
  );

  // Pause: stop the mic but keep the socket + server-side position alive and
  // leave the highlights on screen. The client auto-pongs the server's pings,
  // so the session survives until resume() or end().
  const pause = useCallback(async () => {
    try { await captureRef.current?.stop(); } catch { /* noop */ }
    captureRef.current = null;
    dispatch({ type: "pause" });
  }, []);

  // Resume: restart the mic on the same socket and continue the session. If the
  // socket dropped during a long pause, fall back to a fresh start at the anchor.
  const resume = useCallback(async () => {
    const client = clientRef.current;
    if (client && client.getState() === "connected") {
      dispatch({ type: "resume" });
      await beginCapture(client);
      return;
    }
    if (anchorBlockKey) await start(anchorBlockKey);
  }, [anchorBlockKey, beginCapture, start]);

  // End: full teardown — finalise scoring, close the socket, clear highlights.
  const end = useCallback(async () => {
    try { clientRef.current?.done(); } catch { /* noop */ }
    try { await captureRef.current?.stop(); } catch { /* noop */ }
    clientRef.current?.close();
    clientRef.current = null;
    captureRef.current = null;
    dispatch({ type: "reset" });
  }, []);

  useEffect(() => {
    return () => {
      end().catch(() => undefined);
    };
  }, [end]);

  return {
    start,
    pause,
    resume,
    end,
    status: state.status,
    cursorTokenId: state.cursorTokenId,
    connectionState: state.connectionState,
    phase: recitePhase(state.connectionState, state.paused),
    paused: state.paused,
    error: state.error,
    anchorBlockKey,
  };
}
