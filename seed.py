"""Seed Foundry agents from agents.json — config-level, no code changes.

Usage:  .venv/bin/python seed.py

Reads agents.json, creates any agent whose slug doesn't exist yet, and ingests
every supported document (.md/.txt/.pdf/.docx) in its docs_dir.

To add a new domain (fitness coach, lawyer, plumber, ...):
  1. Add one block to agents.json with a name and docs_dir.
  2. Run this script. The new agent gets a shareable chat link immediately.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from foundry import store, ingest

SUPPORTED = {".md", ".txt", ".pdf", ".docx"}


def main():
    cfg = json.loads((ROOT / "agents.json").read_text())
    conn = store.init_db()  # creates schema if missing (safe on existing DBs)
    for spec in cfg["agents"]:
        slug = spec["slug"]
        existing = store.get_agent(conn, slug)
        if existing:
            print(f"[{slug}] already exists — skipping")
            continue
        agent = store.create_agent(
            conn,
            name=spec["name"],
            tagline=spec.get("tagline", ""),
            description=spec.get("description", ""),
            payment_link=spec.get("payment_link", ""),
        )
        docs_dir = ROOT / spec["docs_dir"] if not str(spec["docs_dir"]).startswith("/") else Path(spec["docs_dir"])
        files = sorted(p for p in (docs_dir.iterdir() if docs_dir.is_dir() else [])
                       if p.suffix.lower() in SUPPORTED and p.is_file())
        if not files:
            print(f"[{slug}] WARNING: no documents found in {docs_dir}")
            continue
        total_chunks = 0
        for path in files:
            doc = ingest.ingest_file(conn, agent["id"], str(path))
            total_chunks += doc["chunk_count"]
            print(f"[{slug}] {path.name} -> {doc['chunk_count']} chunks")
        print(f"[{slug}] DONE — {total_chunks} chunks. Chat: /a/{slug}\n")


if __name__ == "__main__":
    main()
