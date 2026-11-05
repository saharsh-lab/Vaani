# Vaani website and dashboard

The public site (home page, each business's booking page at `/c/<slug>`, privacy policy, terms) and the owner and staff dashboard. Next.js 16, Tailwind 4, shadcn/ui on Base UI.

```bash
npm install
npm run dev        # http://localhost:3000, with the API on :8000
```

Demo logins come from `python -m app.seed --demo-activity` in `backend/`.

## Settings

| Variable | What it is | Default |
| --- | --- | --- |
| `API_URL` | The FastAPI backend, as this server reaches it. `/api/*` is forwarded there, so the session cookie is first-party | `http://localhost:8000` |
| `NEXT_PUBLIC_API_URL` | The API as browsers reach it (the talk-to-us page lives there) | `http://localhost:8000` |
| `NEXT_PUBLIC_SITE_URL` | This site's public address, for canonical links, the sitemap and link previews | on Vercel, the project's production domain; otherwise `http://localhost:3000` |
| `NEXT_PUBLIC_CONTACT_EMAIL` | Where privacy and support questions go; shown on the legal pages | a placeholder: **set it before launch** |

The `NEXT_PUBLIC_*` values are built into the pages, so set them before building.

## What's in place for launch

- **Titles, descriptions and link previews** on every page. Each business's booking page gets its own title and a preview image with its name and address (`src/app/c/[slug]/opengraph-image.tsx`), which is what WhatsApp shows when a clinic shares its link.
- **`/sitemap.xml`, `/robots.txt`** (the dashboard is excluded and marked `noindex`), a web app manifest, a favicon and a home-screen icon.
- **HTTPS only in production:** plain-HTTP requests behind a proxy are redirected (`src/proxy.ts`), and every response sends HSTS and security headers (`next.config.ts`). The API does the same (`backend/app/https.py`).
- **A custom 404 page** with links back.
- **Form checks** on every field: the browser's own rules (required, email, length, phone patterns from `src/lib/validation.ts`) shown in words under the field, with the first problem focused. The API checks the same things again.

## Browser tests

```bash
docker compose up -d db     # from the repo root
npm run e2e                 # about a minute
```

48 tests in `e2e/` click through every page, link, button and form on a desktop and a phone screen: the booking flow with its checks and a slot taken mid-booking, sign-in and sign-up, staff permissions, each dashboard page and form, the 404 page, the sitemap and robots.txt, sharing images, security headers, the HTTPS redirect, and a crawl of every link for broken ones. They build the site into `.next-e2e/` and start their own API on a fresh demo database (`vaani_e2e`), so your development data isn't touched. CI runs them on every push.
