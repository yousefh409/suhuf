import { NextRequest, NextResponse } from "next/server";

// Simple in-memory rate limiter.
// Not perfect across Cloudflare isolates, but catches basic abuse.
const hits = new Map<string, { count: number; resetAt: number }>();

// Cleanup stale entries every 60s
let lastCleanup = Date.now();
function cleanup() {
  const now = Date.now();
  if (now - lastCleanup < 60_000) return;
  lastCleanup = now;
  for (const [key, val] of hits) {
    if (now > val.resetAt) hits.delete(key);
  }
}

function isRateLimited(
  key: string,
  limit: number,
  windowMs: number
): boolean {
  cleanup();
  const now = Date.now();
  const entry = hits.get(key);

  if (!entry || now > entry.resetAt) {
    hits.set(key, { count: 1, resetAt: now + windowMs });
    return false;
  }

  entry.count++;
  return entry.count > limit;
}

// Per-route limits: [max requests, window in ms]
const LIMITS: Record<string, [number, number]> = {
  "POST:/api/waitlist": [5, 60_000], // 5 signups/min per IP
  "POST:/api/features/vote": [30, 60_000], // 30 votes/min per IP
  "POST:/api/features/suggest": [5, 60_000], // 5 suggestions/min per IP
  "PATCH:/api/waitlist/update": [10, 60_000], // 10 updates/min per IP
  "GET:/api/waitlist/me": [30, 60_000], // 30 reads/min per IP
};

const DEFAULT_LIMIT: [number, number] = [60, 60_000]; // 60 req/min fallback

export function middleware(req: NextRequest) {
  const { pathname } = req.nextUrl;

  // Only rate-limit API routes
  if (!pathname.startsWith("/api/")) return NextResponse.next();

  const ip =
    req.headers.get("cf-connecting-ip") ||
    req.headers.get("x-forwarded-for")?.split(",")[0]?.trim() ||
    "unknown";

  const routeKey = `${req.method}:${pathname}`;
  const [limit, window] = LIMITS[routeKey] || DEFAULT_LIMIT;
  const rateLimitKey = `${ip}:${routeKey}`;

  if (isRateLimited(rateLimitKey, limit, window)) {
    return NextResponse.json(
      { error: "Too many requests. Please try again later." },
      { status: 429 }
    );
  }

  return NextResponse.next();
}

export const config = {
  matcher: "/api/:path*",
};
