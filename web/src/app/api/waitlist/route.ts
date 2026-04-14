import { NextRequest, NextResponse } from "next/server";
import { getSupabase } from "@/lib/supabase";
import { generateReferralCode, isValidReferralCode } from "@/lib/referral";
import { sendWelcomeEmail } from "@/lib/email";

export async function POST(req: NextRequest) {
  try {
    const supabase = getSupabase();
    const body = await req.json();
    const { email, signup_source, referral_code: referrerCode } = body;

    if (!email || typeof email !== "string") {
      return NextResponse.json({ error: "Email required" }, { status: 400 });
    }

    const normalizedEmail = email.trim().toLowerCase();

    // Check if already exists
    const { data: existing } = await supabase
      .from("waitlist_users")
      .select("id, position, referral_code")
      .eq("email", normalizedEmail)
      .single();

    if (existing) {
      const res = NextResponse.json({
        id: existing.id,
        position: existing.position,
        referral_code: existing.referral_code,
        is_existing: true,
      });
      res.cookies.set("suhuf_waitlist", existing.id, {
        httpOnly: true,
        secure: process.env.NODE_ENV === "production",
        sameSite: "lax",
        maxAge: 60 * 60 * 24 * 365,
        path: "/",
      });
      return res;
    }

    // Resolve referrer
    let referredBy: string | null = null;
    if (referrerCode && isValidReferralCode(referrerCode)) {
      const { data: referrer } = await supabase
        .from("waitlist_users")
        .select("id")
        .eq("referral_code", referrerCode)
        .single();
      if (referrer) referredBy = referrer.id;
    }

    // Get next position
    const { count } = await supabase
      .from("waitlist_users")
      .select("*", { count: "exact", head: true });
    const position = (count || 0) + 1;

    const newReferralCode = generateReferralCode();

    // Insert
    const { data: user, error } = await supabase
      .from("waitlist_users")
      .insert({
        email: normalizedEmail,
        referral_code: newReferralCode,
        referred_by: referredBy,
        position,
        signup_source: signup_source || "hero",
        utm_source: body.utm_source || null,
        utm_medium: body.utm_medium || null,
        utm_campaign: body.utm_campaign || null,
      })
      .select("id, position, referral_code")
      .single();

    if (error) {
      if (error.code === "23505") {
        // Race condition: email was inserted between check and insert
        const { data: raceUser } = await supabase
          .from("waitlist_users")
          .select("id, position, referral_code")
          .eq("email", normalizedEmail)
          .single();
        const raceRes = NextResponse.json({ ...raceUser, is_existing: true });
        if (raceUser?.id) {
          raceRes.cookies.set("suhuf_waitlist", raceUser.id, {
            httpOnly: true,
            secure: process.env.NODE_ENV === "production",
            sameSite: "lax",
            maxAge: 60 * 60 * 24 * 365,
            path: "/",
          });
        }
        return raceRes;
      }
      throw error;
    }

    // Increment referrer's count
    if (referredBy) {
      await supabase.rpc("increment_referral_count", {
        user_id: referredBy,
      });
    }

    // Send welcome email (fire-and-forget)
    sendWelcomeEmail({
      email: normalizedEmail,
      position: user.position,
      referralCode: user.referral_code,
    }).catch(() => {});

    const res = NextResponse.json({
      id: user.id,
      position: user.position,
      referral_code: user.referral_code,
      is_existing: false,
    });
    res.cookies.set("suhuf_waitlist", user.id, {
      httpOnly: true,
      secure: process.env.NODE_ENV === "production",
      sameSite: "lax",
      maxAge: 60 * 60 * 24 * 365,
      path: "/",
    });
    return res;
  } catch (err) {
    console.error("Waitlist error:", err);
    return NextResponse.json(
      { error: "Something went wrong" },
      { status: 500 }
    );
  }
}
