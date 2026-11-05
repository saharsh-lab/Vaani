import { defineConfig, devices } from "@playwright/test";

// Browser tests for every page, link, button and form: `npm run e2e`.
// They start their own copy of the API on a fresh database (backend/app/e2e_db.py)
// and a production build of this site, so your development data is never touched.
// Needs Postgres from `docker compose up -d db` and the backend's virtualenv.

const API = "http://localhost:8100";
// Postgres and the backend's Python: the dev setup by default, CI sets its own.
const PG = process.env.E2E_PG ?? "localhost:5435";
const PY = process.env.E2E_PYTHON ?? ".venv/bin/python";
const WEB = "http://localhost:3100";
// Locally, use the installed Chrome; CI installs Playwright's own browser.
const channel = process.env.CI ? undefined : "chrome";

export default defineConfig({
  testDir: "./e2e",
  workers: 1, // the tests share one database
  timeout: 30_000,
  expect: { timeout: 10_000 },
  retries: process.env.CI ? 1 : 0,
  reporter: [["list"], ["html", { open: "never" }]],
  use: { baseURL: WEB, trace: "retain-on-failure", screenshot: "only-on-failure" },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"], channel } },
    // Phones: layout checks and the main flows, on a narrow touch screen.
    { name: "phone", use: { ...devices["Pixel 7"], channel }, grep: /@phone/ },
  ],
  webServer: [
    {
      command: `cd ../backend && ${PY} -m app.e2e_db && exec ${PY} -m uvicorn app.main:app --port 8100`,
      url: `${API}/health`,
      timeout: 120_000,
      reuseExistingServer: false,
      env: {
        E2E_PG: PG,
        DATABASE_URL: `postgresql+psycopg://vaani_app:vaani_app@${PG}/vaani_e2e`,
        ADMIN_DATABASE_URL: `postgresql+psycopg://vaani_admin:vaani_admin@${PG}/vaani_e2e`,
        GEMINI_API_KEY: "", // no AI calls from the tests
        APP_ENV: "development",
        PUBLIC_BOOKINGS_PER_IP_PER_HOUR: "1000",
        LOGIN_ATTEMPTS_PER_15_MIN: "1000", // the tests sign in many times
      },
    },
    {
      command: "npm run build && exec npx next start -p 3100",
      url: WEB,
      timeout: 240_000,
      reuseExistingServer: false,
      env: {
        NEXT_DIST_DIR: ".next-e2e",
        API_URL: API,
        NEXT_PUBLIC_API_URL: API,
        NEXT_PUBLIC_SITE_URL: WEB,
      },
    },
  ],
});
