"use client";
/**
 * ReciteShell — owns the recitation session and publishes it via context.
 *
 * Exports:
 *  1. `ReciteShell`            — root; owns `useRecitation` + hide-text state.
 *  2. `ReciteShellToggle`      — main button: Recite → Pause ⇄ Resume.
 *  3. `ReciteShellEnd`         — end button (icon): full teardown + reset.
 *  4. `ReciteShellHideToggle`  — hide-text toggle (reveal words as recited).
 *  5. `ReciteShellContent`     — wraps children in RecitationProvider.
 *
 * Usage in the chapter page (server component):
 *   <ReciteShell chapterBlocks={chapterBlocks} recitable={recitable}>
 *     <header>… <ReciteShellToggle /> <ReciteShellEnd /> … <ReciteShellHideToggle /> …</header>
 *     <ReciteShellContent><ChapterScroll … /></ReciteShellContent>
 *   </ReciteShell>
 */
import {
  createContext,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { useRecitation } from "@/lib/recitation/useRecitation";
import { fetchAuthToken } from "@/lib/recitation/token";
import type { Block } from "@/lib/reader/types";
import type { RecitationStatus } from "@/lib/recitation/types";
import type { RecitePhase } from "@/lib/recitation/state";
import { RecitationProvider } from "./RecitationProvider";
import { ReciteToggle } from "./ReciteToggle";
import { ReciteEndButton } from "./ReciteEndButton";
import { HideTextToggle } from "./HideTextToggle";

const WS_URL =
  process.env.NEXT_PUBLIC_RECITATION_WS_URL ?? "ws://localhost:8000/ws/score";

// ── Shared context ──────────────────────────────────────────────────────────

type ShellCtx = {
  status: Map<string, RecitationStatus>;
  cursorTokenId: string | null;
  isActive: boolean;
  phase: RecitePhase;
  error?: string;
  recitable: boolean;
  hideText: boolean;
  start: (anchorBlockKey: string) => void;
  pause: () => void;
  resume: () => void;
  end: () => void;
  setHideText: (v: boolean) => void;
};

const ReciteShellContext = createContext<ShellCtx | null>(null);

function useShellCtx(): ShellCtx {
  const ctx = useContext(ReciteShellContext);
  if (!ctx) throw new Error("ReciteShell* used outside <ReciteShell>");
  return ctx;
}

// ── Root ────────────────────────────────────────────────────────────────────

export function ReciteShell({
  chapterBlocks,
  recitable,
  children,
}: {
  chapterBlocks: Block[];
  recitable: boolean;
  children: ReactNode;
}) {
  const r = useRecitation({
    chapterBlocks,
    wsUrl: WS_URL,
    tokenProvider: WS_URL.startsWith("wss") ? fetchAuthToken : undefined,
  });
  const [hideText, setHideText] = useState(false);
  // Active = a session exists (listening OR paused). The socket stays
  // "connected" through a pause, so this stays true across pause/resume.
  const isActive = r.connectionState !== "idle" && r.connectionState !== "error";

  const value = useMemo<ShellCtx>(
    () => ({
      status: r.status,
      cursorTokenId: r.cursorTokenId,
      isActive,
      phase: r.phase,
      error: r.error,
      recitable,
      hideText,
      start: r.start,
      pause: r.pause,
      resume: r.resume,
      end: r.end,
      setHideText,
    }),
    [
      r.status, r.cursorTokenId, isActive, r.phase, r.error, recitable,
      hideText, r.start, r.pause, r.resume, r.end,
    ],
  );

  return (
    <ReciteShellContext.Provider value={value}>
      {children}
    </ReciteShellContext.Provider>
  );
}

// ── Main button — Recite → Pause ⇄ Resume ─────────────────────────────────────

export function ReciteShellToggle() {
  const { recitable, phase, error, start, pause, resume, end } = useShellCtx();
  return (
    <ReciteToggle
      disabled={!recitable}
      phase={phase}
      error={error}
      onStart={start}
      onPause={pause}
      onResume={resume}
      onEnd={end}
    />
  );
}

// ── End button — full teardown + reset (only while a session is active) ───────

export function ReciteShellEnd() {
  const { isActive, end } = useShellCtx();
  if (!isActive) return null;
  return <ReciteEndButton onEnd={end} />;
}

// ── Hide-text toggle — reveal words as you recite ─────────────────────────────

export function ReciteShellHideToggle() {
  const { isActive, hideText, setHideText } = useShellCtx();
  // Hide-text only does anything mid-session, so the control only appears while
  // reciting (listening or paused) — like the End button.
  if (!isActive) return null;
  return (
    <HideTextToggle
      hidden={hideText}
      onToggle={() => setHideText(!hideText)}
    />
  );
}

// ── Content wrapper — place around the scroll ────────────────────────────────

export function ReciteShellContent({ children }: { children: ReactNode }) {
  const { status, cursorTokenId, hideText, isActive } = useShellCtx();
  return (
    <RecitationProvider
      status={status}
      cursorTokenId={cursorTokenId}
      hideText={hideText}
      sessionActive={isActive}
    >
      {children}
    </RecitationProvider>
  );
}
