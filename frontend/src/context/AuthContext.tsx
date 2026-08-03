import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";

import { registerApiSessionExpiredHandler } from "@/api/client";
import { registerSessionExpiredHandler } from "@/lib/apiClient";
import { authService, type RegisterPayload } from "@/services/authService";
import type { UserRole } from "@/types/api";

type SessionStatus = "loading" | "authenticated" | "unauthenticated";

interface AuthContextValue {
  status: SessionStatus;
  role: UserRole | null;
  login: (email: string, password: string) => Promise<{ mfaRequired: boolean; challengeToken?: string }>;
  completeMfaLogin: (challengeToken: string, code: string) => Promise<void>;
  register: (payload: RegisterPayload) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<SessionStatus>("loading");
  const [role, setRole] = useState<UserRole | null>(null);

  const applySession = useCallback((nextRole: UserRole) => {
    setRole(nextRole);
    setStatus("authenticated");
  }, []);

  const clearSession = useCallback(() => {
    setRole(null);
    setStatus("unauthenticated");
  }, []);

  useEffect(() => {
    registerSessionExpiredHandler(clearSession);
    registerApiSessionExpiredHandler(clearSession);
  }, [clearSession]);

  useEffect(() => {
    async function bootstrap() {
      try {
        const session = await authService.getSession();
        applySession(session.role);
        return;
      } catch {
        // Cookies are missing, expired, or revoked.
      }
      clearSession();
    }
    void bootstrap();
  }, [applySession, clearSession]);

  const login = useCallback(
    async (email: string, password: string) => {
      const result = await authService.login(email, password);
      if (result.mfa_required && result.challenge_token) {
        return { mfaRequired: true as const, challengeToken: result.challenge_token };
      }
      const session = await authService.getSession();
      applySession(session.role);
      return { mfaRequired: false as const };
    },
    [applySession],
  );

  const completeMfaLogin = useCallback(
    async (challengeToken: string, code: string) => {
      await authService.verifyMfaLogin(challengeToken, code);
      const session = await authService.getSession();
      applySession(session.role);
    },
    [applySession],
  );

  const register = useCallback(async (payload: RegisterPayload) => {
    await authService.register(payload);
  }, []);

  const logout = useCallback(async () => {
    try {
      await authService.logout();
    } catch {
      // Best-effort: always clear the local session state.
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
