"""Retrieval: FTS5 (porter stemming) + BM25 ranking over an agent's chunks."""
from .answer_tokens import tokenize, STOPWORDS  # noqa  (defined below to avoid cycles)


def build_fts_query(query):
    terms = [t for t in tokenize(query) if t not in STOPWORDS and len(t) > 2]
    # de-dupe, cap length; prefix search lets "breath" match "breathing"
    seen, kept = set(), []
    for t in terms:
        if t not in seen:
            seen.add(t)
            kept.append(t)
        if len(kept) >= 12:
            break
    if not kept:
        return None
    return " OR ".join(f'"{t}"*' for t in kept)


def search(conn, agent_id, query, k=8):
    """Return top-k chunk rows (with bm25 score; lower is better) for the agent."""
    fts_q = build_fts_query(query)
    if not fts_q:
        return []
    rows = conn.execute(
        """SELECT chunk_id, doc_title, section_path, text, bm25(chunks_fts) AS score
           FROM chunks_fts
           WHERE chunks_fts MATCH ? AND agent_id = ?
           ORDER BY score LIMIT ?""",
        (fts_q, agent_id, k),
    ).fetchall()
    return rows
