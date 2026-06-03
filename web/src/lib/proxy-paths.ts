// Public: /library (Discover) and /reader/<id> render for logged-out visitors.
// Gated: the personal dashboard and the inspector.
export const PROTECTED_PREFIXES = [
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
  // Only allow same-origin paths. Reject protocol-relative ("//evil.com") and
  // backslash tricks ("/\\evil.com") — browsers normalize "\" to "/", so a
  // leading "/\\" resolves to an external origin.
  if (to && to.startsWith("/") && !to.startsWith("//") && !to.includes("\\")) {
    return to;
  }
  return "/dashboard";
}
