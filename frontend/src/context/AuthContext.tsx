import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";

import { registerApiSessionExpiredHandler } from "@/api/client";
import { accessTokenStore } from "@/lib/accessTokenStore";
import { registerSessionExpiredHandler, refreshAccessToken } from "@/lib/apiClient";
import { decodeAccessToken } from "@/lib/jwt";
import { authService, type RegisterPayload } from "@/services/authService";
import type { RegisterResponse, UserRole } from "@/types/api";

type SessionStatus = "loading" | "authenticated" | "unauthenticated";

interface AuthContextValue {
  status: SessionStatus;
  role: UserRole | null;
  /**
   * Logs in with email/password. Returns `{ mfaRequired: true, challengeToken }`
   * if the account has 2FA enabled — the caller (LoginPage) is responsible
   * for collecting the authenticator code and calling `completeMfaLogin`.
   * Otherwise the session is established immediately and the plain result
   * is returned.
   */
  login: (email: string, password: string) => Promise<{ mfaRequired: boolean; challengeToken?: string }>;
  completeMfaLogin: (challengeToken: string, code: string) => Promise<void>;
  register: (payload: RegisterPayload) => Promise<RegisterResponse>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<SessionStatus>("loading");
  const [role, setRole] = useState<UserRole | null>(null);

  const applyAccessToken = useCallback((accessToken: string) => {
    accessTokenStore.set(accessToken);
    const claims = decodeAccessToken(accessToken);
    setRole(claims?.role ?? null);
    setStatus("authenticated");
  }, []);

  const clearSession = useCallback(() => {
    accessTokenStore.clear();
    setRole(null);
    setStatus("unauthenticated");
  }, []);

  useEffect(() => {
    // Two independent HTTP clients are in play (the legacy axios client in
    // lib/apiClient.ts, and the OpenAPI-generated client in api/client.ts —
    // see frontend/README.md for why both currently exist). Either one
    // hitting a terminal 401 should end the session the same way.
    registerSessionExpiredHandler(clearSession);
    registerApiSessionExpiredHandler(clearSession);
  }, [clearSession]);

  // On first load there is no access token to check — it's memory-only and
  // never survives a reload (see lib/accessTokenStore.ts). The only way to
  // know if the visitor has a live session is to ask the backend: a silent
  // POST /auth/refresh, authenticated purely by the HttpOnly refresh_token
  // cookie the browser sends automatically. Success re-establishes the
  // session with a fresh access token; failure (no cookie, or an
  // expired/revoked one) means logged-out, same as a first-time visitor.
  useEffect(() => {
    async function bootstrap() {
      try {
        const newAccessToken = await refreshAccessToken();
        applyAccessToken(newAccessToken);
      } catch {
        clearSession();
      }
    }
    void bootstrap();
  }, [applyAccessToken, clearSession]);

  const login = useCallback(
    async (email: string, password: string) => {
      const result = await authService.login(email, password);
      if (result.mfa_required && result.challenge_token) {
        return { mfaRequired: true as const, challengeToken: result.challenge_token };
      }
      if (result.access_token) {
        // The refresh_token cookie was already set by the browser from this
        // same response's Set-Cookie header (axios's withCredentials: true
        // in lib/apiClient.ts / api/client.ts's credentials: "include" is
        // what makes that happen) — nothing to do with it here.
        applyAccessToken(result.access_token);
      }
      return { mfaRequired: false as const };
    },
    [applyAccessToken],
  );

  const completeMfaLogin = useCallback(
    async (challengeToken: string, code: string) => {
      const tokens = await authService.verifyMfaLogin(challengeToken, code);
      applyAccessToken(tokens.access_token);
    },
    [applyAccessToken],
  );

  const register = useCallback(async (payload: RegisterPayload) => {
    return authService.register(payload);
  }, []);

  const logout = useCallback(async () => {
    try {
      // No token to pass — the backend reads the refresh_token cookie
      // itself and clears it on response.
      await authService.logout();
    } catch {
      // Best-effort — proceed to clear the local session regardless.
    }
    clearSession();
  }, [clearSession]);

  const value = useMemo(
    () => ({ status, role, login, completeMfaLogin, register, logout }),
    [status, role, login, completeMfaLogin, register, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

// eslint-disable-next-line react-refresh/only-export-components -- context module conventionally exports both the provider and its hook
export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}
