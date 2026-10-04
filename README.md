# Foundry v1

**The machine that makes AI agents.** An expert uploads their book or documents;
Foundry builds a live, citation-backed chat agent that answers strictly from
that material — every factual claim quoted verbatim with its source, and an
honest *"that's outside my training material"* when the corpus doesn't cover it.

$0 build: no paid APIs, no paid services, no paid hosting. Everything runs
locally. Nothing in v1 requires a credit card.

## Quick start

```bash
cd ~/workspace/foundry
.venv/bin/python app.py        # serves http://127.0.0.1:5050
```

Open `http://127.0.0.1:5050`:
- **Dashboard** — lists all agents.
- **New agent** (`/new`) — name it, upload `.pdf` / `.docx` / `.md` / `.txt`,
  get a shareable chat link (`/a/<slug>`).
- **Chat** (`/a/<slug>`) — ask anything; answers quote the source with
  document + section citations and suggested-question chips.

To re-seed the demo agents from the config:

```bash
.venv/bin/python seed.py       # reads agents.json; skips agents that exist
```

## Deployment (public, $0)

Foundry is deploy-ready. Primary target: **Render free tier** (no card).
Fallback: Railway trial, or Oracle Cloud Always Free (persistent disk, but
signup needs a card).

What's in the repo:
- `Dockerfile` — Python 3.12-slim, gunicorn, demo index baked in at build time
- `render.yaml` — one-tap Blueprint (free plan; prompts for the creator passcode)
- `requirements.txt` — pinned: Flask 3.1.3, pypdf 6.19.0, python-docx 1.2.0, gunicorn 26.2.0
- `DEPLOY.md` — the numbered phone-friendly guide: his two taps are
  (1) creating the free Render account via the pre-filled deploy link and
  (2) creating Stripe Payment Links. Nothing else.

`PORT` is honored from the environment and the app binds `0.0.0.0` when it's
set (local runs stay on loopback). SQLite notes: the free tier's filesystem is
ephemeral — owner-added agents/uploads survive idle sleep but are wiped on
redeploy; the demo agent's index is baked into the image so the public site
always works.

## Creator-flow auth

Set `FOUNDRY_ADMIN_PASSCODE` and agent creation is gated: `/new` (GET + POST),
`POST /api/agents/<id>/docs`, and the payment-link editor all redirect to a
passcode page (`/admin`). Public chat (`/a/<slug>`, `/api/chat`,
`/api/agents/<id>/suggest`) stays open. Unset the variable and the gate is
open — that's the local-dev mode. `FOUNDRY_SECRET_KEY` optionally pins the
Flask session secret (otherwise it's random per boot and admin logins end on
restart).

## Payments (Stripe Payment Links — zero API dependency)

Each agent has an optional `payment_link` field: paste a Stripe Payment Link
when creating the agent (or later, from the admin-only editor on the agent
page) and a green **"Subscribe / pay"** button appears on its public page,
pointing at Stripe checkout. Blank = free agent, no button. Only absolute
`http(s)` URLs are accepted. The user creates the actual links in his Stripe
dashboard — the exact taps are in `GATES.md`.

## Architecture

```
app.py                  Flask app: dashboard, creator flow, chat pages, JSON API
foundry/store.py        SQLite schema (agents, documents, chunks) + FTS5 index
foundry/ingest.py       Upload → text extraction → chunking → index
foundry/retrieve.py     FTS5 (porter stemming) + BM25 retrieval
foundry/answer.py       Extractive answer engine (see below)
foundry/answer_tokens.py  Tokenizer, stopwords, compact Porter stemmer
templates/ + static/    Apple-restraint UI, mobile-first
agents.json             Demo-agent config — new domain = new block, no code change
seed.py                 Idempotent seeder: config → agents → ingest
sample_corpus/          Sample fitness guide (demo content for Agent #2)
```

### How answering works (all in `foundry/answer.py`)

1. **Retrieve** — FTS5/BM25 over the agent's chunks (top 30).
2. **Re-rank** — chunks whose *section headings* match the question outrank
   body matches; navigational meta-sections (indexes, reading lists,
   end-of-chapter reviews) are demoted.
3. **Evidence scoring** — every sentence, table row, and adjacent sentence
   pair is scored by stemmed term overlap (TF-IDF weighted). Two guards keep
   it honest:
   - multi-term questions need ≥2 distinct terms in the evidence unit;
   - the question's most distinctive term must appear in the evidence, unless
     the section heading already establishes topicality (this is what makes
     "What is the capital of France?" abstain while "What does Dr. Greenacre
     say about anxiety?" answers).
4. **Quote, don't write** — the best passage per chunk is returned verbatim
   (only markdown formatting characters are stripped for display). Tables
   whose section matches render as the table itself. Nothing is ever invented:
   32/32 sampled quotes programmatically verified verbatim against source.
5. **Abstain honestly** — no evidence → "That's outside my training material,"
   plus suggested questions derived from the agent's real section headers.

### The one LLM plug-in point

`generate_with_llm(question, passages)` in `foundry/answer.py`. Set
`FOUNDRY_LLM_PROVIDER=gemini` + `FOUNDRY_LLM_KEY` (free tier via Google AI
Studio) and it synthesizes a short summary **grounded only in the retrieved
passages** — the prompt forbids using anything else. Unset (the default) →
pure extractive answers.

## Domain-generality (a core requirement, not an accident)

Foundry is **not** dental software. No ingest, retrieval, citation, or UI code
contains domain assumptions (the only domain-tuned constant is a short list of
navigational section names to demote). Proof:

- **Agent #1 — The Mouth Code** (example/demo agent): the real 8-book Mouth
  Code series manuscripts, 488,311 words / 2,159 chunks. Source files live
  outside the repo (`~/workspace/your_files/mouth-code-greenacre-show/manuscripts/`);
  re-ingest with `rm foundry.db* && .venv/bin/python seed.py`.
- **Agent #2 — Strength Basics**: a sample fitness-coaching guide
  (`sample_corpus/`, demo content written for this purpose). Same pipeline,
  same citation engine, same abstain behavior — including table rendering.
- **Creator-flow test**: a plumbing guide uploaded through the web UI became a
  working agent in one POST; then removed to keep the demo clean.

Adding a second (or twentieth) domain is a **config-level operation**:

```json
{ "slug": "my-coach", "name": "My Coach", "tagline": "...",
  "description": "...", "docs_dir": "/path/to/docs" }
```

Add the block to `agents.json`, run `seed.py`. No code changes.

## What's real vs. staged

| Real (works now) | Staged (human gates — see GATES.md) |
|---|---|
| Upload → chunk → index → chat, end to end | Creating the Stripe Payment Links (his tap; the button wiring is done) |
| Verbatim citations on every factual claim | Pushing the repo to GitHub + sending him the Render deploy link (agent pre-step) |
| Honest abstain outside the corpus | WhatsApp/SMS via Twilio |
| Shareable chat links, mobile-friendly UI | Custom domain + paid hosting |
| Multi-agent, multi-domain from one codebase | LLM synthesis (works on a *free* key; extractive is the v1 default) |
| Deploy-ready: Dockerfile, render.yaml, pinned requirements | Public deployment itself (his tap: free Render account) |
| Creator passcode gate on agent creation; public chat open | |
| Per-agent Stripe Payment Link button (paste link → button appears) | |

## Files of record

- `README.md` — this file
- `GATES.md` — every future external service + its free-tier alternative
- `TESTLOG.md` — the 10+ hard questions, results, verbatim verification
