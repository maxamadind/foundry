"""Ingest pipeline: file -> text -> chunks -> indexed documents."""
import os
import re

WORD_TARGET = 450          # target words per chunk
MIN_CHUNK_WORDS = 40       # drop tiny fragments

HEADER_RE = re.compile(r"^(#{1,4})\s+(.+?)\s*$")
HR_RE = re.compile(r"^(\*{3,}|-{3,}|_{3,})\s*$")
# Plain-text chapter/section headings, e.g. "CHAPTER 2: The 7 Hidden Oral Flaws"
PLAIN_CHAPTER_RE = re.compile(r"^(CHAPTER|PART|SECTION|APPENDIX)\s+[A-Z0-9]+[:.\s]", re.IGNORECASE)


def looks_like_header(line):
    """Detect plain-text headings: 'CHAPTER N: ...' or short ALL-CAPS lines."""
    s = line.strip()
    if not s or len(s) > 90 or s[0] in "|-*>#❝\"'0123456789":
        return False
    if PLAIN_CHAPTER_RE.match(s):
        return True
    letters = [c for c in s if c.isalpha()]
    if len(letters) >= 8 and all(c.isupper() for c in letters) and s[-1] not in ".!?:":
        return True
    return False


def extract_text(path):
    """Return (text, suggested_title) for .md/.txt/.pdf/.docx."""
    ext = os.path.splitext(path)[1].lower()
    if ext == ".pdf":
        from pypdf import PdfReader
        reader = PdfReader(path)
        text = "\n".join((page.extract_text() or "") for page in reader.pages)
    elif ext == ".docx":
        from docx import Document
        doc = Document(path)
        text = "\n".join(p.text for p in doc.paragraphs)
    else:  # .md, .txt, .markdown
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
    text = re.sub(r"\r\n?", "\n", text)
    title = None
    for line in text.split("\n")[:40]:
        m = HEADER_RE.match(line.strip())
        if m:
            title = m.group(2).strip()
            break
    if not title:
        title = os.path.splitext(os.path.basename(path))[0].replace("-", " ").replace("_", " ").title()
    return text, title


def chunk_markdown(text, min_words=MIN_CHUNK_WORDS, target=WORD_TARGET):
    """Split markdown-ish text into (section_path, text) chunks.

    Section path is the header breadcrumb, e.g. 'The Mouth Code / Chapter 3: ...'.
    Chunks break at paragraph boundaries near `target` words.
    """
    stack = []            # [(level, title)]
    chunks = []
    buf_words, buf_lines = 0, []
    in_table = False

    def section_path():
        return " / ".join(t for _, t in stack)

    def flush():
        nonlocal buf_words, buf_lines
        body = "\n".join(buf_lines).strip()
        words = len(body.split())
        if words >= min_words:
            chunks.append((section_path(), body))
        elif chunks and words > 0:
            # merge tiny tail into previous chunk
            prev_path, prev_body = chunks[-1]
            chunks[-1] = (prev_path, prev_body + "\n\n" + body)
        buf_words, buf_lines = 0, []

    lines_all = text.split("\n")
    n_lines = len(lines_all)
    li = 0
    while li < n_lines:
        raw = lines_all[li]
        li += 1
        line = raw.rstrip()
        if HR_RE.match(line.strip()):
            continue
        m = HEADER_RE.match(line.strip())
        plain = looks_like_header(line)
        if m or plain:
            flush()
            if m:
                level, title = len(m.group(1)), m.group(2).strip()
                title = re.sub(r"\*+", "", title).strip()
            else:
                level, title = 2, line.strip()
            while stack and stack[-1][0] >= level:
                stack.pop()
            if title and len(title) < 160:
                stack.append((level, title))
            continue
        is_table_row = line.strip().startswith("|")
        if is_table_row:
            in_table = True
        elif line.strip():
            in_table = False  # non-blank, non-table line ends the table run
        if not line.strip():
            if buf_lines and buf_lines[-1].strip():
                buf_lines.append("")
            continue
        buf_lines.append(line)
        buf_words += len(line.split())
        # Break near the target at a paragraph-ish boundary — but never
        # split a markdown table across two chunks, and never strand a table
        # in the next chunk when its introduction is here (look ahead).
        if buf_words >= target and not in_table and len(line) < 200:
            ahead = lines_all[li:li + 15]
            table_ahead = any(l.strip().startswith("|") for l in ahead)
            if table_ahead and buf_words < target + 500:
                continue  # keep accumulating; the table stays with its intro
            flush()

    flush()
    return [(p, re.sub(r"\n{3,}", "\n\n", t).strip()) for p, t in chunks]


def ingest_file(conn, agent_id, path, title=None):
    """Full pipeline for one file. Returns the document row."""
    from . import store
    text, auto_title = extract_text(path)
    chunks = chunk_markdown(text)
    if not chunks:
        raise ValueError(f"No usable text extracted from {os.path.basename(path)}")
    return store.add_document(
        conn, agent_id, title or auto_title, os.path.basename(path), chunks
    )
