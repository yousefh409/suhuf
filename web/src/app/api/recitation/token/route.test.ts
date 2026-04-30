import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { createHmac } from "node:crypto";
import { POST } from "./route";

function makeReq(origin = "http://localhost:3000") {
  const req = new Request(`${origin}/api/recitation/token`, {
    method: "POST",
  }) as unknown as import("next/server").NextRequest;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  (req as any).nextUrl = { origin };
  return req;
}

describe("/api/recitation/token", () => {
  const ORIGINAL = process.env.RECITATION_AUTH_SECRET;

  beforeEach(() => {
    process.env.RECITATION_AUTH_SECRET = "s3cret";
    delete process.env.RECITATION_TOKEN_TTL_SEC;
  });

  afterEach(() => {
    if (ORIGINAL === undefined) delete process.env.RECITATION_AUTH_SECRET;
    else process.env.RECITATION_AUTH_SECRET = ORIGINAL;
  });

  it("returns a properly-shaped token when secret is set", async () => {
    const res = await POST(makeReq());
    expect(res.status).toBe(200);
    const body = await res.json();
    // Token must be base64url(payload).hex(hmac)
    expect(body.token).toMatch(/^[A-Za-z0-9_-]+\.[a-f0-9]{64}$/);
  });

  it("returns 404 when secret is unset", async () => {
    delete process.env.RECITATION_AUTH_SECRET;
    const res = await POST(makeReq());
    expect(res.status).toBe(404);
  });

  it("token payload contains correct origin and exp", async () => {
    const before = Math.floor(Date.now() / 1000);
    const res = await POST(makeReq("http://localhost:3000"));
    const after = Math.floor(Date.now() / 1000);
    const body = await res.json();
    const [p64] = body.token.split(".");
    const pad = "=".repeat((4 - (p64.length % 4)) % 4);
    const payload = JSON.parse(
      Buffer.from(p64.replace(/-/g, "+").replace(/_/g, "/") + pad, "base64").toString(),
    );
    expect(payload.origin).toBe("http://localhost:3000");
    expect(payload.exp).toBeGreaterThanOrEqual(before + 300);
    expect(payload.exp).toBeLessThanOrEqual(after + 300);
  });

  it("TTL is read from RECITATION_TOKEN_TTL_SEC env", async () => {
    process.env.RECITATION_TOKEN_TTL_SEC = "60";
    const before = Math.floor(Date.now() / 1000);
    const res = await POST(makeReq());
    const after = Math.floor(Date.now() / 1000);
    const body = await res.json();
    const [p64] = body.token.split(".");
    const pad = "=".repeat((4 - (p64.length % 4)) % 4);
    const payload = JSON.parse(
      Buffer.from(p64.replace(/-/g, "+").replace(/_/g, "/") + pad, "base64").toString(),
    );
    expect(payload.exp).toBeGreaterThanOrEqual(before + 60);
    expect(payload.exp).toBeLessThanOrEqual(after + 60);
  });

  // Cross-language compatibility test
  it("HMAC-SHA256 sig matches independent computation (cross-language compat)", async () => {
    const secret = "s3cret";
    process.env.RECITATION_AUTH_SECRET = secret;
    const res = await POST(makeReq("http://localhost:3000"));
    const body = await res.json();
    const [p64, sig] = body.token.split(".");

    // Independently verify sig
    const expectedSig = createHmac("sha256", secret).update(p64).digest("hex");
    expect(sig).toBe(expectedSig);

    // Decode and verify payload structure
    const pad = "=".repeat((4 - (p64.length % 4)) % 4);
    const payload = JSON.parse(
      Buffer.from(p64.replace(/-/g, "+").replace(/_/g, "/") + pad, "base64").toString(),
    );
    expect(payload.origin).toBe("http://localhost:3000");
    expect(typeof payload.exp).toBe("number");

    // Verify JSON property order matches Python's json.dumps({"origin":...,"exp":...})
    const raw = Buffer.from(p64.replace(/-/g, "+").replace(/_/g, "/") + pad, "base64").toString();
    expect(raw).toMatch(/^\{"origin":"[^"]+","exp":\d+\}$/);
  });

  it("base64url encoding has no padding characters", async () => {
    const res = await POST(makeReq());
    const body = await res.json();
    const [p64] = body.token.split(".");
    expect(p64).not.toContain("=");
    expect(p64).not.toContain("+");
    expect(p64).not.toContain("/");
  });
});
