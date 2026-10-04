# Foundry v1 — Test Log

Date: 2026-10-04. All tests run against the live app (`app.py` on
`http://127.0.0.1:5050`) and the answer engine directly. Corpus: Agent #1
**The Mouth Code** (8-book series, 488,311 words, 2,159 chunks) and Agent #2
**Strength Basics** (sample fitness corpus, 11 chunks).

## Verbatim guarantee

Every quote below was programmatically verified: 32/32 sampled quotes are
exact substrings of their cited source chunks (tables: every cell verified
verbatim; only markdown formatting characters are stripped for display).
No quote is ever invented — the engine only returns text copied from the
indexed corpus.

## Hard-question battery (The Mouth Code)

| # | Question | Mode | Result |
|---|----------|------|--------|
| 1 | What are the 7 hidden oral flaws? | answer | Renders the source's master table verbatim: all 7 flaw names, cited to *The Mouth Code / CHAPTER 2: The 7 Hidden Oral Flaws Master Framework* |
| 2 | How does mouth breathing cause sleep apnea? | answer | 3 verbatim passages with doc + section citations |
| 3 | What is the 30-day clinical reset protocol? | answer | Quotes the Part III protocol chapters verbatim |
| 4 | What is tongue posture and why does it matter? | answer | 3 verbatim passages, correct sections |
| 5 | What does the book recommend for neck pain? | answer | 3 verbatim passages, incl. jaw/neck connection |
| 6 | What does Dr. Greenacre say about anxiety and the airway? | answer | Quotes *The Face Code / CHAPTER 4: ADHD, Anxiety & The Airway Brain* — attribution term ("Greenacre") correctly ignored as non-topical |
| 7 | What does the book say about thumb sucking in children? | answer | 3 verbatim passages |
| 8 | What supplements does the book recommend? | answer | 3 verbatim passages, incl. evidence-framed guidance |
| 9 | Who wrote The Mouth Code and what are his credentials? | answer | Dedicated bio handler quotes the About the Author section verbatim |
| 10 | What does the book say about oil pulling? | answer | 3 verbatim passages |
| 11 | What is the capital of France? | **abstain** | "That's outside my training material…" — metaphorical "capital" (brainstem) correctly rejected |
| 12 | Explain quantum computing in simple terms. | **abstain** | Honest abstain with suggested in-corpus questions |

## Cross-domain battery (proves domain-generality)

| Agent | Question | Mode | Result |
|-------|----------|------|--------|
| Strength Basics (fitness) | What is progressive overload? | answer | Verbatim quote, correct citation |
| Strength Basics (fitness) | What rep ranges should I use for muscle growth? | answer | Renders the rep-range **table** verbatim (table path works in 2nd domain) |
| Strength Basics (fitness) | Explain quantum physics. | **abstain** | Correct abstain |
| Strength Basics (fitness) | What rep ranges should I use for muscle growth? (asked of Mouth Code) | **abstain** | Correctly abstains — the dental corpus doesn't cover it |
| Test Plumber (via web UI) | What should never go down the drain? | answer | Verbatim quote from "What Never Goes Down the Drain" section |
| Test Plumber (via web UI) | How do I fix a leaky roof? | **abstain** | Correct abstain |

## Creator-flow test (full loop through the browser UI)

1. Opened `/new`, filled name/tagline/description, uploaded a Markdown
   plumbing guide → HTTP 302 redirect to `/a/test-plumber`. ✅
2. Chat page rendered (200), suggested questions derived from the doc's real
   section headers. ✅
3. Asked two questions via the chat UI path (`/api/chat`): topical answered
   with citation, off-topic abstained. ✅
4. Test agent removed afterwards to keep the demo clean.

## HTTP smoke test

- `GET /` → 200 · `GET /new` → 200
- `GET /a/the-mouth-code` → 200 · `GET /a/strength-basics` → 200
- `POST /api/chat` → 200, correct JSON (`mode`, `lead`, `passages[]` with
  `quote`/`doc_title`/`section_path`, `latency_ms` ~15–130ms)
- Suggested-question chips on the chat page come from real section headers,
  phrased with the agent's name (no domain-specific wording).

## Known limits (v1, documented — not hidden)

- Extractive only: answers are quoted passages, not synthesized prose.
  The single plug-in point is `generate_with_llm()` in
  `foundry/answer.py` (free-tier Gemini documented in-code).
- No semantic/embedding search: FTS5 + BM25 with stemming. Paraphrased
  questions outside the corpus vocabulary may abstain even when a human
  would see the connection.
- Suggested questions derive from section headers; an awkward subtitle can
  occasionally appear as a suggestion.
