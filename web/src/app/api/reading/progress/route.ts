import { NextResponse } from "next/server";
import { createClient } from "@/lib/supabase/server";

export const dynamic = "force-dynamic";

type Body = {
  openitiId?: string;
  pageNumber?: number;
  volume?: number;
  pagesRead?: number;
  durationSeconds?: number;
};

/**
 * Records reading activity for the signed-in user. The reader is local-file
 * driven, so the client only knows the book's openiti_id + the visible page
 * number; we resolve the Supabase book/page UUIDs here.
 *
 * - 401 when logged out (public readers no-op on the client).
 * - Upserts the reading position (current page) and the library row
 *   (status in_progress, last_opened_at = now), so opening a book shelves it.
 * - Inserts a reading_sessions row when there's elapsed time or pages read,
 *   which backs the dashboard stats.
 * - If the book isn't ingested into Supabase, returns { recorded: false } —
 *   nothing to attach activity to, but not an error.
 */
export async function POST(request: Request): Promise<Response> {
  const sb = await createClient();
  const {
    data: { user },
  } = await sb.auth.getUser();
  if (!user) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  let body: Body;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "invalid JSON body" }, { status: 400 });
  }

  const openitiId = body.openitiId?.trim();
  if (!openitiId) {
    return NextResponse.json({ error: "openitiId is required" }, { status: 400 });
  }

  const pageNumber =
    typeof body.pageNumber === "number" ? body.pageNumber : undefined;
  const volume = typeof body.volume === "number" ? body.volume : 1;
  const pagesRead = Math.max(0, Math.trunc(body.pagesRead ?? 0));
  const durationSeconds = Math.max(0, Math.trunc(body.durationSeconds ?? 0));

  // Resolve the Supabase book by its openiti_id. Local-only books won't exist.
  const { data: book, error: bookErr } = await sb
    .from("books")
    .select("id")
    .eq("openiti_id", openitiId)
    .maybeSingle();

  if (bookErr) {
    console.error("[reading] book lookup error:", bookErr.message);
    return NextResponse.json({ error: "lookup failed" }, { status: 500 });
  }
  if (!book) {
    return NextResponse.json({ recorded: false });
  }

  const bookId = book.id as string;
  const now = new Date().toISOString();

  // Resolve and upsert the reading position when a page is known.
  if (pageNumber !== undefined) {
    const { data: page, error: pageErr } = await sb
      .from("pages")
      .select("id")
      .eq("book_id", bookId)
      .eq("volume", volume)
      .eq("page_number", pageNumber)
      .maybeSingle();

    if (pageErr) {
      console.error("[reading] page lookup error:", pageErr.message);
    } else if (page) {
      const { error: posErr } = await sb.from("user_reading_positions").upsert(
        {
          user_id: user.id,
          book_id: bookId,
          page_id: page.id as string,
          updated_at: now,
        },
        { onConflict: "user_id,book_id" },
      );
      if (posErr) console.error("[reading] position upsert error:", posErr.message);
    }
  }

  // Shelve the book (opening it adds it to the library) and bump last_opened_at.
  const { error: libErr } = await sb.from("user_library").upsert(
    {
      user_id: user.id,
      book_id: bookId,
      status: "in_progress",
      last_opened_at: now,
      updated_at: now,
    },
    { onConflict: "user_id,book_id" },
  );
  if (libErr) console.error("[reading] library upsert error:", libErr.message);

  // Record the activity slice that backs the stats.
  if (durationSeconds > 0 || pagesRead > 0) {
    const { error: sessErr } = await sb.from("reading_sessions").insert({
      user_id: user.id,
      book_id: bookId,
      pages_read: pagesRead,
      duration_seconds: durationSeconds,
    });
    if (sessErr) console.error("[reading] session insert error:", sessErr.message);
  }

  return NextResponse.json({ recorded: true });
}
