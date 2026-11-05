import { expect, test, type Page } from "@playwright/test";

import { API, expectNoSideScroll, nextOpenDay } from "./helpers";

function shortDate(day: string): string {
  const [y, m, d] = day.split("-").map(Number);
  return new Intl.DateTimeFormat("en-IN", { day: "numeric", month: "short", timeZone: "UTC" }).format(
    new Date(Date.UTC(y, m - 1, d)),
  );
}

/** A day chip's name ends with its date: "Sat 7 Nov" (and not "Tue 17 Nov"). */
function dayName(day: string): RegExp {
  return new RegExp(`\\s${shortDate(day)}$`);
}

/** Choose a service and a day, and return the first free time's button. */
async function pickTime(page: Page, service: string, day: string, nth = 0) {
  await page.goto("/c/sri-dental");
  await page.getByRole("button", { name: new RegExp(`^${service}`) }).click();
  await page.getByRole("button", { name: dayName(day) }).click();
  const times = page.getByRole("group", { name: "Free times" }).getByRole("button");
  await expect(times.first()).toBeVisible();
  const time = times.nth(nth);
  const label = (await time.innerText()).trim();
  await time.click();
  return label;
}

test("booking a free time, with the form checked first @phone", async ({ page }) => {
  const day = nextOpenDay(2);
  const time = await pickTime(page, "General consultation", day);

  // Nothing filled in: each field says what's missing, and nothing is sent.
  await page.getByRole("button", { name: "Confirm booking" }).click();
  await expect(page.getByText("This is required.")).toHaveCount(2);
  await expect(page.getByLabel("Patient's name")).toBeFocused();
  await expect(page.getByLabel("Patient's name")).toHaveAttribute("aria-invalid", "true");

  await page.getByLabel("Patient's name").fill("Asha Rao");
  await page.getByLabel("Mobile number").fill("12345");
  await page.getByRole("button", { name: "Confirm booking" }).click();
  await expect(page.getByText("Enter a 10-digit mobile number, like 98765 43210.")).toBeVisible();
  await expect(page.getByText("This is required.")).toHaveCount(0);

  await page.getByLabel("Mobile number").fill("+91 98480 12345");
  await expect(page.getByText("Enter a 10-digit mobile number")).toHaveCount(0);
  await expectNoSideScroll(page);
  await page.getByRole("button", { name: "Confirm booking" }).click();

  await expect(page.getByRole("heading", { name: "You're booked" })).toBeVisible();
  const confirmation = page.locator("#book");
  await expect(confirmation.getByText("General consultation")).toBeVisible();
  await expect(confirmation.getByText(new RegExp(time, "i"))).toBeVisible();

  // The time is gone for the next person.
  await page.getByRole("button", { name: "Book another appointment" }).click();
  await page.getByRole("button", { name: /^General consultation/ }).click();
  await page.getByRole("button", { name: dayName(day) }).click();
  await expect(page.getByRole("group", { name: "Free times" }).getByRole("button").first()).toBeVisible();
  await expect(page.getByRole("group", { name: "Free times" }).getByRole("button", { name: time, exact: true })).toHaveCount(0);
});

test("a time someone else just took is refused, and the times refresh", async ({ page }) => {
  const day = nextOpenDay(3);
  const time = await pickTime(page, "Teeth cleaning", day);
  const free = await (await page.request.get(`${API}/v1/public/sri-dental/slots?service=Teeth%20cleaning&date=${day}`)).json();
  const taken = await page.request.post(`${API}/v1/public/sri-dental/bookings`, {
    data: { service: "Teeth cleaning", start_at: free.slots[0].start_at, customer_name: "Someone", phone: "9000000002" },
  });
  expect(taken.status()).toBe(201);

  await page.getByLabel("Patient's name").fill("Asha Rao");
  await page.getByLabel("Mobile number").fill("98480 12345");
  await page.getByRole("button", { name: "Confirm booking" }).click();
  await expect(page.getByText("Someone just booked that time. Please pick another.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Confirm booking" })).toHaveCount(0);
  await expect(page.getByRole("group", { name: "Free times" }).getByRole("button", { name: time, exact: true })).toHaveCount(0);
});

test("closed days can't be picked, and services show prices", async ({ page }) => {
  await page.goto("/c/sri-dental");
  await expect(page.getByRole("button", { name: /^RCT consultation\s*30 min · ₹500/ })).toBeVisible();
  const days = page.getByRole("group", { name: "Days" }).getByRole("button");
  const labels = await days.allInnerTexts();
  const sundays = labels.map((l, i) => [l, i] as const).filter(([l]) => l.startsWith("Sun"));
  expect(sundays.length).toBeGreaterThan(0);
  for (const [, i] of sundays) await expect(days.nth(i)).toBeDisabled();
  await expect(page.getByText("Choose a service to see free times.")).toBeVisible();
});

test("the header buttons work", async ({ page }) => {
  await page.goto("/c/sri-dental");
  await page.getByRole("link", { name: "Book an appointment" }).click();
  await expect(page).toHaveURL(/#book$/);
  const talk = await page.getByRole("link", { name: "Talk to us" }).getAttribute("href");
  expect((await page.request.get(talk!)).status()).toBe(200);
  const phone = await page.getByRole("link", { name: "+91 40 2345 6789" }).getAttribute("href");
  expect(phone).toBe("tel:+914023456789");
});
