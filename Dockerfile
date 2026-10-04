# Foundry v1 — production image ($0 stack).
# Render free tier builds this with one tap (see DEPLOY.md).
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN mkdir -p uploads

# Bake the demo agent's index into the image so cold starts are instant.
# (agents.json entries whose docs_dir doesn't exist in the image are skipped
# with a warning — e.g. the local-only Mouth Code manuscripts.)
RUN python seed.py

EXPOSE 10000

# Single worker: SQLite is one-writer; threads handle concurrent chats.
CMD gunicorn app:app --bind 0.0.0.0:${PORT:-10000} --workers 1 --threads 4 --timeout 120
