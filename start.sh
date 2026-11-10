#!/usr/bin/env bash
# Starts the FastAPI backend (port 8000) and the Vite frontend (port 5173).
set -e
ROOT="$(cd "$(dirname "$0")" && pwd)"

(cd "$ROOT/backend" && python3 -m venv .venv 2>/dev/null || true)
source "$ROOT/backend/.venv/bin/activate"
pip install -q -r "$ROOT/backend/requirements.txt"

(cd "$ROOT/backend" && uvicorn app.main:app --reload --port 8000) &
BACK=$!
trap "kill $BACK" EXIT

cd "$ROOT/frontend"
[ -d node_modules ] || npm install
npm run dev
