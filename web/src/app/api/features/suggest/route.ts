import { NextRequest, NextResponse } from "next/server";
import { getSupabase } from "@/lib/supabase";

export async function POST(req: NextRequest) {
  try {
    const supabase = getSupabase();
    const { suggestion, waitlist_id } = await req.json();

    if (!suggestion || typeof suggestion !== "string") {
      return NextResponse.json(
        { error: "Suggestion required" },
        { status: 400 }
      );
    }

    if (!waitlist_id) {
      return NextResponse.json(
        { error: "Join the waitlist first" },
        { status: 403 }
      );
    }

    const { error } = await supabase.from("feature_suggestions").insert({
      waitlist_user_id: waitlist_id,
      suggestion: suggestion.slice(0, 500),
    });

    if (error) throw error;

    return NextResponse.json({ ok: true });
  } catch (err) {
    console.error("Suggestion error:", err);
    return NextResponse.json(
      { error: "Something went wrong" },
      { status: 500 }
    );
  }
}
