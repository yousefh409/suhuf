// Dev-only: seed dashboard activity for the test user against the hosted
// Supabase DB so /dashboard shows non-zero stats, continue-reading, and a
// shelved library entry. NOT a migration — safe to re-run (idempotent upserts;
// reading_sessions are cleared for the user first so stats stay deterministic).
//
// Run with the service-role key in env:
//   node --env-file=.env.local scripts/seed-dashboard.mjs
//
// Requires: NEXT_PUBLIC_SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY.

import { createClient } from "@supabase/supabase-js";

const URL = process.env.NEXT_PUBLIC_SUPABASE_URL;
const SERVICE_KEY =
  process.env.SUPABASE_SERVICE_ROLE_KEY || process.env.SUPABASE_SERVICE_KEY;

const TEST_USER_ID = "b1992f15-7535-4eea-ab17-b1a86fb09797";

if (!URL || !SERVICE_KEY) {
  console.error(
    "Missing env: need NEXT_PUBLIC_SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY.\n" +
      "Run: node --env-file=.env.local scripts/seed-dashboard.mjs",
  );
  process.exit(1);
}

const sb = createClient(URL, SERVICE_KEY, {
  auth: { autoRefreshToken: false, persistSession: false },
});

function isoDaysAgo(days, hour = 9) {
  const d = new Date();
  d.setUTCDate(d.getUTCDate() - days);
  d.setUTCHours(hour, 0, 0, 0);
  return d.toISOString();
}

async function main() {
  // Pick the first ingested book.
  const { data: book, error: bookErr } = await sb
    .from("books")
    .select("id, openiti_id, total_pages")
    .order("created_at", { ascending: true })
    .limit(1)
    .maybeSingle();
  if (bookErr) throw bookErr;
  if (!book) {
    console.error("No books in the DB — ingest one before seeding.");
    process.exit(1);
  }
  console.log(`Seeding against book ${book.openiti_id} (${book.id}).`);

  // Shelve it for the test user, in progress.
  const now = new Date().toISOString();
  const { error: libErr } = await sb.from("user_library").upsert(
    {
      user_id: TEST_USER_ID,
      book_id: book.id,
      status: "in_progress",
      last_opened_at: now,
      updated_at: now,
    },
    { onConflict: "user_id,book_id" },
  );
  if (libErr) throw libErr;

  // Set a reading position ~25% through (or first page if tiny).
  const targetPage = Math.max(1, Math.round((book.total_pages ?? 4) * 0.25));
  const { data: page, error: pageErr } = await sb
    .from("pages")
    .select("id, page_number")
    .eq("book_id", book.id)
    .lte("page_number", targetPage)
    .order("page_number", { ascending: false })
    .limit(1)
    .maybeSingle();
  if (pageErr) throw pageErr;
  if (page) {
    const { error: posErr } = await sb.from("user_reading_positions").upsert(
      {
        user_id: TEST_USER_ID,
        book_id: book.id,
        page_id: page.id,
        updated_at: now,
      },
      { onConflict: "user_id,book_id" },
    );
    if (posErr) throw posErr;
    console.log(`Position set at page ${page.page_number}.`);
  } else {
    console.warn("No pages found for the book; skipped reading position.");
  }

  // Reset this user's sessions so stats are deterministic, then seed a streak.
  const { error: delErr } = await sb
    .from("reading_sessions")
    .delete()
    .eq("user_id", TEST_USER_ID);
  if (delErr) throw delErr;

  // A 4-day streak ending today, with reading time + some words learned.
  const sessions = [
    { occurred_at: isoDaysAgo(0, 8), pages_read: 6, duration_seconds: 1500, words_learned: 4 },
    { occurred_at: isoDaysAgo(0, 12), pages_read: 4, duration_seconds: 900, words_learned: 3 },
    { occurred_at: isoDaysAgo(1, 9), pages_read: 8, duration_seconds: 2100, words_learned: 5 },
    { occurred_at: isoDaysAgo(2, 9), pages_read: 5, duration_seconds: 1200, words_learned: 2 },
    { occurred_at: isoDaysAgo(3, 9), pages_read: 7, duration_seconds: 1800, words_learned: 6 },
  ].map((s) => ({ ...s, user_id: TEST_USER_ID, book_id: book.id }));

  const { error: sessErr } = await sb.from("reading_sessions").insert(sessions);
  if (sessErr) throw sessErr;

  // Re-probe.
  const { count } = await sb
    .from("reading_sessions")
    .select("*", { count: "exact", head: true })
    .eq("user_id", TEST_USER_ID);
  console.log(`Seeded ${sessions.length} sessions (user now has ${count}).`);
  console.log("Done. Load /dashboard as the test user to verify.");
}

main().catch((err) => {
  console.error("Seed failed:", err.message ?? err);
  process.exit(1);
});
