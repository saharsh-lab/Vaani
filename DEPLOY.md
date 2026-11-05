# Deploying Vaani

| Piece | Where | Cost |
| --- | --- | --- |
| Postgres with pgvector | Neon | Free tier |
| API (FastAPI): agent tools, dashboard API, WhatsApp webhook, `/voice/<slug>` page | Railway, service 1 | Usage-based; the Hobby plan's $5 credit covers a small instance |
| Voice worker (LiveKit agent) | Railway, service 2 | About 1 GB of RAM while running |
| Dashboard (Next.js) | Vercel | Free tier |
| Real-time voice transport | LiveKit Cloud | Free tier |
| Error tracking (optional) | Sentry | Free tier |

Put every secret into the platform's variables page. Never commit secrets, and don't paste them into chats.

## 0. Generate three secrets

Run this three times and keep the values for the steps below: `AGENT_API_KEY`, `DASHBOARD_JWT_SECRET`, and the database password for `vaani_app`.

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(40))"
```

## 1. Database: Neon

1. Create a project. Region: **AWS Asia Pacific (Singapore)**, the closest to India.
2. In **SQL Editor**, create the role the API connects as. It doesn't own the tables, so row-level security applies to it:
   ```sql
   CREATE ROLE vaani_app LOGIN PASSWORD '<the vaani_app password from step 0>';
   ```
3. Open **Connect**, switch **Connection pooling off** (use the direct connection), and copy the connection string. Make two URLs from it, changing `postgresql://` to `postgresql+psycopg://` and keeping `?sslmode=require`:
   - `ADMIN_DATABASE_URL`: the string as given (the `neondb_owner` user). It runs migrations and seeding.
   - `DATABASE_URL`: the same, with the user and password replaced by `vaani_app` and its password.

The API runs the migrations itself every time it starts.

## 2. API: Railway, service 1

1. **New Project → Deploy from GitHub repo → `saharsh-lab/Vaani`.**
2. Service **Settings**:
   - **Root Directory:** `backend` (it builds `backend/Dockerfile`)
   - **Healthcheck Path:** `/health`
   - **Networking → Generate Domain**, e.g. `https://vaani-api.up.railway.app`
3. **Variables:**

   | Variable | Value |
   | --- | --- |
   | `APP_ENV` | `production` (the API refuses to start with development defaults) |
   | `DATABASE_URL`, `ADMIN_DATABASE_URL` | from step 1 |
   | `AGENT_API_KEY`, `DASHBOARD_JWT_SECRET` | from step 0 |
   | `COOKIE_SECURE` | `true` |
   | `GEMINI_API_KEY`, `GEMINI_MODEL` | your key, `gemini-3.5-flash-lite` |
   | `SARVAM_API_KEY` | for WhatsApp voice notes |
   | `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET` | from step 4.1: get them first, because in production the API refuses to start with LiveKit's dev secret |
   | `PORT` | `8000`, and use 8000 when Railway asks which port to expose |
   | `SENTRY_DSN` | optional |

4. When it's deployed, `https://<your-api-domain>/health` returns `{"ok":true}`.

## 3. Dashboard: Vercel

1. **Add New → Project → import `saharsh-lab/Vaani`.** Set **Root Directory** to `web`; the framework is detected as Next.js.
2. **Environment Variables**, set **before the first deploy** because the API address is built into the app:

   | Variable | Value |
   | --- | --- |
   | `API_URL` | `https://<your-api-domain>` |
   | `NEXT_PUBLIC_API_URL` | `https://<your-api-domain>` |
   | `NEXT_PUBLIC_SITE_URL` | optional on Vercel, which provides the production domain; set it elsewhere (canonical links, sitemap, link previews) |
   | `NEXT_PUBLIC_CONTACT_EMAIL` | the email for privacy and support questions, shown on `/privacy` and `/terms` |

3. Deploy, open the Vercel URL, and create your business at `/signup`.

To put the demo clinic on the server, run the seed from your laptop against Neon. Choose your own passwords, because the default demo passwords are public in this repo:

```bash
cd backend
ADMIN_DATABASE_URL='<from step 1>' DATABASE_URL='<from step 1>' \
  .venv/bin/python -m app.seed --demo-activity --owner-password '<choose one>' --staff-password '<choose one>'
```

With `GEMINI_API_KEY` set in your shell or `.env`, the seed also embeds the FAQs, so they're searchable in any language. Otherwise, run `python -m app.kb_index` later with the same database URLs.

## 4. Voice: LiveKit Cloud and Railway, service 2

1. In **LiveKit Cloud**, create a project. **Settings → Keys** gives you the URL (`wss://…livekit.cloud`), the API key and the secret. Add all three to the API service (step 2), so it can hand out call tokens.
2. In Railway, add a second service from the same repo (**+ New → GitHub Repo → `saharsh-lab/Vaani`**):
   - **Root Directory:** `backend`
   - Variable `RAILWAY_DOCKERFILE_PATH` = `Dockerfile.voice`
   - No domain and no health check: the worker only connects out to LiveKit.
   - **Variables:** `APP_ENV=production`, `API_BASE_URL=https://<your-api-domain>`, the same `AGENT_API_KEY` as the API, `GEMINI_API_KEY`, `GEMINI_MODEL`, `SARVAM_API_KEY`, the three `LIVEKIT_*` values, optionally `SENTRY_DSN`. On a small instance, also set `VOICE_IDLE_PROCESSES=1`.
3. Its logs show `registered worker` when it's connected. Try a call at `https://<your-api-domain>/voice/<your-business-slug>`. The dashboard's **Channels** page has the link and the embed code.

## 5. WhatsApp (optional)

Follow "Connect WhatsApp" in the README. The callback URL is `https://<your-api-domain>/webhooks/whatsapp`. Add `WHATSAPP_VERIFY_TOKEN`, `WHATSAPP_APP_SECRET` and `WHATSAPP_ACCESS_TOKEN` to the API service.

## 6. Check it

- [ ] `https://<api>/health` returns `{"ok":true}`, and `http://<api>/v1/public/<slug>` redirects to `https://`
- [ ] `/privacy` and `/terms` show your contact email, not `hello@vaani.example`
- [ ] Paste the booking page link into WhatsApp: the preview shows the business name and address
- [ ] `https://<vercel-url>/robots.txt` and `/sitemap.xml` use your real domain
- [ ] Sign up on the Vercel URL; the overview loads and the setup checklist shows what's left
- [ ] Sign in as a staff member: only Bookings and Callbacks appear
- [ ] Add a booking from the dashboard; a taken slot suggests free times nearby
- [ ] Booking page `https://<vercel-url>/c/<your-business-slug>`: book a time, and it appears on the dashboard as Online
- [ ] Voice page: the call connects and the worker logs `call … ended` with latency and cost
- [ ] Sentry (if set): the project shows the `api` environment

## Notes

- **Cold starts:** Railway keeps the API running. If you use a host that sleeps when idle (such as Render's free tier), the first WhatsApp message or call after a pause waits about 50 seconds.
- **One API instance:** the WhatsApp per-customer lock and the rate limits live in memory, so run a single API instance until the Redis queue from the spec is added.
- **Domains:** in Vercel and Railway you can put the dashboard at `app.yourdomain.com` and the API at `api.yourdomain.com`. Then update `API_URL`, `NEXT_PUBLIC_API_URL` and `API_BASE_URL`.
