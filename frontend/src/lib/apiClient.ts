import axios, { type AxiosError, type InternalAxiosRequestConfig } from "axios";

import type { ApiErrorBody, TokenResponse } from "@/types/api";
import { tokenStorage } from "@/lib/tokenStorage";

const BASE_URL = import.meta.env.VITE_API_BASE_URL;

export const apiClient = axios.create({ baseURL: BASE_URL });

// Registered by AuthProvider so the interceptor can trigger a clean logout +
// redirect without importing React Router into a plain module.
let onSessionExpired: (() => void) | null = null;
export function registerSessionExpiredHandler(handler: () => void): void {
  onSessionExpired = handler;
}

apiClient.interceptors.request.use((config) => {
  const token = tokenStorage.getAccessToken();
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// A request that hits 401 while a refresh is already underway waits for
// that same in-flight refresh instead of firing its own — otherwise every
// simultaneously-rejected request would race to rotate the refresh token,
// and only the first would win (see backend's reuse-detection semantics).
let refreshPromise: Promise<string> | null = null;

export async function refreshAccessToken(): Promise<string> {
  const refreshToken = tokenStorage.getRefreshToken();
  if (!refreshToken) {
    throw new Error("No refresh token available");
  }
  const response = await axios.post<TokenResponse>(`${BASE_URL}/auth/refresh`, {
    refresh_token: refreshToken,
  });
  tokenStorage.setTokens(response.data.access_token, response.data.refresh_token);
  return response.data.access_token;
}

interface RetryableConfig extends InternalAxiosRequestConfig {
  _retried?: boolean;
}

apiClient.interceptors.response.use(
  (response) => response,
  async (error: AxiosError<ApiErrorBody>) => {
    const originalRequest = error.config as RetryableConfig | undefined;
    const isAuthEndpoint = originalRequest?.url?.includes("/auth/login") ||
      originalRequest?.url?.includes("/auth/refresh");

    if (error.response?.status === 401 && originalRequest && !originalRequest._retried && !isAuthEndpoint) {
      originalRequest._retried = true;
      try {
        refreshPromise ??= refreshAccessToken().finally(() => {
          refreshPromise = null;
        });
        const newAccessToken = await refreshPromise;
        originalRequest.headers.Authorization = `Bearer ${newAccessToken}`;
        return apiClient(originalRequest);
      } catch {
        tokenStorage.clear();
        onSessionExpired?.();
      }
    }

    return Promise.reject(error);
  },
);

/**
 * Extracts the backend's ApiErrorBody from a caught error, regardless of
 * whether it came from the axios-based client (a real AxiosError) or the
 * generated openapi-fetch client (services/*.ts throw a plain object
 * shaped like `{ response: { data, status } }` on purpose, so both error
 * paths can be handled uniformly by callers here and throughout the app).
 */
function extractErrorBody(error: unknown): ApiErrorBody | undefined {
  if (axios.isAxiosError(error)) {
    return error.response?.data as ApiErrorBody | undefined;
  }
  if (error && typeof error === "object" && "response" in error) {
    const response = (error as { response?: { data?: unknown } }).response;
    return response?.data as ApiErrorBody | undefined;
  }
  return undefined;
}

/** Extracts a user-friendly message from a caught API error, with a safe fallback. */
export function getApiErrorMessage(error: unknown, fallback = "Something went wrong. Please try again."): string {
  const body = extractErrorBody(error);
  if (body?.message) return body.message;
  if (error instanceof Error && error.message) return error.message;
  return fallback;
}

export function getApiErrorCode(error: unknown): string | null {
  return extractErrorBody(error)?.error_code ?? null;
}
