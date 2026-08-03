import createClient, { type Middleware } from "openapi-fetch";

import type { paths } from "@/api/generated/schema";
import { accessTokenStore } from "@/lib/accessTokenStore";

// VITE_API_BASE_URL includes the "/api/v1" prefix (used by the hand-written
// axios client in lib/apiClient.ts), but the generated `paths` keys already
// embed that same prefix (they're the FastAPI app's literal route paths) —
// so this client's baseUrl must be just the origin, or every request would
// double up on "/api/v1".
const BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000/api/v1").replace(
  /\/api\/v1\/?$/,
  "",
);

// `credentials: "include"` is required so the browser attaches the
// HttpOnly refresh_token cookie to requests (and stores it from Set-Cookie
// on login/refresh responses) — mirrors lib/apiClient.ts's
// `withCredentials: true`. Without it, this client would never see the
// cookie regardless of what the backend sets.
export const api = createClient<paths>({ baseUrl: BASE_URL, credentials: "include" });

let onSessionExpired: (() => void) | null = null;
export function registerApiSessionExpiredHandler(handler: () => void): void {
  onSessionExpired = handler;
}

const authMiddleware: Middleware = {
  async onRequest({ request }) {
    const token = accessTokenStore.get();
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
  // No request body — the refresh token is the HttpOnly cookie the browser
  // attaches automatically via `credentials: "include"`.
  const response = await fetch(`${BASE_URL}/api/v1/auth/refresh`, {
    method: "POST",
    credentials: "include",
  });
  if (!response.ok) {
    throw new Error("Refresh failed");
  }
  const data = (await response.json()) as { access_token: string };
  accessTokenStore.set(data.access_token);
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
      return fetch(retriedRequest, { credentials: "include" });
    } catch {
      accessTokenStore.clear();
      onSessionExpired?.();
      return response;
    }
  },
};

api.use(authMiddleware);
api.use(refreshMiddleware);
