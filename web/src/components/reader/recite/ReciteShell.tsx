"use client";
/**
 * ReciteShell — Option B split design.
 *
 * This module exports three things:
 *  1. `ReciteShell`       — root client component that owns `useRecitation`
 *                           and publishes state via ReciteShellContext.
 *  2. `ReciteShellToggle` — reads context; drop anywhere (e.g. header).
 *  3. `ReciteShellContent`— wraps children in RecitationProvider.
 *
 * Usage in the chapter page (server component):
 *   <ReciteShell chapterBlocks={chapterBlocks} recitable={recitable}>
 *     <header>
 *       ...
 *       <ReciteShellToggle />
 *     </header>
 *     <ReciteShellContent>
 *       <ChapterScroll ... />
 *     </ReciteShellContent>
 *   </ReciteShell>
 *
 * Because Next.js allows server components to pass ReactNode children
 * through client boundaries, this pattern keeps the page as a server
 * component while placing the toggle in the header and the provider
 * around the scroll.
 */
import { createContext, useContext, useMemo, type ReactNode } from "react";
import { useRecitation } from "@/lib/recitation/useRecitation";
import { fetchAuthToken } from "@/lib/recitation/token";
import type { Block } from "@/lib/reader/types";
import type { RecitationStatus } from "@/lib/recitation/types";
import { RecitationProvider } from "./RecitationProvider";
import { ReciteToggle } from "./ReciteToggle";

const WS_URL =
  process.env.NEXT_PUBLIC_RECITATION_WS_URL ?? "ws://localhost:8000/ws/score";

// ── Shared context ──────────────────────────────────────────────────────────

type ShellCtx = {
  status: Map<string, RecitationStatus>;
  cursorTokenId: string | null;
  isActive: boolean;
  recitable: boolean;
  start: (anchorBlockKey: string) => void;
  stop: () => void;
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
  const isActive = r.connectionState !== "idle" && r.connectionState !== "error";

  const value = useMemo<ShellCtx>(
    () => ({
      status: r.status,
      cursorTokenId: r.cursorTokenId,
      isActive,
      recitable,
      start: r.start,
      stop: r.stop,
    }),
    [r.status, r.cursorTokenId, isActive, recitable, r.start, r.stop],
  );

  return (
    <ReciteShellContext.Provider value={value}>
      {children}
    </ReciteShellContext.Provider>
  );
}

// ── Toggle — place in the header ─────────────────────────────────────────────

export function ReciteShellToggle() {
  const { recitable, isActive, start, stop } = useShellCtx();
  return (
    <ReciteToggle
      disabled={!recitable}
      isActive={isActive}
      onStart={start}
      onStop={stop}
    />
  );
}

// ── Content wrapper — place around the scroll ────────────────────────────────

export function ReciteShellContent({ children }: { children: ReactNode }) {
  const { status, cursorTokenId } = useShellCtx();
  return (
    <RecitationProvider status={status} cursorTokenId={cursorTokenId}>
      {children}
    </RecitationProvider>
  );
}
