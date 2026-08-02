import type { APIRequestContext, Page } from "@playwright/test";

export const API_BASE_URL = "http://localhost:8000/api/v1";

export function uniqueEmail(prefix: string): string {
  return `${prefix}_${Date.now()}_${Math.floor(Math.random() * 100000)}@example.com`;
}

export interface TestUser {
  email: string;
  password: string;
  firstName: string;
  lastName: string;
}

export function makeTestUser(prefix: string): TestUser {
  return {
    email: uniqueEmail(prefix),
    password: "StrongPass1",
    firstName: "Playwright",
    lastName: "Test",
  };
}

/**
 * Registers and logs in a fresh customer directly via the API (fast setup —
 * the UI registration/login flow itself is covered by its own dedicated
 * spec, so other specs that need "a logged-in customer" as a precondition
 * shouldn't re-drive that UI every time).
 */
export async function registerAndLoginViaApi(
  request: APIRequestContext,
  user: TestUser,
): Promise<{ accessToken: string; refreshToken: string; customerId: string }> {
  const registerResponse = await request.post(`${API_BASE_URL}/auth/register`, {
    data: {
      email: user.email,
      password: user.password,
      first_name: user.firstName,
      last_name: user.lastName,
      date_of_birth: "1992-05-15",
      phone_number: "+994501112233",
    },
  });
  if (!registerResponse.ok()) {
    throw new Error(`Registration failed: ${registerResponse.status()} ${await registerResponse.text()}`);
  }
  const registerBody = await registerResponse.json();

  const loginResponse = await request.post(`${API_BASE_URL}/auth/login`, {
    data: { email: user.email, password: user.password },
  });
  if (!loginResponse.ok()) {
    throw new Error(`Login failed: ${loginResponse.status()} ${await loginResponse.text()}`);
  }
  const loginBody = await loginResponse.json();
  return {
    accessToken: loginBody.access_token,
    refreshToken: loginBody.refresh_token,
    customerId: registerBody.customer.id,
  };
}

/**
 * Reads a just-triggered transfer's OTP via the test-only debug endpoint
 * (see backend/app/core/test_otp_store.py — only responds when the backend
 * is running with ENVIRONMENT=test; 404s otherwise). This is how these e2e
 * tests complete the OTP-confirmation step without a real SMS/email inbox.
 */
export async function readDebugOtp(
  request: APIRequestContext,
  accessToken: string,
  transactionId: string,
): Promise<string> {
  const response = await request.get(`${API_BASE_URL}/transactions/${transactionId}/debug-otp`, {
    headers: { Authorization: `Bearer ${accessToken}` },
  });
  if (!response.ok()) {
    throw new Error(
      `Could not read the debug OTP (status ${response.status()}) — is the backend running with ENVIRONMENT=test?`,
    );
  }
  const body = await response.json();
  return body.otp_code as string;
}

/**
 * Promotes a just-registered user to ADMIN via the test-only debug endpoint
 * (see backend/app/modules/auth/router.py — same ENVIRONMENT=test gating as
 * readDebugOtp). There is no other way to get an admin account in this
 * environment: registration always creates a CUSTOMER.
 */
export async function promoteToAdminViaApi(
  request: APIRequestContext,
  accessToken: string,
): Promise<void> {
  const response = await request.post(`${API_BASE_URL}/auth/debug-promote-to-admin`, {
    headers: { Authorization: `Bearer ${accessToken}` },
  });
  if (!response.ok()) {
    throw new Error(
      `Could not promote to admin (status ${response.status()}) — is the backend running with ENVIRONMENT=test?`,
    );
  }
}

export async function createActiveAccountViaApi(
  request: APIRequestContext,
  adminAccessToken: string,
  customerId: string,
  currency = "AZN",
): Promise<{ id: string; account_number: string }> {
  const response = await request.post(`${API_BASE_URL}/admin/accounts`, {
    headers: { Authorization: `Bearer ${adminAccessToken}` },
    data: { customer_id: customerId, account_type: "CHECKING", currency },
  });
  if (!response.ok()) {
    throw new Error(`Account creation failed: ${response.status()} ${await response.text()}`);
  }
  // Admin-created accounts are ACTIVE by default already (see
  // AdminService.create_account) — nothing further needed here.
  return response.json();
}

/**
 * Seeds a starting balance via the test-only debug endpoint (see
 * backend/app/modules/admin/router.py). There is no real "deposit" feature
 * in this closed-loop system — money only enters via a transfer from
 * another of its own accounts — so fixture setup needs this escape hatch.
 */
export async function setAccountBalanceViaApi(
  request: APIRequestContext,
  adminAccessToken: string,
  accountId: string,
  amount: string,
): Promise<void> {
  const response = await request.post(
    `${API_BASE_URL}/admin/accounts/${accountId}/debug-set-balance?amount=${amount}`,
    { headers: { Authorization: `Bearer ${adminAccessToken}` } },
  );
  if (!response.ok()) {
    throw new Error(
      `Could not seed balance (status ${response.status()}) — is the backend running with ENVIRONMENT=test?`,
    );
  }
}

/**
 * Injects an already-obtained access/refresh token pair into the browser's
 * localStorage, matching lib/tokenStorage.ts's key names exactly. Lets tests
 * that only care about "a logged-in customer sees X" skip re-driving the
 * login form (which has its own dedicated coverage in auth.spec.ts).
 */
export async function injectSession(page: Page, accessToken: string, refreshToken: string): Promise<void> {
  await page.addInitScript(
    ([access, refresh]) => {
      window.localStorage.setItem("banking.access_token", access);
      window.localStorage.setItem("banking.refresh_token", refresh);
    },
    [accessToken, refreshToken],
  );
}
