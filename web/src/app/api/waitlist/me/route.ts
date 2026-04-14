import { NextRequest, NextResponse } from "next/server";
import { getSupabase } from "@/lib/supabase";

export async function GET(req: NextRequest) {
  const waitlistId = req.cookies.get("suhuf_waitlist")?.value;

  if (!waitlistId) {
    return NextResponse.json({ user: null }, { status: 401 });
  }

  const supabase = getSupabase();
  const { data: user } = await supabase
    .from("waitlist_users")
    .select("id, position, referral_code, interest_areas, feature_request")
    .eq("id", waitlistId)
    .single();

  if (!user) {
    // Cookie references a deleted/invalid user — clear it
    const res = NextResponse.json({ user: null }, { status: 401 });
    res.cookies.delete("suhuf_waitlist");
    return res;
  }

  return NextResponse.json({ user });
}
