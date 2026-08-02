import { describe, expect, it } from "vitest";

import { decodeAccessToken, isTokenExpired } from "@/lib/jwt";

// Minimal helper to build a fake (unsigned) JWT for testing the decoder —
// the frontend never verifies signatures, so this is representative enough.
function fakeJwt(payload: Record<string, unknown>): string {
  const base64url = (obj: Record<string, unknown>) =>
    btoa(JSON.stringify(obj)).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
  return `${base64url({ alg: "HS256", typ: "JWT" })}.${base64url(payload)}.signature`;
}

describe("decodeAccessToken", () => {
  it("decodes a well-formed token's claims", () => {
    const token = fakeJwt({ sub: "user-1", role: "CUSTOMER", type: "access", exp: 9999999999, iat: 1 });
    const claims = decodeAccessToken(token);
    expect(claims?.sub).toBe("user-1");
    expect(claims?.role).toBe("CUSTOMER");
  });

  it("returns null for a malformed token", () => {
    expect(decodeAccessToken("not-a-jwt")).toBeNull();
  });
});

describe("isTokenExpired", () => {
  it("returns true for a token whose exp is in the past", () => {
    const claims = { sub: "x", role: "CUSTOMER" as const, type: "access", exp: 1, iat: 0, jti: "x" };
    expect(isTokenExpired(claims)).toBe(true);
  });

  it("returns false for a token whose exp is comfortably in the future", () => {
    const farFuture = Math.floor(Date.now() / 1000) + 3600;
    const claims = { sub: "x", role: "CUSTOMER" as const, type: "access", exp: farFuture, iat: 0, jti: "x" };
    expect(isTokenExpired(claims)).toBe(false);
  });

  it("treats a token within the safety skew window as expired", () => {
    const almostNow = Math.floor(Date.now() / 1000) + 5; // within default 10s skew
    const claims = { sub: "x", role: "CUSTOMER" as const, type: "access", exp: almostNow, iat: 0, jti: "x" };
    expect(isTokenExpired(claims)).toBe(true);
  });
});
