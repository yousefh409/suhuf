"use client";
import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";
import type { WordSelection } from "@/lib/reader/sentences";

type WordPopoverCtx = {
  selection: WordSelection | null;
  anchorEl: HTMLElement | null;
  open: (selection: WordSelection, anchorEl: HTMLElement) => void;
  close: () => void;
};

const Ctx = createContext<WordPopoverCtx | null>(null);

export function WordPopoverProvider({ children }: { children: ReactNode }) {
  const [selection, setSelection] = useState<WordSelection | null>(null);
  const [anchorEl, setAnchorEl] = useState<HTMLElement | null>(null);

  const open = useCallback((sel: WordSelection, el: HTMLElement) => {
    setSelection(sel);
    setAnchorEl(el);
  }, []);
  const close = useCallback(() => {
    setSelection(null);
    setAnchorEl(null);
  }, []);

  const value = useMemo<WordPopoverCtx>(
    () => ({ selection, anchorEl, open, close }),
    [selection, anchorEl, open, close],
  );

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useWordPopover(): WordPopoverCtx | null {
  return useContext(Ctx);
}
