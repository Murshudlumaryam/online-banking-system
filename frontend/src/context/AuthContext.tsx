import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";

import { registerApiSessionExpiredHandler } from "@/api/client";
import { registerSessionExpiredHandler, refreshAccessToken } from "@/lib/apiClient";
import { decodeAccessToken, isTokenExpired } from "@/lib/jwt";
import { tokenStorage } from "@/lib/tokenStorage";
import { authService, type RegisterPayload } from "@/services/authService";
import type { UserRole } from "@/types/api";

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
  register: (payload: RegisterPayload) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<SessionStatus>("loading");
  const [role, setRole] = useState<UserRole | null>(null);

  const applyTokens = useCallback((accessToken: string) => {
    const claims = decodeAccessToken(accessToken);
    setRole(claims?.role ?? null);
    setStatus("authenticated");
  }, []);

  const clearSession = useCallback(() => {
    tokenStorage.clear();
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

  // On first load, resume a session from a persisted refresh token if the
  // access token has expired since the last visit.
  useEffect(() => {
    async function bootstrap() {
      const accessToken = tokenStorage.getAccessToken();
      const claims = accessToken ? decodeAccessToken(accessToken) : null;

      if (accessToken && claims && !isTokenExpired(claims)) {
        applyTokens(accessToken);
        return;
      }

      if (tokenStorage.getRefreshToken()) {
        try {
          const newAccessToken = await refreshAccessToken();
          applyTokens(newAccessToken);
          return;
        } catch {
          // Refresh token was invalid/expired/reused — fall through to logged-out.
        }
      }
      clearSession();
    }
    void bootstrap();
  }, [applyTokens, clearSession]);

  const login = useCallback(
    async (email: string, password: string) => {
      const result = await authService.login(email, password);
      if (result.mfa_required && result.challenge_token) {
        return { mfaRequired: true as const, challengeToken: result.challenge_token };
      }
      if (result.access_token && result.refresh_token) {
        tokenStorage.setTokens(result.access_token, result.refresh_token);
        applyTokens(result.access_token);
      }
      return { mfaRequired: false as const };
    },
    [applyTokens],
  );

  const completeMfaLogin = useCallback(
    async (challengeToken: string, code: string) => {
      const tokens = await authService.verifyMfaLogin(challengeToken, code);
      tokenStorage.setTokens(tokens.access_token, tokens.refresh_token);
      applyTokens(tokens.access_token);
    },
    [applyTokens],
  );

  const register = useCallback(async (payload: RegisterPayload) => {
    await authService.register(payload);
  }, []);

  const logout = useCallback(async () => {
    const refreshToken = tokenStorage.getRefreshToken();
    if (refreshToken) {
      try {
        await authService.logout(refreshToken);
      } catch {
        // Best-effort — proceed to clear the local session regardless.
      }
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
