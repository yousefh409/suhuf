// web/src/lib/recitation/types.ts
// Types mirroring the recitation server's WS protocol and the public surface
// of the useRecitation hook. See:
// docs/superpowers/specs/2026-04-30-recitation-reader-integration-design.md

export type RecitationStatus =
  | "correct"
  | "wrong_word"
  | "i3rab"
  | "tashkeel"
  | "skipped"
  | "current";

export type ConnectionState =
  | "idle"
  | "connecting"
  | "connected"
  | "reconnecting"
  | "error";

// ── Server → client messages ──

export type ScoreWord = {
  idx: number;
  word: string;
  status: "correct" | "error";
  error_type:
    | "wrong"
    | "skipped"
    | "i3rab"
    | "tashkeel"
    | null;
  error_detail: string | null;
  expected_word?: string | null;
  greedy?: string;
  debug?: Record<string, unknown>;
};

export type ScoreEvent = {
  words: ScoreWord[];
  matched_phrase_idx: number;
  final?: boolean;
};

export type ServerErrorEvent = {
  type: "error";
  code: "auth_failed" | "origin_denied" | "session_too_long" | string;
  message: string;
};

export type ServerPing = { type: "ping" };

// ── Client → server messages ──

export type InitMessage = {
  passage: { id: string; phrases: string[] };
  lookbehind_count?: number;
  auth_token?: string;
  debug?: boolean;
};

export type AppendMessage = {
  type: "append_phrases";
  phrases: string[];
};

// ── Public hook surface ──

export type Block = import("@/lib/reader/types").Block;
