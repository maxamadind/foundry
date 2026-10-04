"""Extractive answer engine.

v1 answers STRICTLY from the agent's corpus: it retrieves the most relevant
passages and quotes them verbatim with citations. It never invents content.
When the corpus doesn't cover the question, it abstains honestly.

Optional LLM plug-in point: `generate_with_llm()` — if FOUNDRY_LLM_PROVIDER
and FOUNDRY_LLM_KEY are set (e.g. the free tier of Google AI Studio's Gemini),
an abstractive answer is synthesized GROUNDED ONLY in the retrieved passages.
With no key set (the $0 default), the extractive answer below is used as-is.
"""
import math
import os
import re
import time

from .answer_tokens import tokenize, STOPWORDS, stem_tokens
from .retrieve import search

# BM25 from FTS5 is negative; more negative = better match.
ABSTAIN_BM25 = -2.5
MAX_PASSAGES = 3
MAX_QUOTE_CHARS = 420

# Words that carry no topical meaning in questions (in addition to STOPWORDS).
QUESTION_WORDS = frozenset({
    "book", "books", "say", "says", "said", "does", "recommend", "recommends",
    "recommended", "tell", "tells", "explain", "explains", "describe", "describes",
    "mean", "means", "about", "chapter", "page",
})

# Minimal synonym expansion for common question phrasings (retrieval only).
SYNONYMS = {
    "wrote": ["author", "written"],
    "written": ["author"],
    "write": ["author"],
    "author": ["written"],
}

NUMBER_WORDS = {
    "zero": "0", "one": "1", "two": "2", "three": "3", "four": "4",
    "five": "5", "six": "6", "seven": "7", "eight": "8", "nine": "9",
    "ten": "10", "eleven": "11", "twelve": "12", "fourteen": "14",
    "thirty": "30",
}


def normalize_numbers(tokens):
    return [NUMBER_WORDS.get(t, t) for t in tokens]


def content_terms(query):
    """Topical terms from a question: stopwords/question-words removed,
    digits kept, number-words normalized."""
    terms = [t for t in tokenize(query)
             if (t not in STOPWORDS and t not in QUESTION_WORDS)
             and (len(t) > 2 or t.isdigit())]
    return normalize_numbers(terms)


SENT_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"“\(\[])")
GREETINGS = {"hi", "hello", "hey", "yo", "sup", "thanks", "thank", "ok", "okay"}


def split_sentences(text):
    text = re.sub(r"\s+", " ", text).strip()
    parts = SENT_SPLIT.split(text)
    return [p.strip() for p in parts if p.strip()]


def table_row_units(text):
    """Treat markdown table rows as quotable units (rows lack sentence punctuation)."""
    units = []
    for line in text.split("\n"):
        s = line.strip()
        if not s.startswith("|"):
            continue
        if all(set(c) <= set(":-| ") for c in s):
            continue  # separator row
        cells = [re.sub(r"\*+", "", c).strip() for c in s.strip().strip("|").split("|")]
        cells = [c for c in cells if c]
        if cells:
            units.append(("table", " · ".join(cells)))
    return units


def score_sentences(query_terms, chunks, min_distinct=2):
    """Score every sentence (and table row) in the retrieved chunks.

    Table rows get a lower evidence bar when the chunk's section heading
    already matches the question — the heading establishes topicality, so the
    table itself needs less term overlap to qualify as the answer.
    """
    n = len(chunks)
    df = {}
    for t in query_terms:
        df[t] = sum(1 for c in chunks if t in c["_tokens"])
    idf = {t: math.log((n + 1) / (df[t] + 1)) + 1.0 for t in query_terms}
    # The question's most distinctive term must appear in the evidence.
    # Without this, "What is the capital of France?" matches a metaphorical
    # "capital" (brainstem) and answers instead of abstaining.
    # Terms absent from every retrieved chunk (e.g. the author's name used as
    # attribution: "What does Dr. Greenacre say about anxiety?") are ignored
    # for this purpose — they describe who, not what the question is about.
    pool = [t for t in query_terms if df[t] >= 1] or list(query_terms)
    rarest = max(pool, key=lambda t: idf[t]) if pool else None

    scored = []
    for ci, c in enumerate(chunks):
        table_min = 1 if c.get("_section_hits", 0) >= 2 else min_distinct
        # When the section heading itself matches 2+ query terms, topicality
        # is established by the heading — the rarest-term guard relaxes and
        # sentences just need corroborating overlap.
        need_rarest = rarest is not None and c.get("_section_hits", 0) < 2
        before = len(scored)
        sents = split_sentences(c["text"])
        units = [("sentence", s) for s in sents]
        # Adjacent sentence pairs: evidence often spans a boundary
        # ("...manifests as something equally devastating: Yet their
        # anxiety did not stem from..."). The pair is quoted verbatim.
        for i in range(len(sents) - 1):
            pair = sents[i] + " " + sents[i + 1]
            if 60 <= len(pair) <= 800:
                units.append(("pair", pair))
        units += table_row_units(c["text"])
        for kind, sent in units:
            if len(sent) < 40 or len(sent) > 700:
                continue
            stoks = stem_tokens(normalize_numbers(tokenize(sent)))
            if not stoks:
                continue
            tf = {}
            for t in stoks:
                tf[t] = tf.get(t, 0) + 1
            hits = [t for t in query_terms if t in tf]
            if not hits:
                continue
            if need_rarest and rarest not in hits:
                continue
            bar = table_min if kind == "table" else min_distinct
            if len(hits) < bar:
                continue
            score = sum(tf[t] * idf[t] for t in hits)
            scored.append({
                "chunk_idx": ci,
                "sentence": sent,
                "kind": kind,
                "score": score,
                "distinct": len(hits),
                "bar": bar,
            })
        # Section matched strongly but no sentence shares its vocabulary
        # (e.g. section "What Never Goes Down the Drain", body says "No
        # grease, ever"): fall back to the section's lead sentence, quoted
        # verbatim, ranked modestly so genuine sentence matches still win.
        if len(scored) == before and c.get("_section_hits", 0) >= 2:
            lead = next((s for s in sents if 40 <= len(s) <= 700), None)
            if lead:
                scored.append({
                    "chunk_idx": ci,
                    "sentence": lead,
                    "kind": "lead",
                    "score": float(min_distinct),
                    "distinct": 0,
                    "bar": min_distinct,
                })
    return scored


def answer_question(conn, agent, query):
    """Return a structured answer dict. Always JSON-serializable."""
    t0 = time.time()
    query = (query or "").strip()
    q_terms = content_terms(query)
    q_stem = stem_tokens(q_terms)  # matches FTS5's porter tokenization

    if query.lower() in GREETINGS or not q_terms:
        return {
            "mode": "intro",
            "lead": _intro_lead(agent),
            "passages": [],
            "suggested": suggested_questions(conn, agent),
            "latency_ms": _ms(t0),
        }

    # Dedicated handler: "who wrote / who is the author" -> quote the bio section.
    raw_tokens = set(tokenize(query))
    if ({"wrote", "written", "author", "authors"} & raw_tokens) or (
            "who" in raw_tokens and any(w in raw_tokens for w in ("wrote", "book", "author"))):
        author_hit = _author_answer(conn, agent, t0)
        if author_hit:
            return author_hit

    # Synonym expansion for retrieval (question phrasing -> corpus phrasing).
    retrieval_terms = list(q_terms)
    for t in q_terms:
        retrieval_terms.extend(SYNONYMS.get(t, []))
    # k=30 gives the section-heading boost enough candidates to promote:
    # attribution terms ("Dr. Greenacre") can otherwise crowd genuinely
    # topical chunks out of a smaller top-k.
    chunks = search(conn, agent["id"], " ".join(retrieval_terms), k=30)
    if not chunks or chunks[0]["score"] > ABSTAIN_BM25:
        return _abstain(conn, agent, query, t0)

    # Re-rank: chunks whose SECTION HEADING matches the question outrank body matches.
    # Navigational meta-sections (reading lists, indexes) are demoted — they
    # describe the books rather than answering from them.
    META_SECTIONS = ("further reading", "reference index", "table of contents",
                       "end-of-chapter")
    section_hits = {}

    def boosted(c):
        path = (c["section_path"] or "").lower()
        hits = sum(1 for t in q_terms if t in path)
        section_hits[c["chunk_id"]] = hits
        penalty = 6.0 if any(m in path for m in META_SECTIONS) else 0.0
        return c["score"] - 4.0 * hits + penalty

    chunks = sorted(chunks, key=boosted)

    chunk_dicts = []
    for r in chunks[:6]:
        toks = set(stem_tokens(normalize_numbers(tokenize(r["text"]))))
        chunk_dicts.append({
            "chunk_id": r["chunk_id"],
            "doc_title": r["doc_title"],
            "section_path": r["section_path"],
            "text": r["text"],
            "_tokens": toks,
            "_section_hits": section_hits.get(r["chunk_id"], 0),
            "score": r["score"],
        })

    # Multi-term questions need at least two distinct terms in the evidence
    # unit — one shared word ("capital") must not be enough to answer
    # "What is the capital of France?".
    min_distinct = 2 if len(q_terms) >= 2 else 1
    cands = [s for s in score_sentences(q_stem, chunk_dicts, min_distinct)
             if s["score"] >= 1.0 * s["bar"]]
    if not cands:
        return _abstain(conn, agent, query, t0)

    cands.sort(key=lambda s: (-s["score"], s["chunk_idx"]))

    # One passage per chunk: the best candidate wins, but when the chunk's
    # TABLE matched the query and the section is topical, the table itself
    # is the denser answer — render it instead of a single sentence.
    best_per_chunk = {}
    for c in cands:
        if c["chunk_idx"] not in best_per_chunk:
            best_per_chunk[c["chunk_idx"]] = c

    passages = []
    for ci, best in best_per_chunk.items():
        chunk = chunk_dicts[ci]
        table_cands = [c for c in cands
                       if c["chunk_idx"] == ci and c["kind"] == "table"]
        if table_cands and chunk.get("_section_hits", 0) >= 2:
            quote = _expand_quote(chunk["text"], table_cands[0]["sentence"])
        elif best["kind"] == "pair":
            quote = best["sentence"]
        else:
            quote = _expand_quote(chunk["text"], best["sentence"])
        quote = clean_quote(quote)
        passages.append({
            "quote": quote,
            "doc_title": chunk["doc_title"],
            "section_path": chunk["section_path"],
            "chunk_id": chunk["chunk_id"],
        })
        if len(passages) >= MAX_PASSAGES:
            break

    if not passages:
        return _abstain(conn, agent, query, t0)

    # Optional LLM synthesis layer (grounded only in these passages).
    llm_text = generate_with_llm(query, passages)

    return {
        "mode": "answer",
        "lead": f"Here's what {agent['name']} says about this — quoted directly from the source material:",
        "passages": passages,
        "llm_synthesis": llm_text,
        "suggested": [],
        "latency_ms": _ms(t0),
    }


def clean_quote(q):
    """Light markdown cleanup for display. Words stay verbatim; only
    formatting characters (bold/italic markers, code fences, heading
    hashes, quote markers) are removed so quotes read cleanly in chat."""
    q = re.sub(r"```+\w*\n?", "", q)          # code fences
    q = q.replace("**", "")                    # bold
    q = re.sub(r"(?<!\w)\*(?!\w)", "", q)       # stray asterisks
    q = re.sub(r"^#{1,4}\s+", "", q, flags=re.M)  # heading markers
    q = re.sub(r"^>\s?", "", q, flags=re.M)    # quote markers
    q = re.sub(r"[ \t]+", " ", q)
    return q.strip()


def _expand_quote(chunk_text, sentence):
    """Include a following sentence when it adds context, capped at MAX_QUOTE_CHARS.
    If the match sits inside a markdown table, quote the table rows instead —
    rendered readably but with verbatim cell content."""
    lines = chunk_text.split("\n")
    # locate the matched sentence's line (short prefix: headings may be brief).
    # Table-row units were normalized ("a · b"), so fall back to the first
    # table run in the chunk when the unit isn't found verbatim.
    needle = sentence[:22].strip()
    idx = next((i for i, ln in enumerate(lines) if needle and needle in ln), None)
    table_runs = []
    i = 0
    while i < len(lines):
        if lines[i].strip().startswith("|"):
            s = i
            while i + 1 < len(lines) and lines[i + 1].strip().startswith("|"):
                i += 1
            table_runs.append((s, i))
        i += 1
    near = []
    if idx is not None:
        # find table runs anywhere near the match (within 12 lines either way)
        near = [r for r in table_runs if r[0] - 12 <= idx <= r[1] + 2]
    elif table_runs:
        near = [table_runs[0]]  # table-row unit: render the chunk's table
    if near:
        s, e = near[0]
        rows, rows_short = [], []
        for ln in lines[s:e + 1]:
            cells = [c.strip() for c in ln.strip().strip("|").split("|")]
            if all(set(c) <= set(":- ") for c in cells):
                continue  # separator row
            cells = [re.sub(r"\*+", "", c).strip() for c in cells if c.strip()]
            if cells:
                rows.append(" · ".join(cells))
                rows_short.append(" · ".join(cells[:2]))
            if len(rows) >= 8:
                break
        table = "\n".join(rows)
        # Tables are dense answers: allow a long cap so the table isn't cut
        # mid-row. Very wide tables render condensed (identifier columns only);
        # cell content stays verbatim either way.
        if len(table) > 1600:
            table = "\n".join(rows_short)
        if len(table) <= 1600:
            return table[:1600].strip()
    sents = split_sentences(chunk_text)
    try:
        i = next(i for i, s in enumerate(sents) if s == sentence)
    except StopIteration:
        i = 0
    quote = sents[i] if i < len(sents) else sentence
    if i + 1 < len(sents) and len(quote) + len(sents[i + 1]) < MAX_QUOTE_CHARS:
        quote += " " + sents[i + 1]
    return quote[:MAX_QUOTE_CHARS].strip()


def _author_answer(conn, agent, t0):
    """Quote the 'About the Author' section verbatim. Returns None if absent."""
    rows = conn.execute(
        """SELECT c.text, c.section_path, d.title AS doc_title, d.added_at FROM chunks c
           JOIN documents d ON d.id = c.doc_id
           WHERE c.agent_id = ? AND lower(c.section_path) LIKE '%about the author%'
           ORDER BY d.added_at, c.ord LIMIT 2""",
        (agent["id"],)).fetchall()
    if not rows:
        return None
    sents = split_sentences(rows[0]["text"])
    # first two substantive sentences of the bio
    bio = " ".join(s for s in sents[:3] if len(s) > 30)[:MAX_QUOTE_CHARS]
    if not bio:
        return None
    return {
        "mode": "answer",
        "lead": f"Here's what {agent['name']} says about this — quoted directly from the source material:",
        "passages": [{
            "quote": bio.strip(),
            "doc_title": rows[0]["doc_title"],
            "section_path": rows[0]["section_path"],
            "chunk_id": None,
        }],
        "llm_synthesis": None,
        "suggested": [],
        "latency_ms": _ms(t0),
    }


def _abstain(conn, agent, query, t0):
    docs = conn.execute(
        "SELECT title FROM documents WHERE agent_id=? ORDER BY added_at", (agent["id"],)
    ).fetchall()
    scope = ", ".join(d["title"] for d in docs) if docs else "its source material"
    return {
        "mode": "abstain",
        "lead": (f"That's outside my training material. I only answer from {agent['name']} "
                 f"({scope}). Try one of the suggested questions below."),
        "passages": [],
        "suggested": suggested_questions(conn, agent, limit=4),
        "latency_ms": _ms(t0),
    }


def _intro_lead(agent):
    tag = f" — {agent['tagline']}" if agent["tagline"] else ""
    return (f"You're chatting with **{agent['name']}**{tag}. "
            f"Ask anything covered in its source material and I'll answer with direct quotes.")


def suggested_questions(conn, agent, limit=6):
    """Real suggested questions derived from the agent's actual section headers."""
    from . import store
    agent_id = agent["id"]
    agent_name = agent["name"]
    docs = {d["id"]: d["title"] for d in store.agent_documents(conn, agent_id)}
    rows = conn.execute(
        "SELECT doc_id, section_path FROM chunks WHERE agent_id=? AND section_path != ''"
        " ORDER BY doc_id, ord LIMIT 400", (agent_id,)).fetchall()
    seen, out = set(), []
    for r in rows:
        parts = [p.strip() for p in r["section_path"].split(" / ") if p.strip()]
        # Prefer the deepest header that isn't the document's own title.
        doc_title = docs.get(r["doc_id"], "").lower()
        cands = [p for p in reversed(parts)
                 if p.lower() != doc_title and len(p) < 80
                 and not any(w in p.lower() for w in
                             ("copyright", "dedication", "table of contents", "about the author",
                              "acknowledgment", "further reading", "end-of-chapter", "references"))]
        if not cands:
            continue
        label = cands[0]
        key = label.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(f"What does {agent_name} say about {label.lower()}?")
        if len(out) >= limit:
            break
    return out


def _ms(t0):
    return int((time.time() - t0) * 1000)


# ---------------------------------------------------------------------------
# Optional LLM plug-in (free-tier friendly). $0 default: unset -> extractive only.
# ---------------------------------------------------------------------------
def generate_with_llm(question, passages):
    """Synthesize a grounded summary from retrieved passages.

    Enable by setting:
        FOUNDRY_LLM_PROVIDER=gemini
        FOUNDRY_LLM_KEY=<free key from Google AI Studio — $0 tier>

    Returns None when not configured (extractive answer is used instead).
    The prompt below FORBIDS using anything beyond the supplied passages.
    """
    provider = os.environ.get("FOUNDRY_LLM_PROVIDER", "").lower()
    key = os.environ.get("FOUNDRY_LLM_KEY", "")
    if not provider or not key or not passages:
        return None

    context = "\n\n".join(
        f"[Source {i+1}: {p['doc_title']} — {p['section_path']}]\n{p['quote']}"
        for i, p in enumerate(passages)
    )
    prompt = (
        "You answer ONLY from the sources below. Rules:\n"
        "1. Every factual claim must come from the sources; cite like [1], [2].\n"
        "2. If the sources don't cover something, say so — never invent.\n"
        "3. Keep it under 120 words, plain language.\n\n"
        f"Question: {question}\n\nSources:\n{context}"
    )

    if provider == "gemini":
        import json
        import urllib.request
        body = json.dumps({"contents": [{"parts": [{"text": prompt}]}]}).encode()
        req = urllib.request.Request(
            "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent",
            data=body, headers={"Content-Type": "application/json", "x-goog-api-key": key},
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode())
            return data["candidates"][0]["content"]["parts"][0]["text"].strip()
        except Exception:
            return None
    return None
