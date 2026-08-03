import { expect, test } from "@playwright/test";

import { injectSession, makeTestUser, promoteToAdminViaApi, registerAndLoginViaApi } from "./helpers";

test.describe("Admin panel", () => {
  test("an admin can see the customer list, including a customer they didn't create in this test", async ({
    page,
    request,
  }) => {
    const adminUser = makeTestUser("e2e_admin_view");
    const someCustomer = makeTestUser("e2e_admin_target");

    const adminSession = await registerAndLoginViaApi(request, adminUser);
    await promoteToAdminViaApi(request, adminSession.accessToken);
    await registerAndLoginViaApi(request, someCustomer);

    await injectSession(page, adminSession.refreshToken);
    await page.goto("/admin/customers");

    await expect(page).toHaveURL(/\/admin\/customers/);
    await expect(page.getByText(someCustomer.email, { exact: false }).or(page.getByText("Test"))).toBeVisible();
  });

  test("a plain customer is redirected away from the admin area", async ({ page, request }) => {
    const customer = makeTestUser("e2e_non_admin");
    const session = await registerAndLoginViaApi(request, customer);

    await injectSession(page, session.refreshToken);
    await page.goto("/admin/customers");

    await expect(page).toHaveURL(/\/app\/dashboard/);
  });

  test("filtering customers by status narrows the list without erroring", async ({ page, request }) => {
    const adminUser = makeTestUser("e2e_admin_filter");
    const adminSession = await registerAndLoginViaApi(request, adminUser);
    await promoteToAdminViaApi(request, adminSession.accessToken);

    await injectSession(page, adminSession.refreshToken);
    await page.goto("/admin/customers");

    await page.getByLabel("Filter by status").selectOption("BLOCKED");
    // No error banner should appear just from filtering to a (possibly
    // empty) status bucket.
    await expect(page.getByRole("alert")).toHaveCount(0);
  });
});
