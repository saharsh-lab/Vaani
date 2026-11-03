# Vaani dashboard

The owner and staff dashboard (Next.js 16, Tailwind 4, shadcn/ui on Base UI).

```bash
npm install
npm run dev        # http://localhost:3000, with the API on :8000
```

`/api/*` is forwarded to the FastAPI backend (`API_URL`, default `http://localhost:8000`),
so the session cookie is first-party. `NEXT_PUBLIC_API_URL` is where browsers reach
the API's `/voice/<slug>` page, for the website widget.

Demo logins come from `python -m app.seed --demo-activity` in `backend/`.
