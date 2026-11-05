import { expect, test } from "@playwright/test";

import { request as httpRequest } from "node:http";

import { MOBILE_PATTERN, PHONE_PATTERN } from "../src/lib/validation";
import { expectNoSideScroll } from "./helpers";

/** A raw request, so the Host header can be set (as a proxy in front of the site would). */
function rawGet(path: string, headers: Record<string, string>): Promise<{ status: number; location?: string }> {
  return new Promise((resolve, reject) => {
    httpRequest({ host: "localhost", port: 3100, path, headers }, (res) => {
      res.resume();
      resolve({ status: res.statusCode ?? 0, location: res.headers.location });
    })
      .on("error", reject)
      .end();
  });
}

const PUBLIC_PAGES = [
  { path: "/", heading: "Never miss a customer because the phone was busy." },
  { path: "/c/sri-dental", heading: "Sri Dental Clinic" },
  { path: "/login", heading: "Sign in" },
  { path: "/signup", heading: "Set up your business" },
  { path: "/privacy", heading: "Privacy policy" },
  { path: "/terms", heading: "Terms of service" },
];

for (const { path, heading } of PUBLIC_PAGES) {
  test(`${path} has a title, description, sharing image and fits a phone @phone`, async ({ page }) => {
    const response = await page.goto(path);
    expect(response?.status()).toBe(200);
    await expect(page.getByText(heading, { exact: true }).first()).toBeVisible();

    await expect(page).toHaveTitle(/\S{3,}/);
    const description = await page.locator('meta[name="description"]').getAttribute("content");
    expect(description?.length ?? 0, "meta description length").toBeGreaterThan(50);
    expect(description?.length ?? 0, "meta description length").toBeLessThan(200);
    const image = await page.locator('meta[property="og:image"]').first().getAttribute("content");
    expect(image).toMatch(/^http:\/\/localhost:3100\/(.+\/)?opengraph-image/);
    expect((await page.request.get(image!)).headers()["content-type"]).toBe("image/png");

    await expectNoSideScroll(page);
  });
}

test("each page has its own title", async ({ page }) => {
  const titles = new Set<string>();
  for (const { path } of PUBLIC_PAGES) {
    await page.goto(path);
    titles.add(await page.title());
  }
  expect(titles.size).toBe(PUBLIC_PAGES.length);
});

test("the clinic page is titled and previewed with the clinic's name", async ({ page }) => {
  await page.goto("/c/sri-dental");
  await expect(page).toHaveTitle("Sri Dental Clinic: book an appointment · Vaani");
  await expect(page.locator('link[rel="canonical"]')).toHaveAttribute("href", "http://localhost:3100/c/sri-dental");
  const image = await page.locator('meta[property="og:image"]').first().getAttribute("content");
  expect(image).toContain("/c/sri-dental/opengraph-image");
});

test("home page buttons and links go where they say", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("link", { name: "Set up your business" }).first().click();
  await expect(page).toHaveURL("/signup");

  await page.goto("/");
  await page.getByRole("link", { name: "See the demo clinic" }).click();
  await expect(page.getByRole("heading", { name: "Sri Dental Clinic" })).toBeVisible();

  await page.goto("/");
  await page.getByRole("banner").getByRole("link", { name: "Sign in" }).click();
  await expect(page).toHaveURL("/login");

  await page.goto("/");
  const footer = page.getByRole("contentinfo");
  await footer.getByRole("link", { name: "Privacy policy" }).click();
  await expect(page.getByRole("heading", { name: "Privacy policy" })).toBeVisible();
  await page.getByRole("contentinfo").getByRole("link", { name: "Terms of service" }).click();
  await expect(page.getByRole("heading", { name: "Terms of service" })).toBeVisible();
  await page.getByRole("banner").getByRole("link", { name: "Vaani" }).click();
  await expect(page).toHaveURL("/");

  const talk = page.getByRole("link", { name: /talk to the demo clinic/i });
  const voice = await page.request.get((await talk.getAttribute("href"))!);
  expect(voice.status()).toBe(200);
});

test("a missing page gets the 404 page, with a way back", async ({ page }) => {
  const response = await page.goto("/no-such-page");
  expect(response?.status()).toBe(404);
  await expect(page.getByRole("heading", { name: "This page doesn't exist" })).toBeVisible();
  await expect(page).toHaveTitle(/Page not found/);
  await page.getByRole("link", { name: "Go to the home page" }).click();
  await expect(page).toHaveURL("/");
});

test("an unknown clinic says so and links home", async ({ page }) => {
  await page.goto("/c/no-such-clinic");
  await expect(page.getByRole("heading", { name: "Page not found" })).toBeVisible();
  await page.getByRole("link", { name: "Go to the home page" }).click();
  await expect(page).toHaveURL("/");
});

test("robots.txt, sitemap, manifest and icons are served", async ({ request }) => {
  const robots = await (await request.get("/robots.txt")).text();
  expect(robots).toContain("Disallow: /dashboard");
  expect(robots).toContain("Sitemap: http://localhost:3100/sitemap.xml");

  const sitemap = await request.get("/sitemap.xml");
  expect(sitemap.headers()["content-type"]).toContain("xml");
  const urls = [...(await sitemap.text()).matchAll(/<loc>(.+?)<\/loc>/g)].map((m) => m[1]);
  expect(urls).toContain("http://localhost:3100/c/sri-dental");
  for (const url of urls) expect((await request.get(url)).status(), url).toBe(200);

  const manifest = await (await request.get("/manifest.webmanifest")).json();
  expect(manifest.name).toBe("Vaani");
  for (const icon of manifest.icons) expect((await request.get(icon.src)).status(), icon.src).toBe(200);

  for (const [path, type] of [
    ["/favicon.ico", "image/x-icon"],
    ["/icon.svg", "image/svg+xml"],
    ["/apple-icon", "image/png"],
    ["/opengraph-image", "image/png"],
    ["/c/sri-dental/opengraph-image", "image/png"],
  ]) {
    const r = await request.get(path);
    expect(r.status(), path).toBe(200);
    expect(r.headers()["content-type"], path).toContain(type);
  }
});

test("pages send security headers; the dashboard can't be framed but a booking page can", async ({ request }) => {
  const home = await request.get("/");
  expect(home.headers()["x-content-type-options"]).toBe("nosniff");
  expect(home.headers()["referrer-policy"]).toBe("strict-origin-when-cross-origin");
  expect(home.headers()["x-frame-options"]).toBe("DENY");
  expect(home.headers()["strict-transport-security"]).toContain("max-age=63072000");
  expect((await request.get("/c/sri-dental")).headers()["x-frame-options"]).toBeUndefined();
});

test("plain-HTTP requests behind a proxy are sent to HTTPS", async () => {
  const plain = await rawGet("/privacy?x=1", { host: "vaani.example", "x-forwarded-proto": "http" });
  expect(plain).toEqual({ status: 308, location: "https://vaani.example/privacy?x=1" });
  const secure = await rawGet("/privacy", { host: "vaani.example", "x-forwarded-proto": "https" });
  expect(secure.status).toBe(200);
});

test("the dashboard and the 404 page are kept out of search results", async ({ page, request }) => {
  await page.goto("/login");
  expect(await page.locator('meta[name="robots"]').count()).toBe(0);
  await page.goto("/no-such-page");
  await expect(page.locator('meta[name="robots"]').first()).toHaveAttribute("content", /noindex/);
  // Any cookie gets past the sign-in redirect; the page itself still needs a real session.
  const html = await (await request.get("/dashboard", { headers: { cookie: "vaani_session=x" } })).text();
  expect(html).toMatch(/<meta name="robots" content="noindex, nofollow"/);
});

test("form patterns compile the way browsers read them, and accept real numbers", () => {
  // A pattern that doesn't compile with the "v" flag is ignored by the browser: no check at all.
  const mobile = new RegExp(`^(?:${MOBILE_PATTERN})$`, "v");
  const phone = new RegExp(`^(?:${PHONE_PATTERN})$`, "v");
  for (const ok of ["9876543210", "98765 43210", "098765 43210", "+91 98765 43210", "+91-98765-43210", "+1 415 555 0123"])
    expect(mobile.test(ok), ok).toBe(true);
  for (const bad of ["12345", "1234567890", "call me", "98765 4321"]) expect(mobile.test(bad), bad).toBe(false);
  for (const ok of ["040 2345 6789", "+91 40 2345 6789", "(040) 23456789", "9876543210"]) expect(phone.test(ok), ok).toBe(true);
  for (const bad of ["call us", "123", "040-CALL-NOW"]) expect(phone.test(bad), bad).toBe(false);
});

test("link previews from WhatsApp and Telegram get the clinic's details in the first bytes", async ({ request }) => {
  for (const agent of ["WhatsApp/2.23.20.0", "TelegramBot (like TwitterBot)"]) {
    const html = await (await request.get("/c/sri-dental", { headers: { "user-agent": agent } })).text();
    const head = html.slice(0, html.indexOf("</head>"));
    expect(head, agent).toContain('<meta property="og:title" content="Sri Dental Clinic: book an appointment"/>');
    expect(head, agent).toContain("/c/sri-dental/opengraph-image");
  }
});
