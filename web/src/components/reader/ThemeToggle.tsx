"use client";

import { usePreferences } from "@/components/preferences/PreferencesProvider";
import type { Theme } from "@/lib/preferences/types";

const ORDER: Theme[] = ["paper", "sepia", "night"];

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
  const { prefs, setPref } = usePreferences();
  const theme = prefs.theme;

  const cycle = () => {
    setPref("theme", ORDER[(ORDER.indexOf(theme) + 1) % ORDER.length]);
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
