"use client";
import { createContext, useContext, useMemo, type ReactNode } from "react";
import type { RecitationStatus } from "@/lib/recitation/types";
import { isConcealed } from "@/lib/recitation/state";

type Ctx = {
  status: Map<string, RecitationStatus>;
  cursorTokenId: string | null;
  hideText: boolean;
  sessionActive: boolean;
};

const RecitationContext = createContext<Ctx>({
  status: new Map(),
  cursorTokenId: null,
  hideText: false,
  sessionActive: false,
});

export function RecitationProvider({
  children,
  status,
  cursorTokenId,
  hideText,
  sessionActive,
}: {
  children: ReactNode;
  status: Map<string, RecitationStatus>;
  cursorTokenId: string | null;
  hideText: boolean;
  sessionActive: boolean;
}) {
  const value = useMemo(
    () => ({ status, cursorTokenId, hideText, sessionActive }),
    [status, cursorTokenId, hideText, sessionActive],
  );
  return (
    <RecitationContext.Provider value={value}>
      {children}
    </RecitationContext.Provider>
  );
}

export function useRecitationStatus(tokenId: string): RecitationStatus | null {
  const ctx = useContext(RecitationContext);
  if (ctx.cursorTokenId === tokenId) return "current";
  return ctx.status.get(tokenId) ?? null;
}

/** True when this token should be blurred (hide-text mode, not yet recited). */
export function useRecitationConcealed(tokenId: string): boolean {
  const ctx = useContext(RecitationContext);
  const status =
    ctx.cursorTokenId === tokenId ? "current" : ctx.status.get(tokenId) ?? null;
  return isConcealed(ctx.hideText, ctx.sessionActive, status);
}
