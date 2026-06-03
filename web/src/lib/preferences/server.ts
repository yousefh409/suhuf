// Server-only module. Do NOT import this from client components.
// It uses next/headers (via createClient) which is unavailable on the client.
import { createClient } from "@/lib/supabase/server";
import { coercePreferences } from "./serialize";
import type { Preferences } from "./types";

/**
 * Read the signed-in user's preferences from the database.
 * Returns null when the user is not signed in or has no row yet.
 */
export async function readUserPreferences(): Promise<Preferences | null> {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  if (!user) return null;

  const { data, error } = await supabase
    .from("user_preferences")
    .select("theme, text_size, arabic_font, line_spacing, tashkeel")
    .eq("user_id", user.id)
    .maybeSingle();

  if (error) {
    console.error("[preferences] read error:", error.message);
    return null;
  }

  if (!data) return null;

  // Map snake_case DB columns → camelCase Preferences keys, then coerce.
  return coercePreferences({
    theme: data.theme,
    textSize: data.text_size,
    arabicFont: data.arabic_font,
    lineSpacing: data.line_spacing,
    tashkeel: data.tashkeel,
  });
}

/**
 * Upsert the signed-in user's preferences into the database.
 * No-op when the user is not signed in.
 */
export async function upsertUserPreferences(prefs: Preferences): Promise<void> {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  if (!user) return;

  const { error } = await supabase.from("user_preferences").upsert(
    {
      user_id: user.id,
      theme: prefs.theme,
      text_size: prefs.textSize,
      arabic_font: prefs.arabicFont,
      line_spacing: prefs.lineSpacing,
      tashkeel: prefs.tashkeel,
      updated_at: new Date().toISOString(),
    },
    { onConflict: "user_id" },
  );

  if (error) {
    console.error("[preferences] upsert error:", error.message);
  }
}
