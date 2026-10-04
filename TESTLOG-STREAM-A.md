# Foundry — Stream A Test Log (deploy prep, auth, payments, positioning)

Date: 2026-10-04. All tests run against the Stream A build in
`~/workspace/foundry/`. Original v1 battery (32/32 verbatim, hard questions,
cross-domain) is in `TESTLOG.md` and was not re-run except where noted —
regression spot-checks below confirm nothing broke.

## 1. Deployment config validation

| Check | Method | Result |
|---|---|---|
| `render.yaml` syntax + fields | Parsed with PyYAML; asserted service type/runtime/plan/env vars | ✅ `web / docker / free`; env: `FOUNDRY_ADMIN_PASSCODE` (sync:false → Render prompts at deploy), `FOUNDRY_SECRET_KEY` (generateValue) |
| `requirements.txt` installs clean | Fresh venv (`/tmp/foundry-buildcheck`), `pip install -r requirements.txt` — the exact layer the Dockerfile runs | ✅ exit 0; Flask 3.1.3, pypdf 6.19.0, python-docx 1.2.0, gunicorn 26.2.0 |
| `RUN python seed.py` (Docker build step) | Fresh venv + scratch DB (`FOUNDRY_DB=/tmp/seedcheck.db`) | ✅ seeds from zero; idempotent re-run prints "already exists — skipping" |
| `Dockerfile` builds locally | — | ⚠️ **Not possible: no Docker daemon on this VM** (`docker: command not found`). Every Dockerfile layer was validated individually instead (pip layer ✓, seed layer ✓, gunicorn CMD ✓ below). Dockerfile kept minimal and standard to minimize build risk. |
| gunicorn boot as the container would | `gunicorn app:app --bind 0.0.0.0:$PORT --workers 1 --threads 4` with `PORT=5057` | ✅ boots, serves |
| `PORT` env handling in `app.py` | `PORT=5058 python app.py` | ✅ binds 0.0.0.0:5058 (local default unchanged: 127.0.0.1:5050) |

**Two real bugs found by the dry-run and fixed:**
1. `seed.py` used `store.get_db()` (no schema creation) → crashed on a fresh
   DB, which is exactly what the Docker build does. Fixed to `store.init_db()`.
2. `seed.py` treated `ingest.ingest_file()`'s return as an int chunk count
   (`total_chunks += n`) → `TypeError`; it returns the document row. Fixed to
   `doc["chunk_count"]`. (Pre-existing bug — the ingest path never ran before
   because both demo agents already existed.)

## 2. Creator-flow auth (`FOUNDRY_ADMIN_PASSCODE=streamtest123`)

| # | Test | Result |
|---|---|---|
| 1 | `GET /new` logged out | 302 → `/admin?next=/new` ✅ |
| 2 | `POST /api/agents/<id>/docs` logged out | 302 (blocked) ✅ |
| 3 | `GET /`, public agent pages | 200, open ✅ |
| 4 | `POST /admin` wrong passcode | Stays on form, "Wrong passcode" ✅ |
| 5 | `POST /admin` correct passcode | 302, session set ✅ |
| 6 | `GET /new` with session | 200 ✅ |
| 7 | `POST /admin/agents/<id>/payment-link` logged out | 302 → `/admin` (blocked) ✅ |
| 8 | No passcode set (local mode) | `/new` 200 open, `/admin` redirects home ✅ |

Note: comparison uses `secrets.compare_digest` (timing-safe). Without
`FOUNDRY_SECRET_KEY` the Flask secret is random per boot, so admin sessions
end on restart — documented in `app.py` and `DEPLOY.md`.

## 3. Payments (dummy link `https://buy.stripe.com/test_dummy123`)

| # | Test | Result |
|---|---|---|
| 1 | Create agent with payment link (happy path) | 302 → `/a/pay-test-agent-three` ✅ |
| 2 | Agent page renders pay button | `<a class="btn pay" href="https://buy.stripe.com/test_dummy123" target="_blank" rel="noopener">Subscribe / pay</a>` ✅ |
| 3 | Invalid link at creation (`notaurl`) | 400, clear error ✅ |
| 4 | Admin updates link | 302; page shows new URL ✅ |
| 5 | `javascript:` URL rejected | 400 ✅ |
| 6 | Unauthenticated update | 302 → `/admin` (blocked) ✅ |
| 7 | Clear link + save | 302; button disappears from page ✅ |
| 8 | Admin-only editor visible to admin, hidden to public | `payadmin` block: 1 when logged in, 0 when not ✅ |
| 9 | Public chat unaffected (`POST /api/chat`) | 200 ✅ |

Behavioral note: creating an agent whose files extract no text still returns
400 ("None of those files contained readable text") — pre-existing v1 behavior,
unchanged; the agent row keeps its payment link for retry.

## 4. Positioning copy

"the AI that can't hallucinate — every claim quoted verbatim from your material"
now appears in: homepage hero lede, `/new` lede, site footer (`base.html`).
No other user-facing copy was changed. Verified via page fetches (footer +
hero strings present on `/`).

## 5. Regression spot-checks (existing work untouched)

- Real DB migration: `init_db()` on the existing 11 MB `foundry.db` adds the
  `payment_link` column idempotently; both demo agents intact, links empty.
- `POST /api/chat` on The Mouth Code ("What are the 7 hidden oral flaws?")
  still answers with the verbatim master table.
- Dashboard lists both demo agents; `/a/the-mouth-code` and
  `/a/strength-basics` render.

## Known honest limits (Stream A)

- Docker image not built end-to-end here (no daemon) — first Render build is
  the true end-to-end test; every layer was validated individually.
- Render free tier: ephemeral disk (owner-added agents wiped on redeploy,
  survive idle sleep), sleeps after ~15 min idle (30–60 s cold start).
  Documented in `render.yaml`, `DEPLOY.md`, and `README.md`.
- Publishing the repo to GitHub is the one remaining pre-step before his
  Tap 1 (no GitHub auth on this VM) — flagged in `DEPLOY.md` and the handoff.
