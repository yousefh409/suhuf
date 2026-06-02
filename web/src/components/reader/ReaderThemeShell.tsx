"use client";

import { useEffect, useState, type ReactNode } from "react";

import { THEME_KEY as KEY } from "@/lib/reader/storageKeys";
const VALID = ["paper", "sepia", "night"] as const;
export type ReaderTheme = (typeof VALID)[number];

function isTheme(v: string | null): v is ReaderTheme {
  return v !== null && (VALID as readonly string[]).includes(v);
}

export function ReaderThemeShell({ children }: { children: ReactNode }) {
  const [theme, setTheme] = useState<ReaderTheme>("paper");

  useEffect(() => {
    if (typeof window === "undefined") return;
    const v = window.localStorage.getItem(KEY);
    // eslint-disable-next-line react-hooks/set-state-in-effect
    if (isTheme(v)) setTheme(v);
    const onStorage = (e: StorageEvent) => {
      if (e.key === KEY && isTheme(e.newValue)) setTheme(e.newValue);
    };
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, []);

  return (
    <div data-reader-theme={theme} className="reader-shell">
      {children}
    </div>
  );
}
