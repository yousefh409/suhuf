let cached: { token: string; exp: number } | null = null;

export async function fetchAuthToken(): Promise<string> {
  const now = Math.floor(Date.now() / 1000);
  if (cached && cached.exp > now + 30) return cached.token;
  const res = await fetch("/api/recitation/token", { method: "POST" });
  if (!res.ok) throw new Error(`token fetch failed: ${res.status}`);
  const body = (await res.json()) as { token: string };
  // Decode exp from token payload (best-effort, just for caching)
  try {
    const [p64] = body.token.split(".");
    const pad = "=".repeat((4 - (p64.length % 4)) % 4);
    const payload = JSON.parse(atob(p64.replace(/-/g, "+").replace(/_/g, "/") + pad));
    cached = { token: body.token, exp: payload.exp };
  } catch {
    cached = { token: body.token, exp: now + 60 };
  }
  return body.token;
}
