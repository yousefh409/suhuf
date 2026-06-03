"use client";

import { usePreferences } from "@/components/preferences/PreferencesProvider";

/**
 * Reader header toggle for diacritics (tashkeel). Kept as a top-level control
 * rather than buried in the Display panel, since readers flip it often. Drives
 * the saved preference, so the reader updates live.
 */
export function TashkeelButton() {
  const { prefs, setPref } = usePreferences();
  const on = prefs.tashkeel;

  return (
    <button
      type="button"
      onClick={() => setPref("tashkeel", !on)}
      className={`reader-textbtn${on ? " is-on" : ""}`}
      title={`Diacritics (tashkeel): ${on ? "on" : "off"}`}
      aria-pressed={on}
    >
      <span
        aria-hidden
        style={{ fontFamily: "var(--font-arabic), serif", fontSize: 17, lineHeight: 1 }}
      >
        نَ
      </span>
      <span>Tashkeel</span>
    </button>
  );
}
