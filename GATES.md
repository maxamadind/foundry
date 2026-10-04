# Foundry — Human Gates & Free-Tier Alternatives

**Standing constraint: $0.** Nothing in v1 may require the user to pull out a
credit card. Everything agent-side is built and tested (see
`TESTLOG-STREAM-A.md`). What remains is exactly **two taps from him** — nothing
else.

## TAP 1 — Free hosting account (Render)

**What he taps, in order, on his iPhone:**

1. Opens the one-tap deploy link the agent sends him
   (`render.com/deploy?repo=…`, pre-filled from `render.yaml`).
2. **Sign up** → continue with Google. Free plan — no card asked, ever.
3. When prompted for **FOUNDRY_ADMIN_PASSCODE**, types a passcode he'll
   remember (this locks agent creation on the public site; chat stays public).
4. **Deploy.** Waits ~5 minutes.

Full numbered guide: `DEPLOY.md`. Fallback if Render fails: Railway trial, or
Oracle Cloud Always Free (persistent disk, but signup needs a card).

## TAP 2 — Stripe Payment Links (per agent he wants to charge)

**What he taps, in order:**

1. Stripe Dashboard → **Payment links** (sidebar) → **Create payment link** →
   set price + product name → **Create link** → **Copy link**.
2. Public Foundry site → **Create an agent** → creator passcode → open the
   agent → **Add a payment link** → paste → **Save**.

A green **"Subscribe / pay"** button appears on that agent's public page.
Agents with no link stay free (no button). No Stripe API key, no code, no
take-rate logic in v1 — the link *is* the checkout.

## Still staged (later, with his explicit go-ahead)

| # | Gate | Why it's gated | Free-tier / $0 alternative |
|---|------|----------------|----------------------------|
| 3 | **WhatsApp/SMS delivery (Twilio)** | Requires a Twilio account + phone number purchase | v1 is web-chat only; later, Twilio's free trial credit covers testing, and WhatsApp Business Platform's free tier covers the first 1,000 conversations/month |
| 4 | **Custom domain** | Requires purchase (~$12–15/yr) | The free `onrender.com` URL works; later, free subdomains (e.g. via Cloudflare) |
| 5 | **LLM API key** | Paid tiers need a card — but NOT required | Extractive answers ARE v1 (no key needed). If synthesis is wanted: **Google AI Studio (Gemini) free tier** — no card, generous free quota; plug-in point is `generate_with_llm()` in `foundry/answer.py` |

## What v1 deliberately does NOT need

- No vector database (SQLite FTS5 + BM25 does retrieval; zero deps beyond Flask/pypdf/python-docx).
- No embedding model, no API calls at query time — answers are extracted from
  the local index, so per-question cost is $0 and latency is ~15–130ms.
- No user accounts — one shared creator passcode gates the creator flow; all
  chat is public.
- No Stripe API integration — Payment Links are pasted URLs; Stripe handles
  the entire checkout.

## Agent pre-step before Tap 1 (not his work)

Render deploys from a public GitHub repo. The agent pushes `~/workspace/foundry/`
(already committed to git locally) to a public repo and hands him the one-tap
`render.com/deploy?repo=…` link. Then Tap 1 is genuinely one tap.
