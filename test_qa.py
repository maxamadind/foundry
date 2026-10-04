"""QA probe: run hard questions through the answer engine, print results."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from foundry import store  # noqa: E402
from foundry.answer import answer_question  # noqa: E402

QUESTIONS = [
    "What are the 7 hidden oral flaws?",
    "How does mouth breathing cause sleep apnea?",
    "What is the 30-day clinical reset protocol?",
    "What does the book say about tongue posture?",
    "How are neck pain and the jaw connected?",
    "What does Dr. Greenacre say about anxiety and the airway?",
    "What does the book say about thumb sucking in children?",
    "What supplements does the book recommend?",
    "Who wrote The Mouth Code and what are his credentials?",
    "What does the book say about oil pulling?",
    "What is the capital of France?",
    "Explain quantum computing in simple terms.",
]

conn = store.get_db()
agent = store.get_agent(conn, "the-mouth-code")

for i, q in enumerate(QUESTIONS, 1):
    r = answer_question(conn, agent, q)
    print(f"\n{'='*70}\nQ{i}: {q}\n  mode={r['mode']} latency={r['latency_ms']}ms")
    print(f"  lead: {r['lead'][:160]}")
    for j, p in enumerate(r["passages"], 1):
        print(f"  [{j}] {p['doc_title']} / {p['section_path'][:70]}")
        print(f"      \"{p['quote'][:220]}...\"")
    if r.get("suggested"):
        print(f"  suggested: {r['suggested'][:2]}")
conn.close()
