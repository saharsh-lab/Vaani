import { expect, type Page } from "@playwright/test";

export const API = "http://localhost:8100";
export const OWNER = { email: "owner@sri-dental.example.com", password: "vaani-demo-owner" };
export const STAFF = { email: "staff@sri-dental.example.com", password: "vaani-demo-staff" };

export async function signIn(page: Page, who: { email: string; password: string }) {
  await page.goto("/login");
  await page.getByLabel("Email").fill(who.email);
  await page.getByLabel("Password").fill(who.password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/dashboard/);
}

/** Nothing sticks out sideways: the page fits the screen without scrolling left and right. */
export async function expectNoSideScroll(page: Page) {
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow, "page is wider than the screen").toBeLessThanOrEqual(0);
}

/** YYYY-MM-DD in India, n days from today. */
export function istDay(n = 0): string {
  const now = new Date(Date.now() + n * 86_400_000);
  return new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Kolkata" }).format(now);
}

/** The next day the demo clinic is open (it closes on Sundays), at least `from` days ahead. */
export function nextOpenDay(from = 1): string {
  for (let n = from; ; n++) {
    const day = istDay(n);
    if (new Date(`${day}T12:00:00Z`).getUTCDay() !== 0) return day;
  }
}
