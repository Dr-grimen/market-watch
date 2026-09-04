#!/usr/bin/env bash
# Startar appen lokalt. Opne http://localhost:8000 på telefonen eller i nettlesaren.
set -euo pipefail
cd "$(dirname "$0")"
python3 -m pip install --quiet -r krav.txt
exec python3 -m uvicorn app.web:app --host 0.0.0.0 --port "${PORT:-8000}" --reload
