import { createServerClient } from "@supabase/ssr";
import { NextRequest, NextResponse } from "next/server";
import { isProtectedPath, loginRedirectTarget } from "@/lib/proxy-paths";

// ---- In-memory rate limiter (carried over from middleware.ts) ----
// Not perfect across Cloudflare isolates, but catches basic abuse.
const hits = new Map<string, { count: number; resetAt: number }>();

let lastCleanup = Date.now();
function cleanup() {
  const now = Date.now();
  if (now - lastCleanup < 60_000) return;
  lastCleanup = now;
  for (const [key, val] of hits) {
    if (now > val.resetAt) hits.delete(key);
  }
}

function isRateLimited(key: string, limit: number, windowMs: number): boolean {
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

const LIMITS: Record<string, [number, number]> = {
  "POST:/api/waitlist": [5, 60_000],
  "POST:/api/features/vote": [30, 60_000],
  "POST:/api/features/suggest": [5, 60_000],
  "PATCH:/api/waitlist/update": [10, 60_000],
  "GET:/api/waitlist/me": [30, 60_000],
};

const DEFAULT_LIMIT: [number, number] = [60, 60_000];

function rateLimitApi(req: NextRequest): NextResponse | null {
  const ip =
    req.headers.get("cf-connecting-ip") ||
    req.headers.get("x-forwarded-for")?.split(",")[0]?.trim() ||
    "unknown";
  const routeKey = `${req.method}:${req.nextUrl.pathname}`;
  const [limit, window] = LIMITS[routeKey] || DEFAULT_LIMIT;
  if (isRateLimited(`${ip}:${routeKey}`, limit, window)) {
    return NextResponse.json(
      { error: "Too many requests. Please try again later." },
      { status: 429 },
    );
  }
  return null;
}

export async function proxy(req: NextRequest) {
  const { pathname } = req.nextUrl;

  // API routes: rate-limit only (no auth gating).
  if (pathname.startsWith("/api/")) {
    return rateLimitApi(req) ?? NextResponse.next();
  }

  // App routes: refresh the Supabase session and gate protected paths.
  let response = NextResponse.next({ request: req });

  const supabase = createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    {
      cookies: {
        getAll() {
          return req.cookies.getAll();
        },
        setAll(cookiesToSet) {
          cookiesToSet.forEach(({ name, value }) => req.cookies.set(name, value));
          response = NextResponse.next({ request: req });
          cookiesToSet.forEach(({ name, value, options }) =>
            response.cookies.set(name, value, options),
          );
        },
      },
    },
  );

  // Do not insert code between createServerClient and getUser().
  // On a refresh/network failure, treat the request as logged-out rather than
  // 500-ing every page.
  const result = await supabase.auth.getUser().catch(() => null);
  const user = result?.data.user ?? null;

  if (!user && isProtectedPath(pathname)) {
    const url = new URL(
      loginRedirectTarget(pathname, req.nextUrl.search),
      req.url,
    );
    return NextResponse.redirect(url);
  }

  return response;
}

export const config = {
  matcher: [
    // Run on everything except Next internals and static image assets.
    "/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp)$).*)",
  ],
};
