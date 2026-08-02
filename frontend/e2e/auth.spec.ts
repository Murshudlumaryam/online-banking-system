import { expect, test } from "@playwright/test";

import { makeTestUser } from "./helpers";

test.describe("Authentication", () => {
  test("a new customer can register, land on the dashboard, and log out", async ({ page }) => {
    const user = makeTestUser("e2e_register");

    await page.goto("/register");
    await page.getByLabel("First name").fill(user.firstName);
    await page.getByLabel("Last name").fill(user.lastName);
    await page.getByLabel("Email").fill(user.email);
    await page.getByLabel("Password").fill(user.password);
    await page.getByLabel("Date of birth").fill("1992-05-15");
    await page.getByLabel("Phone number").fill("+994501112233");
    await page.getByRole("button", { name: "Create account" }).click();

    // Registration logs the customer straight in and lands on the dashboard.
    await expect(page).toHaveURL(/\/app\/dashboard/);
    await expect(page.getByText(user.firstName, { exact: false })).toBeVisible();

    await page.getByRole("button", { name: "Sign out" }).click();
    await expect(page).toHaveURL(/\/login/);
  });

  test("an existing customer can log in and see their dashboard", async ({ page }) => {
    const user = makeTestUser("e2e_login");

    // Register first via the UI so this test is fully self-contained.
    await page.goto("/register");
    await page.getByLabel("First name").fill(user.firstName);
    await page.getByLabel("Last name").fill(user.lastName);
    await page.getByLabel("Email").fill(user.email);
    await page.getByLabel("Password").fill(user.password);
    await page.getByLabel("Date of birth").fill("1992-05-15");
    await page.getByLabel("Phone number").fill("+994501112233");
    await page.getByRole("button", { name: "Create account" }).click();
    await expect(page).toHaveURL(/\/app\/dashboard/);
    await page.getByRole("button", { name: "Sign out" }).click();

    await page.goto("/login");
    await page.getByLabel("Email").fill(user.email);
    await page.getByLabel("Password").fill(user.password);
    await page.getByRole("button", { name: "Sign in" }).click();

    await expect(page).toHaveURL(/\/app\/dashboard/);
  });

  test("shows an error for the wrong password", async ({ page }) => {
    const user = makeTestUser("e2e_wrongpass");

    await page.goto("/register");
    await page.getByLabel("First name").fill(user.firstName);
    await page.getByLabel("Last name").fill(user.lastName);
    await page.getByLabel("Email").fill(user.email);
    await page.getByLabel("Password").fill(user.password);
    await page.getByLabel("Date of birth").fill("1992-05-15");
    await page.getByLabel("Phone number").fill("+994501112233");
    await page.getByRole("button", { name: "Create account" }).click();
    await expect(page).toHaveURL(/\/app\/dashboard/);
    await page.getByRole("button", { name: "Sign out" }).click();

    await page.goto("/login");
    await page.getByLabel("Email").fill(user.email);
    await page.getByLabel("Password").fill("DefinitelyWrongPass1");
    await page.getByRole("button", { name: "Sign in" }).click();

    await expect(page.getByRole("alert")).toContainText(/incorrect/i);
    await expect(page).toHaveURL(/\/login/);
  });

  test("redirects an unauthenticated visitor away from a protected page", async ({ page }) => {
    await page.goto("/app/dashboard");
    await expect(page).toHaveURL(/\/login/);
  });
});
