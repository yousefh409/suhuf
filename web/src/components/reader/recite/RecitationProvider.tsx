"use client";
import { createContext, useContext, type ReactNode } from "react";
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
  return (
    <RecitationContext.Provider value={{ status, cursorTokenId }}>
      {children}
    </RecitationContext.Provider>
  );
}

export function useRecitationStatus(tokenId: string): RecitationStatus | null {
  const ctx = useContext(RecitationContext);
  if (ctx.cursorTokenId === tokenId) return "current";
  return ctx.status.get(tokenId) ?? null;
}
