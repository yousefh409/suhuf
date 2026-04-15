import { createClient, SupabaseClient } from "@supabase/supabase-js";

export function getSupabase(): SupabaseClient {
  const url = process.env.SUPABASE_URL;
  const key = process.env.SUPABASE_SERVICE_ROLE_KEY;

  if (!url || !key) {
    throw new Error(
      `Missing Supabase env vars: SUPABASE_URL=${url ? "set" : "MISSING"}, SUPABASE_SERVICE_ROLE_KEY=${key ? "set" : "MISSING"}`
    );
  }

  return createClient(url, key);
}
