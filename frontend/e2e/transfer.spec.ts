import { expect, test } from "@playwright/test";

import {
  createActiveAccountViaApi,
  injectSession,
  makeTestUser,
  promoteToAdminViaApi,
  readDebugOtp,
  registerAndLoginViaApi,
  setAccountBalanceViaApi,
} from "./helpers";

test.describe("Money transfer", () => {
  test("a customer can send money end-to-end, including real OTP confirmation", async ({ page, request }) => {
    // --- Fixture setup via API (fast) — the UI-driven part of this test is
    // the transfer itself, not the account provisioning around it. ---
    const sender = makeTestUser("e2e_sender");
    const receiver = makeTestUser("e2e_receiver");
    const adminUser = makeTestUser("e2e_admin_for_transfer");

    const senderSession = await registerAndLoginViaApi(request, sender);
    const receiverSession = await registerAndLoginViaApi(request, receiver);
    const adminSession = await registerAndLoginViaApi(request, adminUser);
    await promoteToAdminViaApi(request, adminSession.accessToken);

    const senderAccount = await createActiveAccountViaApi(request, adminSession.accessToken, senderSession.customerId);
    const receiverAccount = await createActiveAccountViaApi(
      request,
      adminSession.accessToken,
      receiverSession.customerId,
    );
    await setAccountBalanceViaApi(request, adminSession.accessToken, senderAccount.id, "500.00");

    // --- The actual UI-driven part: sign in as the sender and send money. ---
    await injectSession(page, senderSession.refreshToken);
    await page.goto("/app/transfer");

    await page.getByLabel("From account").selectOption(senderAccount.id);
    await page.getByLabel("Receiver account number").fill(receiverAccount.account_number);
    await page.getByLabel(/amount/i).fill("125.00");
    await page.getByRole("button", { name: "Continue" }).click();

    // The OTP modal should appear with the transaction's reference number.
    const modal = page.getByRole("dialog");
    await expect(modal).toBeVisible();
    await expect(modal).toContainText("TXN-");

    // Extract the reference number so we can look up the transaction id via
    // the API (the debug-OTP endpoint needs the transaction id, which isn't
    // itself shown in the UI — only the human-readable reference is).
    const modalText = (await modal.textContent()) ?? "";
    const referenceMatch = modalText.match(/TXN-[A-F0-9]+/);
    expect(referenceMatch).not.toBeNull();
    const referenceNumber = referenceMatch![0];

    const searchResponse = await request.get(
      `http://localhost:8000/api/v1/transactions/search?reference=${referenceNumber}`,
      { headers: { Authorization: `Bearer ${senderSession.accessToken}` } },
    );
    expect(searchResponse.ok()).toBeTruthy();
    const transaction = await searchResponse.json();

    const otpCode = await readDebugOtp(request, senderSession.accessToken, transaction.id);

    await page.getByLabel(/one-time code/i).fill(otpCode);
    await page.getByRole("button", { name: /confirm transfer/i }).click();

    await expect(page.getByText(/completed successfully/i)).toBeVisible();
    await expect(modal).not.toBeVisible();
  });

  test("shows a clear error when the OTP code is wrong", async ({ page, request }) => {
    const sender = makeTestUser("e2e_wrongotp_sender");
    const receiver = makeTestUser("e2e_wrongotp_receiver");
    const adminUser = makeTestUser("e2e_admin_for_wrongotp");

    const senderSession = await registerAndLoginViaApi(request, sender);
    const receiverSession = await registerAndLoginViaApi(request, receiver);
    const adminSession = await registerAndLoginViaApi(request, adminUser);
    await promoteToAdminViaApi(request, adminSession.accessToken);

    const senderAccount = await createActiveAccountViaApi(request, adminSession.accessToken, senderSession.customerId);
    const receiverAccount = await createActiveAccountViaApi(
      request,
      adminSession.accessToken,
      receiverSession.customerId,
    );
    await setAccountBalanceViaApi(request, adminSession.accessToken, senderAccount.id, "200.00");

    await injectSession(page, senderSession.refreshToken);
    await page.goto("/app/transfer");

    await page.getByLabel("From account").selectOption(senderAccount.id);
    await page.getByLabel("Receiver account number").fill(receiverAccount.account_number);
    await page.getByLabel(/amount/i).fill("10.00");
    await page.getByRole("button", { name: "Continue" }).click();

    const modal = page.getByRole("dialog");
    await expect(modal).toBeVisible();

    await page.getByLabel(/one-time code/i).fill("000000");
    await page.getByRole("button", { name: /confirm transfer/i }).click();

    await expect(modal.getByRole("alert")).toContainText(/incorrect/i);
    // The modal must stay open so the customer can try again — a wrong
    // guess isn't a reason to make them restart the whole transfer.
    await expect(modal).toBeVisible();
  });

  test("rejects a transfer that exceeds the available balance", async ({ page, request }) => {
    const sender = makeTestUser("e2e_insufficient_sender");
    const receiver = makeTestUser("e2e_insufficient_receiver");
    const adminUser = makeTestUser("e2e_admin_for_insufficient");

    const senderSession = await registerAndLoginViaApi(request, sender);
    const receiverSession = await registerAndLoginViaApi(request, receiver);
    const adminSession = await registerAndLoginViaApi(request, adminUser);
    await promoteToAdminViaApi(request, adminSession.accessToken);

    const senderAccount = await createActiveAccountViaApi(request, adminSession.accessToken, senderSession.customerId);
    const receiverAccount = await createActiveAccountViaApi(
      request,
      adminSession.accessToken,
      receiverSession.customerId,
    );
    await setAccountBalanceViaApi(request, adminSession.accessToken, senderAccount.id, "5.00");

    await injectSession(page, senderSession.refreshToken);
    await page.goto("/app/transfer");

    await page.getByLabel("From account").selectOption(senderAccount.id);
    await page.getByLabel("Receiver account number").fill(receiverAccount.account_number);
    await page.getByLabel(/amount/i).fill("999.00");
    await page.getByRole("button", { name: "Continue" }).click();

    await expect(page.getByRole("alert")).toContainText(/balance/i);
    await expect(page.getByRole("dialog")).not.toBeVisible();
  });
});
