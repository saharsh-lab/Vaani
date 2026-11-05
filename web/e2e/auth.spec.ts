import { expect, test } from "@playwright/test";

import { expectNoSideScroll, OWNER, signIn, STAFF } from "./helpers";

test("the dashboard needs a sign-in, and returns you to the page you wanted", async ({ page }) => {
  await page.goto("/dashboard/bookings");
  await expect(page).toHaveURL("/login?next=%2Fdashboard%2Fbookings");
  await page.getByLabel("Email").fill(OWNER.email);
  await page.getByLabel("Password").fill(OWNER.password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL("/dashboard/bookings");
});

test("sign-in checks the form, then the password @phone", async ({ page }) => {
  await page.goto("/login");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByText("This is required.")).toHaveCount(2);
  await expect(page.getByLabel("Email")).toBeFocused();

  await page.getByLabel("Email").fill("owner-at-example");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByText("Enter an email address, like name@example.com.")).toBeVisible();

  await page.getByLabel("Email").fill(OWNER.email);
  await page.getByLabel("Password").fill("not-the-password");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.locator("form").getByRole("alert")).toHaveText("Wrong email or password");
  await expectNoSideScroll(page);

  await page.getByLabel("Password").fill(OWNER.password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: /Good to see you/ })).toBeVisible();
});

test("staff only see bookings and callbacks", async ({ page }) => {
  await signIn(page, STAFF);
  await expect(page).toHaveURL("/dashboard/bookings");
  const nav = page.getByRole("navigation").first();
  await expect(nav.getByRole("link")).toHaveText([/Bookings/, /Callbacks/]);
  await page.goto("/dashboard/settings");
  await expect(page.getByText("Only the business owner can see this page.")).toBeVisible();
});

test("signing up checks every field, then creates the business @phone", async ({ page }) => {
  await page.goto("/signup");
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page.getByText("This is required.")).toHaveCount(5);
  await expect(page.getByLabel("Business name")).toBeFocused();

  const unique = Date.now().toString(36);
  await page.getByLabel("Business name").fill(`Glow Salon ${unique}`);
  await page.getByLabel("Type of business").fill("salon");
  await page.getByLabel("Your name").fill("Meena");
  await page.getByLabel("Email").fill(`meena-${unique}@example.com`);
  await page.getByLabel("Password").fill("short");
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page.getByText("Use at least 8 characters.")).toBeVisible();
  await expect(page.getByText("This is required.")).toHaveCount(0);

  const consent = page.locator("form");
  await expect(consent.getByRole("link", { name: "terms of service" })).toHaveAttribute("href", "/terms");
  await expect(consent.getByRole("link", { name: "privacy policy" })).toHaveAttribute("href", "/privacy");

  await page.getByLabel("Password").fill("a-good-long-password");
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page.getByRole("heading", { name: "Good to see you, Meena" })).toBeVisible();
  await expect(page.getByText(`Glow Salon ${unique}`).first()).toBeVisible();
});

test("signing out ends the session", async ({ page }) => {
  await signIn(page, OWNER);
  await page.getByRole("button", { name: "Sign out" }).filter({ visible: true }).click();
  await expect(page).toHaveURL("/login");
  await page.goto("/dashboard");
  await expect(page).toHaveURL(/\/login/);
});
