import createClient, { type Middleware } from "openapi-fetch";

import type { paths } from "@/api/generated/schema";
import { tokenStorage } from "@/lib/tokenStorage";

// VITE_API_BASE_URL includes the "/api/v1" prefix (used by the hand-written
// axios client in lib/apiClient.ts), but the generated `paths` keys already
// embed that same prefix (they're the FastAPI app's literal route paths) —
// so this client's baseUrl must be just the origin, or every request would
// double up on "/api/v1".
const BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000/api/v1").replace(
  /\/api\/v1\/?$/,
  "",
);

export const api = createClient<paths>({ baseUrl: BASE_URL });

let onSessionExpired: (() => void) | null = null;
export function registerApiSessionExpiredHandler(handler: () => void): void {
  onSessionExpired = handler;
}

const authMiddleware: Middleware = {
  async onRequest({ request }) {
    const token = tokenStorage.getAccessToken();
    if (token) {
      request.headers.set("Authorization", `Bearer ${token}`);
    }
    return request;
  },
};

// Mirrors lib/apiClient.ts's refresh-on-401 behavior: concurrent 401s share
// a single in-flight refresh instead of each racing to rotate the token.
let refreshPromise: Promise<string> | null = null;

async function refreshAccessTokenViaFetch(): Promise<string> {
  const refreshToken = tokenStorage.getRefreshToken();
  if (!refreshToken) {
    throw new Error("No refresh token available");
  }
  const response = await fetch(`${BASE_URL}/api/v1/auth/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: refreshToken }),
  });
  if (!response.ok) {
    throw new Error("Refresh failed");
  }
  const data = (await response.json()) as { access_token: string; refresh_token: string };
  tokenStorage.setTokens(data.access_token, data.refresh_token);
  return data.access_token;
}

const refreshMiddleware: Middleware = {
  async onResponse({ request, response }) {
    const isAuthEndpoint = request.url.includes("/auth/login") || request.url.includes("/auth/refresh");
    if (response.status !== 401 || isAuthEndpoint) {
      return response;
    }

    try {
      refreshPromise ??= refreshAccessTokenViaFetch().finally(() => {
        refreshPromise = null;
      });
      const newAccessToken = await refreshPromise;

      const retriedRequest = request.clone();
      retriedRequest.headers.set("Authorization", `Bearer ${newAccessToken}`);
      return fetch(retriedRequest);
    } catch {
      tokenStorage.clear();
      onSessionExpired?.();
      return response;
    }
  },
};

api.use(authMiddleware);
api.use(refreshMiddleware);
