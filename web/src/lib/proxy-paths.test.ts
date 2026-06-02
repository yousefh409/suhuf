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
