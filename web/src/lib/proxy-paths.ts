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
