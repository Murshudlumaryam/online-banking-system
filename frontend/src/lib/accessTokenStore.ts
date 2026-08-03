// In-memory access token storage.
//
// The refresh token never touches this module — or any JavaScript at all.
// It travels exclusively as an HttpOnly, Secure, SameSite=Strict cookie
// that the backend sets and reads directly (see
// backend/app/modules/auth/cookies.py); the browser attaches it
// automatically to requests under /api/v1/auth when the HTTP client is
// configured with credentials included (see lib/apiClient.ts and
// api/client.ts). A cookie JavaScript can't read can't be exfiltrated by an
// XSS payload the way a localStorage-held token could be.
//
// The access token itself is intentionally NOT persisted anywhere
// (localStorage, sessionStorage, or otherwise) — it lives only in this
// module-level variable, so it's gone on every page reload. That's a
// deliberate tradeoff, not an oversight: it means a reload always has to
// re-establish the session via a silent POST /auth/refresh (cookie-
// authenticated, see AuthContext's bootstrap effect) rather than trusting
// a token that was sitting in browser storage — the same storage an XSS
// payload would be able to read.
let currentAccessToken: string | null = null;

export const accessTokenStore = {
  get(): string | null {
    return currentAccessToken;
  },
  set(accessToken: string): void {
    currentAccessToken = accessToken;
  },
  clear(): void {
    currentAccessToken = null;
  },
};
