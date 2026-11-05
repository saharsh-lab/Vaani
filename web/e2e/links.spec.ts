import { expect, test, type Page } from "@playwright/test";

import { OWNER, signIn } from "./helpers";

const PUBLIC = ["/", "/c/sri-dental", "/login", "/signup", "/privacy", "/terms", "/no-such-page"];
const DASHBOARD = [
  "/dashboard",
  "/dashboard/bookings",
  "/dashboard/handoffs",
  "/dashboard/conversations",
  "/dashboard/knowledge",
  "/dashboard/settings",
  "/dashboard/team",
  "/dashboard/channels",
];

async function linksOn(page: Page, path: string): Promise<string[]> {
  await page.goto(path);
  await page.waitForLoadState("networkidle");
  return page.$$eval("a[href]", (anchors) => anchors.map((a) => (a as HTMLAnchorElement).href));
}

async function checkAll(page: Page, paths: string[]) {
  const found = new Map<string, string>(); // link -> page it was on
  for (const path of paths) for (const href of await linksOn(page, path)) if (!found.has(href)) found.set(href, path);
  const broken: string[] = [];
  for (const [href, from] of found) {
    if (href.startsWith("mailto:") || href.startsWith("tel:")) {
      expect(href, `on ${from}`).toMatch(/^(mailto:\S+@\S+\.\S+|tel:\+\d{8,15})$/);
      continue;
    }
    const url = new URL(href);
    url.hash = "";
    const status = (await page.request.get(url.toString())).status();
    if (status >= 400) broken.push(`${href} (on ${from}): ${status}`);
  }
  expect(broken, "broken links").toEqual([]);
  expect(found.size).toBeGreaterThan(5);
}

test("no broken links on the public pages", async ({ page }) => {
  await checkAll(page, PUBLIC);
});

test("no broken links in the dashboard", async ({ page }) => {
  await signIn(page, OWNER);
  await checkAll(page, DASHBOARD);
});
