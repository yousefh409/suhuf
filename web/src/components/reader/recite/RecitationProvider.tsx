"use client";
import { createContext, useContext, useMemo, type ReactNode } from "react";
import type { RecitationStatus } from "@/lib/recitation/types";

type Ctx = {
  status: Map<string, RecitationStatus>;
  cursorTokenId: string | null;
};

const RecitationContext = createContext<Ctx>({
  status: new Map(),
  cursorTokenId: null,
});

export function RecitationProvider({
  children,
  status,
  cursorTokenId,
}: {
  children: ReactNode;
  status: Map<string, RecitationStatus>;
  cursorTokenId: string | null;
}) {
  const value = useMemo(() => ({ status, cursorTokenId }), [status, cursorTokenId]);
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
