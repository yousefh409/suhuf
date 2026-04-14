import { NextRequest, NextResponse } from "next/server";
import { getSupabase } from "@/lib/supabase";

export async function POST(req: NextRequest) {
  try {
    const supabase = getSupabase();
    const { feature_id, waitlist_id } = await req.json();

    if (!feature_id || !waitlist_id) {
      return NextResponse.json(
        { error: "feature_id and waitlist_id required" },
        { status: 400 }
      );
    }

    // Verify user exists
    const { data: user } = await supabase
      .from("waitlist_users")
      .select("id")
      .eq("id", waitlist_id)
      .single();

    if (!user) {
      return NextResponse.json(
        { error: "Join the waitlist first" },
        { status: 403 }
      );
    }

    // Upsert vote (idempotent)
    const { error } = await supabase.from("feature_votes").upsert(
      { waitlist_user_id: waitlist_id, feature_id },
      { onConflict: "waitlist_user_id,feature_id" }
    );

    if (error) throw error;

    return NextResponse.json({ ok: true });
  } catch (err) {
    console.error("Vote error:", err);
    return NextResponse.json(
      { error: "Something went wrong" },
      { status: 500 }
    );
  }
}
