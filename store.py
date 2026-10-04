"""SQLite storage for Foundry: agents, documents, chunks + FTS5 index."""
import os
import re
import sqlite3
import time
import secrets

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.environ.get("FOUNDRY_DB", os.path.join(BASE_DIR, "foundry.db"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS agents (
    id          TEXT PRIMARY KEY,
    slug        TEXT UNIQUE NOT NULL,
    name        TEXT NOT NULL,
    tagline     TEXT DEFAULT '',
    description TEXT DEFAULT '',
    payment_link TEXT DEFAULT '',
    created_at  REAL NOT NULL,
    doc_count   INTEGER DEFAULT 0,
    chunk_count INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS documents (
    id          TEXT PRIMARY KEY,
    agent_id    TEXT NOT NULL,
    title       TEXT NOT NULL,
    filename    TEXT NOT NULL,
    word_count  INTEGER DEFAULT 0,
    chunk_count INTEGER DEFAULT 0,
    added_at    REAL NOT NULL,
    FOREIGN KEY(agent_id) REFERENCES agents(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS chunks (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id     TEXT NOT NULL,
    doc_id       TEXT NOT NULL,
    ord          INTEGER NOT NULL,
    section_path TEXT NOT NULL,
    text         TEXT NOT NULL,
    FOREIGN KEY(agent_id) REFERENCES agents(id) ON DELETE CASCADE,
    FOREIGN KEY(doc_id) REFERENCES documents(id) ON DELETE CASCADE
);
CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
    text, section_path, doc_title,
    chunk_id UNINDEXED, agent_id UNINDEXED,
    tokenize='porter'
);
"""


def get_db(path=None):
    conn = sqlite3.connect(path or DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(path=None):
    conn = get_db(path)
    conn.executescript(SCHEMA)
    # Idempotent migration for DBs created before payment_link existed.
    try:
        conn.execute("ALTER TABLE agents ADD COLUMN payment_link TEXT DEFAULT ''")
    except sqlite3.OperationalError:
        pass  # column already there
    conn.commit()
    return conn


def slugify(name):
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug[:60] or "agent"


def unique_slug(conn, base):
    slug, i = base, 2
    while conn.execute("SELECT 1 FROM agents WHERE slug=?", (slug,)).fetchone():
        slug = f"{base}-{i}"
        i += 1
    return slug


def create_agent(conn, name, tagline="", description="", payment_link=""):
    agent_id = secrets.token_hex(8)
    slug = unique_slug(conn, slugify(name))
    conn.execute(
        "INSERT INTO agents (id, slug, name, tagline, description, payment_link, created_at)"
        " VALUES (?,?,?,?,?,?,?)",
        (agent_id, slug, name.strip(), tagline.strip(), description.strip(),
         payment_link.strip(), time.time()),
    )
    conn.commit()
    return get_agent(conn, agent_id)


def set_payment_link(conn, agent_id, payment_link):
    """Owner sets/updates the Stripe Payment Link shown on the public page."""
    conn.execute("UPDATE agents SET payment_link=? WHERE id=?",
                 (payment_link.strip(), agent_id))
    conn.commit()
    return get_agent(conn, agent_id)


def get_agent(conn, agent_id_or_slug):
    return conn.execute(
        "SELECT * FROM agents WHERE id=? OR slug=?", (agent_id_or_slug, agent_id_or_slug)
    ).fetchone()


def list_agents(conn):
    return conn.execute("SELECT * FROM agents ORDER BY created_at DESC").fetchall()


def agent_documents(conn, agent_id):
    return conn.execute(
        "SELECT * FROM documents WHERE agent_id=? ORDER BY added_at", (agent_id,)
    ).fetchall()


def add_document(conn, agent_id, title, filename, chunk_list):
    """chunk_list: list of (section_path, text). Returns document row."""
    doc_id = secrets.token_hex(8)
    word_count = sum(len(t.split()) for _, t in chunk_list)
    conn.execute(
        "INSERT INTO documents (id, agent_id, title, filename, word_count, chunk_count, added_at)"
        " VALUES (?,?,?,?,?,?,?)",
        (doc_id, agent_id, title, filename, word_count, len(chunk_list), time.time()),
    )
    for ord_, (section_path, text) in enumerate(chunk_list):
        cur = conn.execute(
            "INSERT INTO chunks (agent_id, doc_id, ord, section_path, text) VALUES (?,?,?,?,?)",
            (agent_id, doc_id, ord_, section_path, text),
        )
        conn.execute(
            "INSERT INTO chunks_fts (text, section_path, doc_title, chunk_id, agent_id)"
            " VALUES (?,?,?,?,?)",
            (text, section_path, title, cur.lastrowid, agent_id),
        )
    conn.execute(
        "UPDATE agents SET doc_count = doc_count + 1, chunk_count = chunk_count + ? WHERE id=?",
        (len(chunk_list), agent_id),
    )
    conn.commit()
    return conn.execute("SELECT * FROM documents WHERE id=?", (doc_id,)).fetchone()


def get_chunk(conn, chunk_id):
    return conn.execute(
        """SELECT c.*, d.title AS doc_title FROM chunks c
           JOIN documents d ON d.id = c.doc_id WHERE c.id=?""",
        (chunk_id,),
    ).fetchone()


def agent_sections(conn, agent_id, limit=12):
    """Top-level section headers, used for suggested questions. Real data only."""
    rows = conn.execute(
        """SELECT DISTINCT section_path FROM chunks
           WHERE agent_id=? AND section_path != '' ORDER BY ord LIMIT ?""",
        (agent_id, limit * 4),
    ).fetchall()
    seen, out = set(), []
    for r in rows:
        top = r["section_path"].split(" / ")[0].strip()
        if top and top.lower() not in seen and len(top) < 90:
            seen.add(top.lower())
            out.append(top)
        if len(out) >= limit:
            break
    return out
