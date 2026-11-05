import { expect, test } from "@playwright/test";

import { expectNoSideScroll, nextOpenDay, OWNER, signIn } from "./helpers";

const PAGES = [
  { link: "Overview", heading: /Good to see you/ },
  { link: "Bookings", heading: "Bookings" },
  { link: "Callbacks", heading: "Callbacks" },
  { link: "Conversations", heading: "Conversations" },
  { link: "Knowledge base", heading: "Knowledge base" },
  { link: "Settings", heading: "Settings" },
  { link: "Team", heading: "Team" },
  { link: "Channels", heading: "Channels" },
];

test.beforeEach(async ({ page }) => {
  await signIn(page, OWNER);
});

test("every menu link opens its page, without errors, on a phone too @phone", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  for (const { link, heading } of PAGES) {
    await page.getByRole("navigation").first().getByRole("link", { name: link }).click();
    await expect(page.getByRole("heading", { level: 1, name: heading })).toBeVisible();
    await expect(page.getByRole("main").getByRole("alert")).toHaveCount(0);
    await expectNoSideScroll(page);
  }
  expect(errors).toEqual([]);
});

test("a conversation opens from the list", async ({ page }) => {
  await page.goto("/dashboard/conversations");
  await page.locator('a[href^="/dashboard/conversations/"]').first().click();
  await expect(page).toHaveURL(/\/dashboard\/conversations\/[0-9a-f-]{36}$/);
  await expect(page.getByRole("main").getByRole("alert")).toHaveCount(0);
});

test("adding a booking checks the number, then books it", async ({ page }) => {
  await page.goto("/dashboard/bookings");
  await page.getByRole("button", { name: "New booking" }).click();
  const dialog = page.getByRole("dialog", { name: "New booking" });
  await dialog.getByLabel("Date").fill(nextOpenDay(4));
  await dialog.getByLabel("Time").fill("11:15");
  await dialog.getByLabel("Customer name").fill("Walk-in Ravi");
  await dialog.getByLabel("Mobile number").fill("98765");
  await dialog.getByRole("button", { name: "Book" }).click();
  await expect(dialog.getByText("Enter a 10-digit mobile number, like 98765 43210.")).toBeVisible();

  await dialog.getByLabel("Mobile number").fill("98765 43210");
  await dialog.getByRole("button", { name: "Book" }).click();
  await expect(page.getByText(/^Booked for /)).toBeVisible();
  await expect(dialog).toBeHidden();
});

test("a knowledge base answer can be added, then deleted", async ({ page }) => {
  await page.goto("/dashboard/knowledge");
  await page.getByRole("button", { name: "Add answer" }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByRole("button", { name: "Save" }).click();
  await expect(dialog.getByText("This is required.")).toHaveCount(2);

  await dialog.getByLabel("Topic").fill("Wheelchair access");
  await dialog.getByLabel("Question and answer").fill("Q: Is there a ramp? A: Yes, at the side entrance.");
  await dialog.getByRole("button", { name: "Save" }).click();
  await expect(page.getByText("Saved. Vaani will use it from the next conversation.")).toBeVisible();
  await expect(page.getByText("Wheelchair access")).toBeVisible();

  page.once("dialog", (d) => d.accept());
  await page.getByRole("button", { name: "Delete Wheelchair access" }).click();
  await expect(page.getByText("Wheelchair access")).toHaveCount(0);
});

test("business settings check the phone number before saving", async ({ page }) => {
  await page.goto("/dashboard/settings");
  const phone = page.getByLabel("Phone", { exact: true });
  await phone.fill("call us");
  const save = page.getByRole("button", { name: "Save", exact: true }).first();
  await save.click();
  await expect(page.getByText("Enter a phone number, like 040 2345 6789 or +91 98765 43210.")).toBeVisible();
  await phone.fill("040 2345 6789");
  await save.click();
  await expect(page.getByText("Saved", { exact: true })).toBeVisible();
});

test("days off can't end before they start", async ({ page }) => {
  await page.goto("/dashboard/settings");
  await page.getByRole("tab", { name: "Days off" }).click();
  const form = page.locator("form").filter({ has: page.getByLabel("From") });
  await form.getByLabel("From").fill(nextOpenDay(10));
  await form.getByLabel("To (optional)").fill(nextOpenDay(1));
  await form.getByRole("button", { name: /Add/ }).click();
  await expect(form.getByText("The last day can't be before the first.")).toBeVisible();
});

test("adding a team member checks the fields", async ({ page }) => {
  await page.goto("/dashboard/team");
  await page.getByRole("button", { name: "Add person" }).click();
  const dialog = page.getByRole("dialog", { name: "Add a person" });
  await dialog.getByRole("button", { name: "Add" }).click();
  await expect(dialog.getByText("This is required.")).toHaveCount(3);
  await dialog.getByLabel("Name").fill("Kiran");
  await dialog.getByLabel("Email").fill("kiran@sri-dental.example.com");
  await dialog.getByLabel("Temporary password").fill("short");
  await dialog.getByRole("button", { name: "Add" }).click();
  await expect(dialog.getByText("Use at least 8 characters.")).toBeVisible();
  await dialog.getByLabel("Temporary password").fill("kiran-temp-password");
  await dialog.getByRole("button", { name: "Add" }).click();
  await expect(page.getByText("Added. Share the email and temporary password with them privately.")).toBeVisible();
});

test("change password is reachable on a phone, and checks the new password @phone", async ({ page }) => {
  await page.getByRole("button", { name: "Change password" }).filter({ visible: true }).click();
  const dialog = page.getByRole("dialog", { name: "Change password" });
  await dialog.getByLabel("Current password").fill(OWNER.password);
  await dialog.getByLabel("New password", { exact: true }).fill("new-password-1");
  await dialog.getByLabel("New password again").fill("new-password-2");
  await dialog.getByRole("button", { name: "Change password" }).click();
  await expect(dialog.locator("form").getByRole("alert")).toHaveText("The new passwords don't match");
});

test("the channels page links to the booking page and the talk-to-us page", async ({ page, context }) => {
  await page.goto("/dashboard/channels");
  const [booking] = await Promise.all([context.waitForEvent("page"), page.getByRole("link", { name: "Open" }).click()]);
  await expect(booking.getByRole("heading", { name: "Sri Dental Clinic" })).toBeVisible();
  const talk = await page.getByRole("link", { name: "Try it" }).getAttribute("href");
  expect((await page.request.get(talk!)).status()).toBe(200);
});
