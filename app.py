"""Foundry v1 — upload knowledge, get a citation-backed AI agent. $0 stack."""
import os
import secrets
import time
from functools import wraps

from flask import Flask, request, jsonify, render_template, redirect, url_for, abort, session
from werkzeug.utils import secure_filename

from foundry import store, ingest
from foundry.answer import answer_question, suggested_questions

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
ALLOWED_EXTS = {".md", ".markdown", ".txt", ".pdf", ".docx"}

# --- Creator-flow auth -------------------------------------------------------
# FOUNDRY_ADMIN_PASSCODE: when set, creating agents (and everything that
# changes an agent) requires the passcode. Public chat pages stay open.
# When unset (local dev), the creator flow is open — no passcode needed.
ADMIN_PASSCODE = os.environ.get("FOUNDRY_ADMIN_PASSCODE", "")

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 60 * 1024 * 1024  # 60 MB per request
app.secret_key = os.environ.get("FOUNDRY_SECRET_KEY") or secrets.token_hex(32)
# Note: without FOUNDRY_SECRET_KEY the key is random per boot, so admin
# sessions end on restart/redeploy. Set the env var for persistent logins.


def db():
    return store.init_db()


def is_admin():
    return (not ADMIN_PASSCODE) or session.get("foundry_admin") is True


def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if is_admin():
            return fn(*args, **kwargs)
        return redirect(url_for("admin_login", next=request.path))
    return wrapper


def valid_payment_link(link):
    """Accept only absolute http(s) URLs — the Stripe Payment Link the owner pastes."""
    link = (link or "").strip()
    if not link:
        return ""
    if link.startswith(("http://", "https://")) and " " not in link:
        return link
    return None


@app.route("/")
def index():
    conn = db()
    agents = store.list_agents(conn)
    conn.close()
    return render_template("index.html", agents=agents, is_admin=is_admin(),
                           admin_enabled=bool(ADMIN_PASSCODE))


@app.route("/admin", methods=["GET", "POST"])
def admin_login():
    if not ADMIN_PASSCODE:
        return redirect(url_for("index"))
    error = ""
    if request.method == "POST":
        if secrets.compare_digest(request.form.get("passcode", ""), ADMIN_PASSCODE):
            session["foundry_admin"] = True
            nxt = request.args.get("next") or request.form.get("next") or url_for("index")
            if not nxt.startswith("/"):
                nxt = url_for("index")
            return redirect(nxt)
        error = "Wrong passcode. Try again."
    return render_template("admin.html", error=error,
                           next=request.args.get("next", ""))


@app.route("/admin/logout")
def admin_logout():
    session.pop("foundry_admin", None)
    return redirect(url_for("index"))


@app.route("/new", methods=["GET", "POST"])
@admin_required
def new_agent():
    if request.method == "GET":
        return render_template("new.html")
    conn = db()
    name = (request.form.get("name") or "").strip()
    tagline = (request.form.get("tagline") or "").strip()
    description = (request.form.get("description") or "").strip()
    payment_link = valid_payment_link(request.form.get("payment_link"))
    if not name:
        conn.close()
        return render_template("new.html", error="Give your agent a name."), 400
    if payment_link is None:
        conn.close()
        return render_template("new.html",
                               error="That payment link doesn't look like a URL — paste the full link starting with https://"), 400

    files = [f for f in request.files.getlist("docs") if f and f.filename]
    if not files:
        conn.close()
        return render_template("new.html", error="Upload at least one document (PDF, Word, Markdown, or text)."), 400

    agent = store.create_agent(conn, name, tagline, description, payment_link)
    agent_dir = os.path.join(UPLOAD_DIR, agent["id"])
    os.makedirs(agent_dir, exist_ok=True)

    errors = []
    for f in files:
        ext = os.path.splitext(f.filename)[1].lower()
        if ext not in ALLOWED_EXTS:
            errors.append(f"{f.filename}: unsupported file type.")
            continue
        safe = secure_filename(f.filename)
        path = os.path.join(agent_dir, safe)
        f.save(path)
        try:
            ingest.ingest_file(conn, agent["id"], path)
        except Exception as e:  # noqa: BLE001 — surface per-file ingest errors
            errors.append(f"{safe}: could not read ({e}).")

    agent = store.get_agent(conn, agent["id"])
    conn.close()
    if agent["doc_count"] == 0:
        return render_template("new.html",
                               error="None of those files contained readable text. " + " ".join(errors)), 400
    return redirect(url_for("agent_page", slug=agent["slug"]))


@app.route("/a/<slug>")
def agent_page(slug):
    conn = db()
    agent = store.get_agent(conn, slug)
    if not agent:
        conn.close()
        abort(404)
    docs = store.agent_documents(conn, agent["id"])
    sugg = suggested_questions(conn, agent, limit=4)
    conn.close()
    return render_template("agent.html", agent=agent, docs=docs, suggested=sugg,
                           is_admin=is_admin())


@app.route("/admin/agents/<agent_id>/payment-link", methods=["POST"])
@admin_required
def update_payment_link(agent_id):
    conn = db()
    agent = store.get_agent(conn, agent_id)
    if not agent:
        conn.close()
        abort(404)
    link = valid_payment_link(request.form.get("payment_link"))
    if link is None:
        conn.close()
        return "That doesn't look like a URL — paste the full link starting with https://", 400
    store.set_payment_link(conn, agent_id, link)
    conn.close()
    return redirect(url_for("agent_page", slug=agent["slug"]))


@app.route("/api/chat", methods=["POST"])
def api_chat():
    data = request.get_json(force=True, silent=True) or {}
    agent_ref = data.get("agent_id", "")
    question = (data.get("question") or "").strip()
    if not agent_ref or not question:
        return jsonify({"error": "agent_id and question are required."}), 400
    conn = db()
    agent = store.get_agent(conn, agent_ref)
    if not agent:
        conn.close()
        return jsonify({"error": "Unknown agent."}), 404
    t0 = time.time()
    try:
        result = answer_question(conn, agent, question)
    finally:
        conn.close()
    result["server_ms"] = int((time.time() - t0) * 1000)
    return jsonify(result)


@app.route("/api/agents/<agent_id>/docs", methods=["POST"])
@admin_required
def api_add_docs(agent_id):
    conn = db()
    agent = store.get_agent(conn, agent_id)
    if not agent:
        conn.close()
        return jsonify({"error": "Unknown agent."}), 404
    files = [f for f in request.files.getlist("docs") if f and f.filename]
    agent_dir = os.path.join(UPLOAD_DIR, agent["id"])
    os.makedirs(agent_dir, exist_ok=True)
    added, errors = 0, []
    for f in files:
        ext = os.path.splitext(f.filename)[1].lower()
        if ext not in ALLOWED_EXTS:
            errors.append(f"{f.filename}: unsupported file type.")
            continue
        path = os.path.join(agent_dir, secure_filename(f.filename))
        f.save(path)
        try:
            ingest.ingest_file(conn, agent["id"], path)
            added += 1
        except Exception as e:  # noqa: BLE001
            errors.append(f"{f.filename}: could not read ({e}).")
    agent = store.get_agent(conn, agent["id"])
    conn.close()
    return jsonify({"added": added, "errors": errors,
                    "doc_count": agent["doc_count"], "chunk_count": agent["chunk_count"]})


@app.route("/api/agents/<agent_id>/suggest")
def api_suggest(agent_id):
    conn = db()
    agent = store.get_agent(conn, agent_id)
    if not agent:
        conn.close()
        return jsonify({"error": "Unknown agent."}), 404
    out = suggested_questions(conn, agent)
    conn.close()
    return jsonify({"suggested": out})


if __name__ == "__main__":
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    store.init_db().close()
    # On a host (Render etc.) PORT is injected and we must bind 0.0.0.0;
    # locally we keep the loopback-only default.
    port = int(os.environ.get("PORT", 5050))
    host = "0.0.0.0" if os.environ.get("PORT") else "127.0.0.1"
    app.run(host=host, port=port, debug=False)
