"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import type { Preferences } from "@/lib/preferences/types";
import { preferencesToAttributes } from "@/lib/preferences/attributes";
import { writePreferencesCookie } from "@/lib/preferences/cookie";
import { mergePreferences } from "@/lib/preferences/merge";

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

export function PreferencesProvider({ initial, children }: PreferencesProviderProps) {
  const [prefs, setPrefs] = useState<Preferences>(initial);
  const signedInRef = useRef(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // On mount: fetch DB prefs and reconcile with the cookie (initial).
  useEffect(() => {
    let cancelled = false;

    fetch("/api/preferences")
      .then(async (res) => {
        if (cancelled) return;

        if (res.status === 401) {
          signedInRef.current = false;
          return;
        }

        if (!res.ok) return;

        signedInRef.current = true;

        const { prefs: dbPrefs } = (await res.json()) as { prefs: Preferences | null };
        if (cancelled) return;

        const { effective, seedDb } = mergePreferences(initial, dbPrefs ?? null);

        if (seedDb) {
          // No DB row yet — push the cookie preferences to seed the DB.
          fetch("/api/preferences", {
            method: "PUT",
            headers: { "content-type": "application/json" },
            body: JSON.stringify(effective),
          }).catch(() => {});
        } else {
          // DB wins: apply the authoritative preferences from the server.
          setPrefs(effective);
          writePreferencesCookie(effective);
          applyAttributes(effective);
        }
      })
      .catch(() => {});

    return () => {
      cancelled = true;
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const setPref = useCallback(
    <K extends keyof Preferences>(key: K, value: Preferences[K]) => {
      setPrefs((prev) => {
        const next = { ...prev, [key]: value };
        writePreferencesCookie(next);
        applyAttributes(next);

        // Write-through to the DB for signed-in users, debounced.
        if (signedInRef.current) {
          if (debounceRef.current !== null) clearTimeout(debounceRef.current);
          debounceRef.current = setTimeout(() => {
            fetch("/api/preferences", {
              method: "PUT",
              headers: { "content-type": "application/json" },
              body: JSON.stringify(next),
            }).catch(() => {});
          }, 400);
        }

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
