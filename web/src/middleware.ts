import { createServerClient } from "@supabase/ssr";
import { NextRequest, NextResponse } from "next/server";
import { isProtectedPath, loginRedirectTarget } from "@/lib/proxy-paths";

// NOTE: This stays as `middleware.ts` (not Next 16's `proxy.ts`) on purpose.
// `proxy.ts` defaults to the Node.js runtime, which @opennextjs/cloudflare does
// not support ("Node.js middleware is not currently supported"). The
// `middleware` convention defaults to the Edge runtime that the Cloudflare
// adapter requires.

// ---- In-memory rate limiter ----
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

export async function middleware(req: NextRequest) {
  const { pathname } = req.nextUrl;

  // API routes: rate-limit only (no auth gating).
  if (pathname.startsWith("/api/")) {
    return rateLimitApi(req) ?? NextResponse.next();
  }

  // App routes: refresh the Supabase session and gate protected paths.
  const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const supabaseKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

  // If Supabase isn't configured in this environment, do NOT take the whole
  // site down. Skip gating (fail open) so public pages still render. Set
  // NEXT_PUBLIC_SUPABASE_URL / NEXT_PUBLIC_SUPABASE_ANON_KEY to enable the gate.
  if (!supabaseUrl || !supabaseKey) {
    return NextResponse.next();
  }

  let response = NextResponse.next({ request: req });

  const supabase = createServerClient(
    supabaseUrl,
    supabaseKey,
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
