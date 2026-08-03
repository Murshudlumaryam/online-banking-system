import { api } from "@/api/client";
import type { RegisterResponse, SessionResponse, TokenResponse } from "@/types/api";

export interface RegisterPayload {
  email: string;
  password: string;
  first_name: string;
  last_name: string;
  date_of_birth: string;
  phone_number: string;
  address?: string;
  national_id?: string;
}

async function unwrap<T>(promise: Promise<{ data?: T; error?: unknown; response: Response }>): Promise<T> {
  const { data, error, response } = await promise;
  if (error) throw { response: { data: error, status: response.status } };
  return data as T;
}

export const authService = {
  async register(payload: RegisterPayload): Promise<RegisterResponse> {
    return unwrap(api.POST("/api/v1/auth/register", { body: payload }));
  },

  async login(email: string, password: string) {
    return unwrap(api.POST("/api/v1/auth/login", { body: { email, password } }));
  },

  async logout(): Promise<void> {
    await api.POST("/api/v1/auth/logout", { body: {} } as never);
  },

  async getSession(): Promise<SessionResponse> {
    return unwrap(api.GET("/api/v1/auth/session" as never, {} as never));
  },

  async changePassword(currentPassword: string, newPassword: string): Promise<void> {
    await unwrap(
      api.POST("/api/v1/auth/password/change", {
        body: { current_password: currentPassword, new_password: newPassword },
      }),
    );
  },

  async requestPasswordReset(email: string): Promise<void> {
    await api.POST("/api/v1/auth/password/reset-request", { body: { email } });
  },

  async confirmPasswordReset(resetToken: string, newPassword: string): Promise<void> {
    await unwrap(
      api.POST("/api/v1/auth/password/reset-confirm", {
        body: { reset_token: resetToken, new_password: newPassword },
      }),
    );
  },

  async setupTwoFactor() {
    return unwrap(api.POST("/api/v1/auth/2fa/setup", {}));
  },

  async enableTwoFactor(code: string): Promise<void> {
    await unwrap(api.POST("/api/v1/auth/2fa/enable", { body: { code } }));
  },

  async disableTwoFactor(password: string, code: string): Promise<void> {
    await unwrap(api.POST("/api/v1/auth/2fa/disable", { body: { password, code } }));
  },

  async verifyMfaLogin(challengeToken: string, code: string): Promise<TokenResponse> {
    return unwrap(
      api.POST("/api/v1/auth/2fa/verify-login", {
        body: { challenge_token: challengeToken, code },
      }),
    );
  },
};
