// Client-side JWT decoding is for UI routing decisions ONLY (which nav to
// show, which route guard to apply). It is never trusted as an authorization
// check â€” every protected backend endpoint re-validates the token's
// signature and claims independently. Do not add access-control logic here.
interface AccessTokenClaims {
  sub: string;
  role: "ADMIN" | "CUSTOMER";
  type: string;
  exp: number;
  iat: number;
  jti: string;
}

export function decodeAccessToken(token: string): AccessTokenClaims | null {
  try {
    const payloadSegment = token.split(".")[1];
    const normalized = payloadSegment.replace(/-/g, "+").replace(/_/g, "/");
    const json = atob(normalized);
    return JSON.parse(json) as AccessTokenClaims;
  } catch {
    return null;
  }
}

export function isTokenExpired(claims: AccessTokenClaims, skewSeconds = 10): boolean {
  const nowInSeconds = Date.now() / 1000;
  return claims.exp - skewSeconds <= nowInSeconds;
}
