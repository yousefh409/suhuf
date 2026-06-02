"use client";
import type { ReactNode } from "react";
import { WordPopoverProvider } from "./WordPopoverProvider";
import { WordPopover } from "./WordPopover";

export function WordPopoverShell({ children }: { children: ReactNode }) {
  return (
    <WordPopoverProvider>
      {children}
      <WordPopover />
    </WordPopoverProvider>
  );
}
