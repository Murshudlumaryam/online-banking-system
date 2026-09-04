import { api } from "@/api/client";
import type { RegisterResponse, TokenResponse } from "@/types/api";

export interface RegisterPayload {
  email: string;
  password: string;
  first_name: string;
  last_name: string;
  date_of_birth: string;
  phone_number: string;
  address?: string;
  national_id: string;
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

  async confirmRegistration(userId: string, otpCode: string): Promise<void> {
    await unwrap(
      api.POST("/api/v1/auth/register/confirm", { body: { user_id: userId, otp_code: otpCode } }),
    );
  },

  async resendRegistrationOtp(userId: string): Promise<{ otp_expires_in_seconds: number; message: string }> {
    return unwrap(api.POST("/api/v1/auth/register/resend-otp", { body: { user_id: userId } }));
  },

  async login(email: string, password: string) {
    return unwrap(api.POST("/api/v1/auth/login", { body: { email, password } }));
  },

  async logout(): Promise<void> {
    // No body — the refresh token to revoke is read from the HttpOnly
    // cookie server-side (see backend/app/modules/auth/router.py). The
    // `api` client's `credentials: "include"` setting (api/client.ts) is
    // what makes the browser attach that cookie to this request.
    await api.POST("/api/v1/auth/logout", {});
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
