# Foundry — Post-Deploy Checklist (before Expert #1 onboards)

**Rule: no expert is contacted until every box is checked.**
Deploy is necessary but not sufficient — this is the launch gate.

## A. The public site works

- [ ] Public URL loads on a phone (not just desktop) — homepage renders.
- [ ] Demo agent chats correctly on the public URL: ask a topical question
      → verbatim quote with citation; ask an off-topic question → honest
      abstain.
- [ ] First paint after idle sleep is acceptable (Render free tier sleeps;
      ~30–60s cold start is normal and documented — but verify it wakes).
- [ ] `FOUNDRY_ADMIN_PASSCODE` is set and the creator flow (`/new`,
      doc upload, payment-link editor) is locked behind it. Public chat
      stays open without it.

## B. The expert onboarding flow works end-to-end

- [ ] Create a test agent through the **public** `/new` page (passcode),
      upload a real multi-page document, and get a working shareable link.
- [ ] The test agent's chat page renders suggested questions from the
      document's real section headers.
- [ ] Delete the test agent afterwards — the public site stays clean.
- [ ] Time the full loop (upload → indexed → chatting). Know the number so
      we can tell experts "your agent will be live within [X]".

## C. Trust infrastructure — MUST BE BUILT (verified missing 2026-10-04)

Code inspection on 2026-10-04 confirmed these do **not** exist yet. They
are launch blockers, not nice-to-haves — an expert's name goes on this.

- [ ] **Consent + privacy notice on every chat page.** One short block:
      what the agent is, that conversations may be logged to improve the
      service, and a contact for removal requests. No dark patterns, no
      legalese.
- [ ] **Conversation logging with consent.** Store (agent, timestamp,
      question, answer mode, cited passages) — the quality-monitoring and
      future data-flywheel foundation. Must only log after the consent
      notice is live. Schema addition to `foundry/store.py`.
- [ ] **"This is software, not the expert" disclosure** on each agent page.
      Required by the revenue-share terms (§5) — the page must state the
      agent quotes the expert's published material and is not the person.
- [ ] **Abuse basics:** rate-limit the chat API per IP (a public endpoint
      with $0 marginal cost is still a spam target), and strip uploaded
      filenames/paths from any public output.

## D. Money path verified

- [ ] Guled creates one Stripe Payment Link (his tap, per GATES.md) and we
      paste it on a test agent — the green button appears and points at a
      real Stripe checkout.
- [ ] Revenue statement template exists (gross, Stripe fees, 70/30 split —
      a one-page format, even if it's a spreadsheet for the first expert).

## E. The ephemeral-storage problem is handled

Render's free tier wipes uploaded agents on redeploy. An expert's agent
disappearing is a trust-destroying event. Before onboarding:

- [ ] Every expert manuscript is stored in `~/workspace/foundry/expert-corpora/`
      (never only on Render) — re-ingest is one documented command.
- [ ] A written re-seed runbook exists: redeploy → re-run seed for expert
      agents → verify each chat link. Tested once on the demo agent.
- [ ] Experts are told upfront (in the terms): hosting is best-effort on
      the free tier; their material is safe with us regardless.

## F. Documents ready

- [ ] `01-expert-onboarding-plan.md` — Guled has approved the 3 names.
- [ ] `02-revenue-share-terms.md` — reviewed; both sides to get independent
      advice before signing.
- [ ] `03-expert-pitch.md` — Guled has read it and it sounds like him.

## G. Expert #1 readiness

- [ ] Manuscript received as a file; rights confirmed in writing (one-line
      email is enough at this stage).
- [ ] 30-minute review call scheduled — nothing goes live without their
      approval.

---

**When all boxes are checked, Expert #1's agent goes live — and Foundry
stops being a demo and starts being a business.**
