#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -d .venv ]; then
  /opt/homebrew/bin/python3.14 -m venv .venv
  ./.venv/bin/pip -q install --upgrade pip
  ./.venv/bin/pip -q install -r requirements.txt
fi

PORT="${PORT:-8077}"
echo "→ PDF House Local: http://127.0.0.1:${PORT}"
exec ./.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port "${PORT}"
