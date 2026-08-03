import createClient, { type Middleware } from "openapi-fetch";

import type { paths } from "@/api/generated/schema";

// VITE_API_BASE_URL includes the "/api/v1" prefix (used by the hand-written
// axios client in lib/apiClient.ts), but the generated `paths` keys already
// embed that same prefix (they're the FastAPI app's literal route paths) â€”
// so this client's baseUrl must be just the origin, or every request would
// double up on "/api/v1".
const BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000/api/v1").replace(
  /\/api\/v1\/?$/,
  "",
);

export const api = createClient<paths>({
  baseUrl: BASE_URL,
  fetch: (request: Request) => fetch(request, { credentials: "include" }),
});

let onSessionExpired: (() => void) | null = null;
export function registerApiSessionExpiredHandler(handler: () => void): void {
  onSessionExpired = handler;
}

const authMiddleware: Middleware = {
  async onRequest({ request }) {
    return request;
  },
};

// Mirrors lib/apiClient.ts's refresh-on-401 behavior: concurrent 401s share
// a single in-flight refresh instead of each racing to rotate the token.
let refreshPromise: Promise<string> | null = null;

async function refreshAccessTokenViaFetch(): Promise<string> {
  const response = await fetch(`${BASE_URL}/api/v1/auth/refresh`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({}),
  });
  if (!response.ok) {
    throw new Error("Refresh failed");
  }
  return "cookie";
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
      await refreshPromise;

      const retriedRequest = request.clone();
      return fetch(retriedRequest);
    } catch {
      onSessionExpired?.();
      return response;
    }
  },
};

api.use(authMiddleware);
api.use(refreshMiddleware);
