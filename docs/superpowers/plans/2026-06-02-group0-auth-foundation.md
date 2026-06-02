# Group 0 — Auth + Reader Gating Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Supabase email/password auth (login + signup), move the reader surfaces out of `/internal` to the site root, and gate them behind login.

**Architecture:** `@supabase/ssr` cookie-based sessions. A Next 16 `proxy.ts` (the renamed `middleware`) refreshes the session on every app request and redirects unauthenticated users away from protected paths. An `(app)` route-group layout re-verifies the user server-side (defense in depth, no content flash). The reader keeps reading local JSON files — its data layer is untouched.

**Tech Stack:** Next.js 16.2.3 (App Router, `src/app`, non-standard build — `middleware` is renamed to `proxy`), `@supabase/ssr`, `@supabase/supabase-js`, Vitest (node env).

---

## Context the engineer needs

- **Next 16 renamed `middleware` → `proxy`.** The file is `src/proxy.ts` and the exported function is `proxy`. The old `src/middleware.ts` is deprecated. Reference: `web/node_modules/next/dist/docs/01-app/03-api-reference/03-file-conventions/proxy.md`.
- **Supabase clients:** the existing `web/src/lib/supabase.ts` is a **service-role** server client used for data ops — leave it alone. We add two new anon-key clients under `web/src/lib/supabase/`.
- **Env vars:** the browser/proxy clients need `NEXT_PUBLIC_SUPABASE_URL` and `NEXT_PUBLIC_SUPABASE_ANON_KEY` (the anon/publishable key, safe to expose). These are different from the existing `SUPABASE_URL` / `SUPABASE_SERVICE_ROLE_KEY`.
- **Reader data layer stays local.** Do NOT touch `web/src/lib/reader/queries.ts`. Pages keep `export const dynamic = "force-dynamic"`.
- **Tests:** Vitest, node environment, files named `*.test.ts(x)` under `src`. Run from `web/` with `npm run test`. Alias `@` → `src`. See `web/vitest.config.ts` and `web/src/app/api/recitation/token/route.test.ts` for conventions.
- **Working directory** for all commands: `web/` inside the `group0-foundation` worktree.
- **Shipping:** commit locally per task. Do NOT push or run `suhuf ship`/`quickfix` — that happens at the end after the user approves.

## File structure

Create:
- `web/src/lib/supabase/client.ts` — browser anon client (`createBrowserClient`).
- `web/src/lib/supabase/server.ts` — server anon client (`createServerClient` + `next/headers` cookies).
- `web/src/lib/proxy-paths.ts` — pure helpers: `isProtectedPath`, `loginRedirectTarget`, `safeRedirect`.
- `web/src/lib/proxy-paths.test.ts` — unit tests for the pure helpers.
- `web/src/proxy.ts` — replaces `web/src/middleware.ts`: rate-limit `/api/*` + Supabase session refresh + redirect on protected paths.
- `web/src/app/(app)/layout.tsx` — auth-gated layout (replaces the `/internal` banner layout).
- `web/src/app/(app)/reader/[openiti_id]/page.tsx` — moved from `internal/reader`.
- `web/src/app/(app)/library/page.tsx` — moved from `internal/library`.
- `web/src/app/(app)/inspector/[openiti_id]/page.tsx` — moved from `internal/inspector`.
- `web/src/app/(app)/dashboard/page.tsx` — new minimal landing.
- `web/src/app/(app)/dashboard/SignOutButton.tsx` — client sign-out control.
- `web/src/app/login/page.tsx` — server page (reads `redirectTo`).
- `web/src/app/login/LoginForm.tsx` — client login/signup toggle form.

Modify:
- `web/package.json` — add `@supabase/ssr`.
- `web/.env.local` and `web/.env.local.example` — add the two `NEXT_PUBLIC_SUPABASE_*` vars.
- `web/src/components/reader/ModeToggle.tsx` — update `/internal/...` path regex.

Delete:
- `web/src/middleware.ts`
- `web/src/app/internal/` (entire tree: `layout.tsx`, `reader/`, `library/`, `inspector/`).

---

## Task 1: Install @supabase/ssr and add env vars

**Files:**
- Modify: `web/package.json` (+ `package-lock.json` via install)
- Modify: `web/.env.local`, `web/.env.local.example`

- [ ] **Step 1: Install the package**

Run (from `web/`):
```bash
npm install @supabase/ssr
```
Expected: `@supabase/ssr` added to `dependencies` in `package.json`, lockfile updated, no peer-dep errors.

- [ ] **Step 2: Add env vars to `.env.local.example`**

Append these lines to `web/.env.local.example`:
```
# Public Supabase keys for browser + proxy auth (anon key — safe to expose)
NEXT_PUBLIC_SUPABASE_URL=
NEXT_PUBLIC_SUPABASE_ANON_KEY=
```

- [ ] **Step 3: Add real values to `.env.local`**

Add the same two keys to `web/.env.local`, filled with the project URL and the **anon/publishable** key from the Supabase dashboard (Project Settings → API). `NEXT_PUBLIC_SUPABASE_URL` is the same URL as the existing `SUPABASE_URL`.

> Note: `.env.local` is gitignored and may be permission-restricted for the agent. If you cannot edit it, STOP and ask the user to paste the anon key — auth cannot be verified without it.

- [ ] **Step 4: Commit**

```bash
git add web/package.json web/package-lock.json web/.env.local.example
git commit -m "build: add @supabase/ssr and public supabase env vars"
```

---

## Task 2: Supabase browser + server clients

**Files:**
- Create: `web/src/lib/supabase/client.ts`
- Create: `web/src/lib/supabase/server.ts`

- [ ] **Step 1: Write the browser client**

Create `web/src/lib/supabase/client.ts`:
```ts
import { createBrowserClient } from "@supabase/ssr";

export function createClient() {
  return createBrowserClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
  );
}
```

- [ ] **Step 2: Write the server client**

Create `web/src/lib/supabase/server.ts`:
```ts
import { createServerClient } from "@supabase/ssr";
import { cookies } from "next/headers";

export async function createClient() {
  const cookieStore = await cookies();

  return createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    {
      cookies: {
        getAll() {
          return cookieStore.getAll();
        },
        setAll(cookiesToSet) {
          try {
            cookiesToSet.forEach(({ name, value, options }) =>
              cookieStore.set(name, value, options),
            );
          } catch {
            // Called from a Server Component, which cannot write cookies.
            // Safe to ignore: proxy.ts refreshes the session and writes cookies.
          }
        },
      },
    },
  );
}
```

- [ ] **Step 3: Typecheck**

Run (from `web/`):
```bash
npx tsc --noEmit
```
Expected: no errors from the two new files.

- [ ] **Step 4: Commit**

```bash
git add web/src/lib/supabase/client.ts web/src/lib/supabase/server.ts
git commit -m "feat: add supabase browser and server (anon) clients"
```

---

## Task 3: Proxy — pure path helpers (TDD) + session refresh + gating

**Files:**
- Create: `web/src/lib/proxy-paths.ts`
- Test: `web/src/lib/proxy-paths.test.ts`
- Create: `web/src/proxy.ts`
- Delete: `web/src/middleware.ts`

- [ ] **Step 1: Write the failing test for the pure helpers**

Create `web/src/lib/proxy-paths.test.ts`:
```ts
import { describe, it, expect } from "vitest";
import { isProtectedPath, loginRedirectTarget, safeRedirect } from "./proxy-paths";

describe("isProtectedPath", () => {
  it("matches protected roots and their children", () => {
    expect(isProtectedPath("/reader")).toBe(true);
    expect(isProtectedPath("/reader/0123Book")).toBe(true);
    expect(isProtectedPath("/library")).toBe(true);
    expect(isProtectedPath("/inspector/0123Book")).toBe(true);
    expect(isProtectedPath("/dashboard")).toBe(true);
  });

  it("does not match public paths or lookalikes", () => {
    expect(isProtectedPath("/")).toBe(false);
    expect(isProtectedPath("/login")).toBe(false);
    expect(isProtectedPath("/welcome")).toBe(false);
    expect(isProtectedPath("/r/abc")).toBe(false);
    expect(isProtectedPath("/readerly")).toBe(false);
  });
});

describe("loginRedirectTarget", () => {
  it("builds an encoded /login?redirectTo=... path", () => {
    expect(loginRedirectTarget("/reader/0123", "")).toBe(
      "/login?redirectTo=%2Freader%2F0123",
    );
  });

  it("includes the original query string", () => {
    expect(loginRedirectTarget("/library", "?page=2")).toBe(
      "/login?redirectTo=%2Flibrary%3Fpage%3D2",
    );
  });
});

describe("safeRedirect", () => {
  it("allows internal paths", () => {
    expect(safeRedirect("/reader/0123")).toBe("/reader/0123");
  });

  it("rejects external/protocol-relative urls and falls back to /dashboard", () => {
    expect(safeRedirect("//evil.com")).toBe("/dashboard");
    expect(safeRedirect("https://evil.com")).toBe("/dashboard");
    expect(safeRedirect(undefined)).toBe("/dashboard");
    expect(safeRedirect("")).toBe("/dashboard");
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run (from `web/`):
```bash
npm run test -- proxy-paths
```
Expected: FAIL — `Cannot find module './proxy-paths'` (file not created yet).

- [ ] **Step 3: Implement the pure helpers**

Create `web/src/lib/proxy-paths.ts`:
```ts
export const PROTECTED_PREFIXES = [
  "/reader",
  "/library",
  "/inspector",
  "/dashboard",
] as const;

export function isProtectedPath(pathname: string): boolean {
  return PROTECTED_PREFIXES.some(
    (prefix) => pathname === prefix || pathname.startsWith(prefix + "/"),
  );
}

export function loginRedirectTarget(pathname: string, search = ""): string {
  const params = new URLSearchParams({ redirectTo: pathname + search });
  return `/login?${params.toString()}`;
}

export function safeRedirect(to: string | undefined): string {
  if (to && to.startsWith("/") && !to.startsWith("//")) return to;
  return "/dashboard";
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run (from `web/`):
```bash
npm run test -- proxy-paths
```
Expected: PASS (all three describe blocks green).

- [ ] **Step 5: Write `proxy.ts` (rate limit + session refresh + gating)**

Create `web/src/proxy.ts` (this folds in the existing rate-limiter from `middleware.ts` verbatim, then adds Supabase session refresh and the protected-path redirect):
```ts
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
  const {
    data: { user },
  } = await supabase.auth.getUser();

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
```

- [ ] **Step 6: Delete the old middleware file**

```bash
git rm web/src/middleware.ts
```

- [ ] **Step 7: Typecheck + run full test suite**

Run (from `web/`):
```bash
npx tsc --noEmit && npm run test
```
Expected: no type errors; `proxy-paths.test.ts` passes; existing tests still pass.

- [ ] **Step 8: Commit**

```bash
git add web/src/lib/proxy-paths.ts web/src/lib/proxy-paths.test.ts web/src/proxy.ts
git commit -m "feat: proxy auth gating + session refresh (replaces middleware)"
```

---

## Task 4: Move reader surfaces into `(app)` route group + gated layout

**Files:**
- Create: `web/src/app/(app)/layout.tsx`
- Move: `internal/reader/[openiti_id]/page.tsx` → `(app)/reader/[openiti_id]/page.tsx`
- Move: `internal/library/page.tsx` → `(app)/library/page.tsx`
- Move: `internal/inspector/[openiti_id]/page.tsx` → `(app)/inspector/[openiti_id]/page.tsx`
- Modify: the three moved pages (update `/internal/...` link hrefs)
- Modify: `web/src/components/reader/ModeToggle.tsx`
- Delete: `web/src/app/internal/` (including `layout.tsx`)

- [ ] **Step 1: Create the gated `(app)` layout**

Create `web/src/app/(app)/layout.tsx`:
```tsx
import type { Metadata } from "next";
import type { ReactNode } from "react";
import { redirect } from "next/navigation";
import { createClient } from "@/lib/supabase/server";

export const metadata: Metadata = {
  robots: { index: false, follow: false, nocache: true },
};

export default async function AppLayout({ children }: { children: ReactNode }) {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  if (!user) redirect("/login");

  return <div className="min-h-screen bg-white text-zinc-900">{children}</div>;
}
```

- [ ] **Step 2: Move the three pages with git (preserves history)**

```bash
mkdir -p "web/src/app/(app)/reader/[openiti_id]" "web/src/app/(app)/inspector/[openiti_id]" "web/src/app/(app)/library"
git mv "web/src/app/internal/reader/[openiti_id]/page.tsx" "web/src/app/(app)/reader/[openiti_id]/page.tsx"
git mv "web/src/app/internal/library/page.tsx" "web/src/app/(app)/library/page.tsx"
git mv "web/src/app/internal/inspector/[openiti_id]/page.tsx" "web/src/app/(app)/inspector/[openiti_id]/page.tsx"
```

- [ ] **Step 3: Update the `← library` link in the reader page**

In `web/src/app/(app)/reader/[openiti_id]/page.tsx`, change:
```tsx
            href="/internal/library"
```
to:
```tsx
            href="/library"
```

- [ ] **Step 4: Update the `← library` link in the inspector page**

In `web/src/app/(app)/inspector/[openiti_id]/page.tsx`, change:
```tsx
        <Link href="/internal/library" className="text-xs font-mono text-zinc-600 hover:text-zinc-900">
```
to:
```tsx
        <Link href="/library" className="text-xs font-mono text-zinc-600 hover:text-zinc-900">
```

- [ ] **Step 5: Update the Reader/Inspector links in the library page**

In `web/src/app/(app)/library/page.tsx`, change:
```tsx
                  <Link href={`/internal/reader/${id}`} className="px-2 py-1 rounded bg-zinc-100 hover:bg-zinc-200">
                    Reader
                  </Link>
                  <Link href={`/internal/inspector/${id}`} className="px-2 py-1 rounded bg-zinc-100 hover:bg-zinc-200">
                    Inspector
                  </Link>
```
to:
```tsx
                  <Link href={`/reader/${id}`} className="px-2 py-1 rounded bg-zinc-100 hover:bg-zinc-200">
                    Reader
                  </Link>
                  <Link href={`/inspector/${id}`} className="px-2 py-1 rounded bg-zinc-100 hover:bg-zinc-200">
                    Inspector
                  </Link>
```

- [ ] **Step 6: Update the path regex in `ModeToggle.tsx`**

In `web/src/components/reader/ModeToggle.tsx`, change:
```tsx
  const target = pathname.replace(/^\/internal\/(reader|inspector)/, `/internal/${other}`);
```
to:
```tsx
  const target = pathname.replace(/^\/(reader|inspector)/, `/${other}`);
```

- [ ] **Step 7: Delete the now-empty `internal/` tree**

```bash
git rm "web/src/app/internal/layout.tsx"
```
Then confirm nothing remains:
```bash
ls -R "web/src/app/internal" 2>/dev/null || echo "internal removed"
```
Expected: `internal removed` (the three pages were already `git mv`'d out; only the layout was left).

- [ ] **Step 8: Verify no stale `/internal` references remain**

Run (from repo root):
```bash
grep -rn "/internal" web/src || echo "no /internal references"
```
Expected: `no /internal references`.

- [ ] **Step 9: Typecheck**

Run (from `web/`):
```bash
npx tsc --noEmit
```
Expected: no errors.

- [ ] **Step 10: Commit**

```bash
git add -A web/src/app web/src/components/reader/ModeToggle.tsx
git commit -m "feat: move reader/library/inspector to root behind gated (app) layout"
```

---

## Task 5: Login page + login/signup toggle form

**Files:**
- Create: `web/src/app/login/page.tsx`
- Create: `web/src/app/login/LoginForm.tsx`

- [ ] **Step 1: Create the server page (reads + sanitizes `redirectTo`)**

Create `web/src/app/login/page.tsx`:
```tsx
import { LoginForm } from "./LoginForm";
import { safeRedirect } from "@/lib/proxy-paths";

export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ redirectTo?: string }>;
}) {
  const { redirectTo } = await searchParams;

  return (
    <main className="min-h-screen flex items-center justify-center bg-zinc-50 px-4">
      <LoginForm redirectTo={safeRedirect(redirectTo)} />
    </main>
  );
}
```

- [ ] **Step 2: Create the client form**

Create `web/src/app/login/LoginForm.tsx`:
```tsx
"use client";

import { useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { createClient } from "@/lib/supabase/client";

type Mode = "login" | "signup";

export function LoginForm({ redirectTo }: { redirectTo: string }) {
  const router = useRouter();
  const [mode, setMode] = useState<Mode>("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setPending(true);
    const supabase = createClient();
    const { error } =
      mode === "login"
        ? await supabase.auth.signInWithPassword({ email, password })
        : await supabase.auth.signUp({ email, password });
    setPending(false);
    if (error) {
      setError(error.message);
      return;
    }
    router.push(redirectTo);
    router.refresh();
  }

  return (
    <div className="w-full max-w-sm rounded-lg border border-zinc-200 bg-white p-6 shadow-sm">
      <div className="mb-4 flex gap-1 text-sm font-medium">
        <button
          type="button"
          onClick={() => setMode("login")}
          className={`flex-1 rounded px-3 py-1.5 ${mode === "login" ? "bg-zinc-900 text-white" : "bg-zinc-100 text-zinc-600"}`}
        >
          Log in
        </button>
        <button
          type="button"
          onClick={() => setMode("signup")}
          className={`flex-1 rounded px-3 py-1.5 ${mode === "signup" ? "bg-zinc-900 text-white" : "bg-zinc-100 text-zinc-600"}`}
        >
          Sign up
        </button>
      </div>

      <form onSubmit={onSubmit} className="space-y-3">
        <input
          type="email"
          required
          autoComplete="email"
          placeholder="Email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          className="w-full rounded border border-zinc-300 px-3 py-2 text-sm"
        />
        <input
          type="password"
          required
          autoComplete={mode === "login" ? "current-password" : "new-password"}
          placeholder="Password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className="w-full rounded border border-zinc-300 px-3 py-2 text-sm"
        />
        {error && <p className="text-sm text-red-600">{error}</p>}
        <button
          type="submit"
          disabled={pending}
          className="w-full rounded bg-zinc-900 px-3 py-2 text-sm font-medium text-white disabled:opacity-50"
        >
          {pending ? "…" : mode === "login" ? "Log in" : "Sign up"}
        </button>
      </form>
    </div>
  );
}
```

- [ ] **Step 3: Typecheck**

Run (from `web/`):
```bash
npx tsc --noEmit
```
Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add web/src/app/login/page.tsx web/src/app/login/LoginForm.tsx
git commit -m "feat: /login page with login/signup toggle"
```

---

## Task 6: Dashboard + sign-out

**Files:**
- Create: `web/src/app/(app)/dashboard/page.tsx`
- Create: `web/src/app/(app)/dashboard/SignOutButton.tsx`

- [ ] **Step 1: Create the dashboard page**

Create `web/src/app/(app)/dashboard/page.tsx`:
```tsx
import { createClient } from "@/lib/supabase/server";
import { SignOutButton } from "./SignOutButton";

export default async function DashboardPage() {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  return (
    <main className="mx-auto max-w-3xl px-4 py-8">
      <h1 className="mb-4 text-xl font-bold">Hi {user?.email}</h1>
      <SignOutButton />
    </main>
  );
}
```

- [ ] **Step 2: Create the sign-out button**

Create `web/src/app/(app)/dashboard/SignOutButton.tsx`:
```tsx
"use client";

import { useRouter } from "next/navigation";
import { createClient } from "@/lib/supabase/client";

export function SignOutButton() {
  const router = useRouter();

  async function onClick() {
    await createClient().auth.signOut();
    router.push("/login");
    router.refresh();
  }

  return (
    <button
      onClick={onClick}
      className="rounded bg-zinc-100 px-3 py-1.5 text-sm font-medium text-zinc-700 hover:bg-zinc-200"
    >
      Sign out
    </button>
  );
}
```

- [ ] **Step 3: Typecheck + full test suite**

Run (from `web/`):
```bash
npx tsc --noEmit && npm run test
```
Expected: no type errors; all tests pass.

- [ ] **Step 4: Commit**

```bash
git add "web/src/app/(app)/dashboard/page.tsx" "web/src/app/(app)/dashboard/SignOutButton.tsx"
git commit -m "feat: minimal /dashboard with sign-out"
```

---

## Task 7: Manual verification (dev server)

No new code. Confirm the whole flow works end-to-end. The reader is a server component and gating happens server-side, so verify there is no content flash.

- [ ] **Step 1: Start the dev server**

Run (from `web/`):
```bash
npm run dev
```

- [ ] **Step 2: Verify the gate (logged out)**

Visit `/reader/<an-openiti-id-in-web/data>` while logged out. Expected: redirected to `/login?redirectTo=%2Freader%2F...`. The reader content must NOT flash before redirect.

- [ ] **Step 3: Verify signup → dashboard**

On `/login`, switch to **Sign up**, register a new email + password. Expected: immediate redirect to `/dashboard` showing "Hi <email>". (Email confirmation is disabled in the project, so a session is returned immediately. If signup instead shows no session / an "email not confirmed" error, STOP — confirmation is unexpectedly enabled and the design needs the deferred callback route; report to the user.)

- [ ] **Step 4: Verify deep-link return**

Sign out, then visit `/library` directly. Expected: redirected to login; after logging in, you land back on `/library` (not `/dashboard`).

- [ ] **Step 5: Verify the reader still reads local files**

From `/library`, open a book in the reader and the inspector. Expected: pages render from `web/data/*.json` exactly as before; Reader/Inspector toggle and `← library` links work with the new root paths.

- [ ] **Step 6: Verify sign-out**

On `/dashboard`, click **Sign out**. Expected: redirected to `/login`; revisiting `/dashboard` redirects back to login.

- [ ] **Step 7: Verify public routes are unaffected**

Visit `/`, `/welcome`, and an `/r/<code>` link while logged out. Expected: all load normally (no auth redirect). Hit a rate-limited API route repeatedly to confirm the 429 limiter still fires.

---

## Final: verify + ship (after user confirmation)

- [ ] Run `./bin/suhuf verify` from the worktree and confirm green.
- [ ] Ask the user "Ready to ship?" and wait for confirmation.
- [ ] On yes: `./bin/suhuf worktree finish` (runs `suhuf ship` from the worktree).
