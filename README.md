# Vaani

An AI receptionist for small Indian businesses. It answers calls and WhatsApp messages in Telugu, Hindi and English, answers questions from the business's own FAQs, and books, reschedules and cancels appointments.

## Status

- [x] **Booking engine (text-first):** multi-tenant Postgres schema with row-level security, slot engine, the six agent tools as an API, a Gemini agent you can chat with in the terminal, CI
- [x] **WhatsApp channel:** signed webhooks, chats that continue across messages, dedupe of redelivered messages, read receipts with typing indicator
- [x] **Voice notes on WhatsApp:** transcribed with Sarvam (Telugu, Hindi, English and mixed speech), then answered like a typed message
- [ ] Booking confirmations and owner handoff alerts on WhatsApp (needs approved message templates)
- [ ] Knowledge base with embeddings (pgvector), PDF upload
- [x] **Real-time voice:** browser "Talk to us" widget over LiveKit, Sarvam streaming speech-to-text, Gemini with the same six tools, Sarvam Bulbul voice; per-reply latency and per-call cost saved
- [x] **Owner and staff dashboard** (Next.js + shadcn/ui): sign-up, role-based access, bookings calendar, callback queue, conversations with transcripts and cost, settings, FAQs, team, channels
- [x] **Eval suite:** 50 scripted conversations and 100 labelled utterances run against real Gemini, scored from the database plus an LLM judge; nightly in CI, failing below 90% booking success
- [x] **Ready to deploy:** production safety checks, Docker images for the API and the voice worker, Sentry; step-by-step guide in [DEPLOY.md](DEPLOY.md) (Neon, Railway, Vercel, LiveKit Cloud)
- [ ] Langfuse LLM tracing; Redis job queue for running several API instances

## Quickstart

You need Docker and Python 3.12.

```bash
cp .env.example .env            # then add GEMINI_API_KEY (free: https://aistudio.google.com/apikey)
docker compose up -d db         # Postgres 16 + pgvector on localhost:5435

cd backend
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
alembic upgrade head
python -m app.seed              # demo tenant: Sri Dental Clinic
uvicorn app.main:app --reload   # API docs at http://localhost:8000/docs
```

In a second terminal, talk to the clinic's agent:

```bash
cd backend && source .venv/bin/activate
python -m vaani_agent.cli --phone 9876543210   # --phone acts like caller ID
```

Try "Repu evening RCT consultation ki appointment kavali", "Is there parking?", or "I want to cancel my booking". Tool calls are printed as they happen, and the session ends with token count, cost in ₹ and median latency.

The default model is `gemini-3.5-flash-lite`. On a 10-conversation booking slice it booked 10/10 correctly, against 7/10 for `gemini-3.1-flash-lite`, and it averages about 0.85 s per call. (`gemini-2.5-flash-lite` is closed to new keys.) To try another, run `python -m vaani_agent.cli --list-models` and set `GEMINI_MODEL` in `.env`.

**Tests:** `pytest` from `backend/`, with the database container running. They use a separate `vaani_test` database, so your dev data is never touched.

**All in Docker:** `docker compose up --build`, then `docker compose exec api python -m app.seed`.

## Dashboard

```bash
cd backend && python -m app.seed --demo-activity   # demo clinic + logins + a week of sample activity
cd ../web && npm install && npm run dev            # http://localhost:3000 (API must be on :8000)
```

Sign in as `owner@sri-dental.example.com` / `vaani-demo-owner` or `staff@sri-dental.example.com` / `vaani-demo-staff`, or create your own business at `/signup`.

| | Owner | Staff |
| --- | --- | --- |
| Bookings: day/week calendar, add walk-ins, mark done / no-show, move, cancel | ✅ | ✅ |
| Callbacks: customers the agent handed over; claim, call, resolve with a note | ✅ | ✅ |
| Overview: today, setup checklist, bookings by Vaani, cost, voice latency, channels, languages | ✅ | |
| Conversations: every call and chat with transcript, tool calls, latency and cost | ✅ | |
| Settings: business, greeting, languages, hours (split shifts, per staff), services, staff, days off | ✅ | |
| Knowledge base and team logins | ✅ | |

The API enforces the roles (staff get 403 on owner endpoints) and each request runs in the user's business under row-level security. Changes take effect on the agent's next conversation: a new FAQ is searchable immediately, and a day off stops Vaani offering that day.

## Talk to it (browser voice)

You need `SARVAM_API_KEY` and `GEMINI_API_KEY` in `.env`.

```bash
docker compose up -d livekit                 # local LiveKit server on :7880
cd backend && source .venv/bin/activate
python -m vaani_agent.voice download-files   # once
python -m vaani_agent.voice dev              # the voice agent; waits for calls
```

With the API running, open http://localhost:8000/voice/sri-dental, tap the button and speak in Telugu, Hindi or English. The worker logs each call's p50/p95 latency, outcome and cost when it ends.

To put it on a business's website:

```html
<iframe src="https://<your-api>/voice/sri-dental" allow="microphone" width="420" height="560"
        style="border:0"></iframe>
```

How a call works:

- The page asks `POST /v1/voice/session` for a 10-minute LiveKit token. The token creates a new room and tells LiveKit to send the `vaani-voice` agent, with the business id attached.
- The agent detects the language of each utterance (`language=unknown`) and switches language and voice to match. Bulbul v4 Flash voices are per language: Pooja for Telugu, Ishita for Hindi-English and English (`sarvam_tts_speakers` in `vaani_agent/config.py`). It writes Telugu in Telugu script and Hindi in Devanagari so the voice pronounces them properly.
- Silero VAD decides when the caller has finished speaking, as the spec chose. LiveKit's turn-detector model is available on LiveKit Cloud, but it probably doesn't cover Telugu.
- Each reply's latency (caller stops speaking → first audio) is saved on its transcript line, so p50/p95 come straight from the `messages` table. Cost adds up Gemini tokens, seconds of speech transcribed and characters spoken.
- Calls end after `VOICE_MAX_CALL_SECONDS`, and each IP can start 20 calls an hour (`VOICE_CALLS_PER_IP_PER_HOUR`).

## Connect WhatsApp

Meta gives every developer app a free test number that can message up to 5 numbers you verify. Meta's dashboard changes often, so the menu names below may differ slightly.

1. At [developers.facebook.com](https://developers.facebook.com), create an app of type **Business** and add the **WhatsApp** product.
2. On **WhatsApp > API Setup**, note the **Phone number ID** and generate an access token. The temporary token lasts 24 hours; for a lasting one, create a System User token in Business Settings. Add your own phone under **To** and verify it.
3. Fill in `.env`: `WHATSAPP_ACCESS_TOKEN`, `WHATSAPP_APP_SECRET` (from **App settings > Basic**), and any random `WHATSAPP_VERIFY_TOKEN`. For voice notes, add `SARVAM_API_KEY` from [dashboard.sarvam.ai](https://dashboard.sarvam.ai) (new accounts get free credit). Restart uvicorn.
4. Link the demo clinic to the number: `python -m app.seed --whatsapp-number-id <Phone number ID>`
5. Give your local API a public HTTPS URL, for example `cloudflared tunnel --url http://localhost:8000` or `ngrok http 8000`.
6. On **WhatsApp > Configuration**, set the callback URL to `https://<your-tunnel>/webhooks/whatsapp`, enter the same verify token, and subscribe to the **messages** field.
7. Message the test number from your phone: "Hi, repu evening appointment kavali".

Without `WHATSAPP_ACCESS_TOKEN`, replies are written to the uvicorn log instead of sent, which is enough to test the webhook with a signed request.

How it behaves:

- The sender's WhatsApp number counts as verified, so the agent books under it and only shows or changes that number's bookings.
- Messages less than 30 minutes apart continue the same conversation, with the agent's saved history. After a longer gap a new conversation starts (`WHATSAPP_IDLE_MINUTES`).
- Voice notes are downloaded from Meta and transcribed with Sarvam's `saaras:v4` model. The recogniser is primed with the business's service and staff names (Sarvam "key terms"), so "RCT consultation" and "Dr. Lakshmi" come through. The agent sees the text tagged `[voice note, te-IN]`, confirms names and times before booking, and the detected language and speech-to-text cost are saved on the conversation.
- Sarvam's synchronous API takes up to 30 seconds of audio. Longer voice notes get a polite "please send a shorter one or type it", decided from the file's own headers before anything is uploaded. Images, documents and stickers get a "please type" reply.

## Evals

```bash
cd backend && source .venv/bin/activate
python -m evals                          # ~500 Gemini calls; writes evals/reports/latest.md
python -m evals --only booking --limit 5 # a quick slice while iterating on the prompt
python -m evals.calls                    # numbers from real calls and chats in your database
```

What it measures, against the targets in the project spec:

| Metric | How |
| --- | --- |
| Booking success rate | 27 booking, reschedule and cancel conversations. Passes only if the database ends up exactly right: the right service, day and time, under the caller's number, with no extra bookings and their other bookings untouched. |
| Tool-call accuracy | 100 single messages in English, Telugu and Hindi (romanised and native script), each labelled with the first tool and its key arguments. |
| FAQ answer accuracy | 10 FAQ conversations, checked by an LLM judge against a rubric. |
| Hallucination rate | The judge lists every claim in every reply that the clinic's facts or that conversation's tool results don't support. |
| Handoff rate, latency, cost | Recorded per conversation. Voice latency and ₹ per minute come from live calls (`python -m evals.calls`). |

A full run takes about 500 Gemini calls (agent turns, utterances and judging), so its length depends on your key's rate limit: `--rpm` paces it, and rate-limit errors are retried. At 30 requests a minute it takes roughly 17 minutes.

First full run (3 Nov 2026, `gemini-3.5-flash-lite`): booking success 92.6% (25/27), FAQ accuracy 90%, hallucination rate 0% (0/101 replies), and 95% tool-call accuracy on the 80 sentences that ran before the free-tier daily quota ran out. The failures pointed to date arithmetic and one missed cancel confirmation; the prompt now has a two-week date table and stricter confirmation rules. Re-run to see their effect: about 550 Gemini calls, so on the free tier, once a day.

Each conversation runs in its own copy of the demo clinic (a separate business), with the clock frozen at Monday 2 Nov 2026, 9:00 AM IST, so "repu sayantram 6 ki" always means one specific slot. `pytest` checks that every expected slot is actually free in the seeded schedule, so a failed eval always means the agent got something wrong, not the test.

To run it in CI, add a `GEMINI_API_KEY` repository secret. The `evals` job then runs on pushes to `main`, nightly and on demand, posts the report to the run summary, and fails below 90% booking success. Set the `EVAL_RPM` variable to fit your key's rate limit.

Before quoting these numbers:

- The customer's lines are fixed. An agent that asks something the script doesn't answer can fail a conversation it would have handled with a real person; read the failure reasons before blaming the prompt.
- The judge is a Gemini model grading Gemini. The spec says "LLM-as-judge plus manual check", so read the FAQ transcripts in `latest.json` yourself before quoting FAQ accuracy.
- Language detection accuracy needs recorded audio clips (Telugu, Hindi, English, mixed), and the spec's weekly audio run isn't built. Record 20-30 short clips with friends and family to start that set.

## How it works

```
customer ──► channel: terminal, WhatsApp webhook (voice next)
               │
               ▼
        vaani_agent.AgentSession ◄──► Gemini (function calling)
               │  tool calls over HTTP: agent key + X-Business-Id
               ▼
        FastAPI /v1/tools/*  ──►  Postgres (row-level security per business)
```

The agent is one LLM with a per-business system prompt and six tools: `search_knowledge`, `check_availability`, `create_booking`, `find_booking`, `reschedule_or_cancel` and `handoff_to_human`. It never touches the database; every action goes through the API.

Design decisions worth knowing:

- **The database enforces tenant isolation.** The API connects as `vaani_app`, which doesn't own the tables, and each transaction sets `app.business_id`. Row-level security policies then filter every table on it. Composite foreign keys on `(business_id, id)` stop a booking from pointing at another business's service, staff member or customer.
- **The database prevents double booking.** An exclusion constraint on `(staff_id, time range)` covers confirmed bookings. Writes happen inside a savepoint, so a caller who loses a race gets a 409 with the nearest free slots, not an error. One test fires five simultaneous requests for the same slot and expects exactly one booking.
- **The model can't control fields that matter for security.** The runtime fills in the conversation id and the channel. When the caller's number is verified (WhatsApp, caller ID), the runtime uses it for `find_booking` and booking changes, so nobody can read someone else's appointments by saying their number.
- **Errors give the model a way forward.** A taken slot returns alternatives, and an unknown service returns the real service names. The model recovers with real data instead of guessing.
- **One agent, many channels.** Voice, WhatsApp and the terminal share the same prompt, six tool schemas and the runtime's security overrides. The terminal and WhatsApp wrap the same `AgentSession`; the LiveKit voice agent registers the same JSON schemas as LiveKit tools. On WhatsApp it runs inside the API process and calls the tools through the API's own routes (in-process HTTP), so the same auth and tenant checks apply.
- **Slot logic is pure functions** (`app/services/availability.py`), tested without a database. It handles split shifts, per-staff hours, holidays, lead time and spreading the offered times.

## Layout

```
backend/
  app/
    api/            routes: tools, agent context, conversations, WhatsApp webhook
    services/       availability (slot math), scheduling, bookings, knowledge, conversations
    models.py       ORM mappings
    seed.py         demo clinic
  migrations/       hand-written SQL: schema, row-level security, constraints
  vaani_agent/      agent runtime: tool declarations, prompt, Gemini loop, terminal chat,
                    WhatsApp, Sarvam speech-to-text, LiveKit voice worker (voice.py)
  app/static/       the "Talk to us" voice page
  evals/            scenarios.yaml, tool_calls.yaml, the harness, judge and report
  tests/
web/                owner and staff dashboard (Next.js)
infra/postgres/     database role setup
```

## Differences from the spec

- `staff_services` is a join table rather than `staff.service_ids[]`, so every link is checked by a foreign key.
- Added `businesses.slug` (for lookups and widget URLs), `messages.business_id` (for row-level security), LLM token counts on `conversations`, and a `web_chat` channel.
- Knowledge search is keyword-only for now, and the agent is told to search in English. Embeddings come with the RAG milestone.
- The cost per conversation uses the prices in `vaani_agent/config.py`. Gemini 3.5 Flash-Lite is set to $0.30 / $2.50 per million input / output tokens, taken from third-party price trackers. Confirm on Google's pricing page before you quote numbers.

## Known limits

- WhatsApp turns run as FastAPI background tasks, with a per-customer lock inside one process. Running more than one API instance, or surviving restarts mid-turn, needs the ARQ/Redis queue from the spec.
- One Meta access token serves every business for now. Per-business numbers need Meta's Embedded Signup, with a token stored per business.
- `channel_events` (message ids kept for dedupe) grows forever until a cleanup job exists. A week of ids is enough.
- Booking confirmations for voice and web bookings, and handoff alerts to the owner, aren't sent yet. Messages a business starts on WhatsApp need pre-approved templates.
- Voice notes over 30 seconds aren't transcribed. Sarvam's batch API handles up to 2 hours, but it's asynchronous and too slow for a chat reply.
- The voice pipeline has been tested end to end with LiveKit, but not with real audio or real keys. Tests drive LiveKit's own agent session in text mode with a scripted model, and a local run confirmed the hand-off: token, then agent dispatched, then the clinic's details loaded and the agent listening, then Sarvam's streaming endpoint (rejected with a placeholder key).
- If Sarvam or Gemini fails mid-call, the session ends and the page shows "Call ended". There's no fallback provider yet; the spec's Whisper fallback would go in LiveKit's `FallbackAdapter`.
- `LIVEKIT_API_SECRET=secret` is LiveKit's dev-mode secret. Use LiveKit Cloud's long secret anywhere public.
- The voice worker isn't in Docker Compose yet. It runs from the venv, and in production it deploys as a separate service (`python -m vaani_agent.voice start`).
- Dashboard logins are email and password, built into the API (scrypt hashes, signed httpOnly cookie). There's no password reset or email invite yet: owners set a temporary password for staff. Supabase Auth, as in the spec, can replace it behind `app/auth.py`. Set a long `DASHBOARD_JWT_SECRET` and `COOKIE_SECURE=true` before deploying.
- Speech-to-text cost is counted only for OGG/Opus audio (every WhatsApp voice note), because that's where the length can be read without decoding. Forwarded MP3 or M4A files are transcribed but their cost isn't counted.
