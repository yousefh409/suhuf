"use client";

import {
  createContext,
  useCallback,
  useContext,
  useState,
  type ReactNode,
} from "react";
import type { Preferences } from "@/lib/preferences/types";
import { preferencesToAttributes } from "@/lib/preferences/attributes";
import { writePreferencesCookie } from "@/lib/preferences/cookie";

interface PreferencesContextValue {
  prefs: Preferences;
  setPref: <K extends keyof Preferences>(key: K, value: Preferences[K]) => void;
}

const PreferencesContext = createContext<PreferencesContextValue | null>(null);

// Reflect the render-affecting prefs onto <html> so the change applies instantly
// (the server already stamped these for the initial paint).
function applyAttributes(prefs: Preferences) {
  if (typeof document === "undefined") return;
  const attrs = preferencesToAttributes(prefs);
  for (const [name, value] of Object.entries(attrs)) {
    document.documentElement.setAttribute(name, value);
  }
}

interface PreferencesProviderProps {
  initial: Preferences;
  children: ReactNode;
}

// Preferences are stored locally only: a long-lived cookie is the single source
// of truth. The root layout reads it server-side to stamp <html> before first
// paint (no flash); this provider rewrites it on every change.
export function PreferencesProvider({ initial, children }: PreferencesProviderProps) {
  const [prefs, setPrefs] = useState<Preferences>(initial);

  const setPref = useCallback(
    <K extends keyof Preferences>(key: K, value: Preferences[K]) => {
      setPrefs((prev) => {
        const next = { ...prev, [key]: value };
        writePreferencesCookie(next);
        applyAttributes(next);
        return next;
      });
    },
    [],
  );

  return (
    <PreferencesContext.Provider value={{ prefs, setPref }}>
      {children}
    </PreferencesContext.Provider>
  );
}

export function usePreferences(): PreferencesContextValue {
  const ctx = useContext(PreferencesContext);
  if (!ctx) {
    throw new Error("usePreferences must be used within a PreferencesProvider");
  }
  return ctx;
}
