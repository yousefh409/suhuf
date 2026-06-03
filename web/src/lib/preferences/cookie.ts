import {
  parsePreferences,
  serializePreferences,
} from "./serialize";
import type { Preferences } from "./types";

// Name of the cookie holding the serialized preferences JSON. This is the
// render source of truth: the root layout reads it server-side to stamp <html>
// before first paint (no theme flash), and the client provider rewrites it on
// every change. Client-safe module — must NOT import next/headers.
export const PREFERENCES_COOKIE = "suhuf.prefs";

// One year. Preferences are not sensitive, so a long-lived cookie is fine.
export const PREFERENCES_COOKIE_MAX_AGE = 60 * 60 * 24 * 365;

// Cookie values are percent-encoded on write (JSON contains characters like `,`
// and `"` that are not safe raw in a cookie). Decoding a value with no percent
// escapes is a no-op, so this is safe whether or not the platform pre-decodes.
function decodeCookieValue(raw: string | undefined): string | undefined {
  if (raw === undefined) return undefined;
  try {
    return decodeURIComponent(raw);
  } catch {
    return raw;
  }
}

// Parse a raw cookie value (as read on the server or client) into Preferences,
// filling defaults for anything missing or invalid.
export function parsePreferencesCookie(raw: string | undefined): Preferences {
  return parsePreferences(decodeCookieValue(raw));
}

// Write the preferences to the cookie from the browser. No-op on the server.
export function writePreferencesCookie(prefs: Preferences): void {
  if (typeof document === "undefined") return;
  const value = encodeURIComponent(serializePreferences(prefs));
  document.cookie = `${PREFERENCES_COOKIE}=${value}; path=/; max-age=${PREFERENCES_COOKIE_MAX_AGE}; samesite=lax`;
}
