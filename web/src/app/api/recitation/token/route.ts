import { NextRequest, NextResponse } from "next/server";
import { createHmac } from "node:crypto";

export const runtime = "nodejs";

export async function POST(req: NextRequest) {
  const secret = process.env.RECITATION_AUTH_SECRET;
  if (!secret) {
    return NextResponse.json({ error: "auth disabled" }, { status: 404 });
  }
  const ttl = parseInt(process.env.RECITATION_TOKEN_TTL_SEC ?? "300", 10);
  const origin = req.nextUrl.origin;
  const exp = Math.floor(Date.now() / 1000) + ttl;
  const payload = JSON.stringify({ origin, exp });
  const p64 = Buffer.from(payload).toString("base64url");
  const sig = createHmac("sha256", secret).update(p64).digest("hex");
  return NextResponse.json({ token: `${p64}.${sig}` });
}
