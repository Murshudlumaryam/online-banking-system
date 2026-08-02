// Token persistence.
//
// SECURITY NOTE: the backend issues bearer tokens (no httpOnly cookie
// support), so the frontend has to hold them somewhere JS can read. We use
// localStorage so a session survives a page reload, which is the standard
// tradeoff for bearer-token APIs without a BFF layer. This does mean an XSS
// vulnerability elsewhere in the app could exfiltrate tokens — mitigated by:
// short-lived access tokens (15 min, see backend Settings.access_token_expire_minutes),
// refresh-token rotation with reuse detection (see backend AuthService.refresh),
// and strict input handling throughout this app (no dangerouslySetInnerHTML).
// A production hardening pass (Phase 6) could move to an httpOnly-cookie
// refresh flow via a backend-for-frontend if this app ever leaves a closed,
// trusted deployment.
const ACCESS_TOKEN_KEY = "banking.access_token";
const REFRESH_TOKEN_KEY = "banking.refresh_token";

export const tokenStorage = {
  getAccessToken(): string | null {
    return localStorage.getItem(ACCESS_TOKEN_KEY);
  },
  getRefreshToken(): string | null {
    return localStorage.getItem(REFRESH_TOKEN_KEY);
  },
  setTokens(accessToken: string, refreshToken: string): void {
    localStorage.setItem(ACCESS_TOKEN_KEY, accessToken);
    localStorage.setItem(REFRESH_TOKEN_KEY, refreshToken);
  },
  clear(): void {
    localStorage.removeItem(ACCESS_TOKEN_KEY);
    localStorage.removeItem(REFRESH_TOKEN_KEY);
  },
};
