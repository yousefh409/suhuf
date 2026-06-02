"use client";

import { useEffect, useState } from "react";

import { THEME_KEY as KEY } from "@/lib/reader/storageKeys";
const ORDER = ["paper", "sepia", "night"] as const;
type Theme = (typeof ORDER)[number];

const LABEL: Record<Theme, string> = {
  paper: "Paper",
  sepia: "Sepia",
  night: "Night",
};

const GLYPH: Record<Theme, string> = {
  paper: "☼",
  sepia: "❍",
  night: "☾",
};

export function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>("paper");

  useEffect(() => {
    if (typeof window === "undefined") return;
    const v = window.localStorage.getItem(KEY) as Theme | null;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    if (v && (ORDER as readonly string[]).includes(v)) setTheme(v);
  }, []);

  const cycle = () => {
    const next = ORDER[(ORDER.indexOf(theme) + 1) % ORDER.length];
    setTheme(next);
    window.localStorage.setItem(KEY, next);
    window.dispatchEvent(new StorageEvent("storage", { key: KEY, newValue: next }));
  };

  return (
    <button
      type="button"
      onClick={cycle}
      className="reader-chip text-xs font-mono px-2 py-1 rounded inline-flex items-center gap-1.5"
      title={`Theme: ${LABEL[theme]} (click to cycle)`}
    >
      <span aria-hidden>{GLYPH[theme]}</span>
      <span>{LABEL[theme]}</span>
    </button>
  );
}
