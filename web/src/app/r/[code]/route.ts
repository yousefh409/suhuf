import { NextRequest, NextResponse } from "next/server";
import { isValidReferralCode } from "@/lib/referral";

export async function GET(
  req: NextRequest,
  { params }: { params: Promise<{ code: string }> }
) {
  const { code } = await params;

  const baseUrl = req.nextUrl.origin;

  if (!isValidReferralCode(code)) {
    return NextResponse.redirect(baseUrl);
  }

  const response = NextResponse.redirect(baseUrl);
  response.cookies.set("suhuf_ref", code, {
    maxAge: 60 * 60 * 24 * 30, // 30 days
    path: "/",
    httpOnly: false,
  });
  return response;
}
