#!/usr/bin/env bash
# Fresh machine: venv + dependencies + agents for every channel + doctor.  Usage: ./scripts/setup.sh [--youtube]
set -euo pipefail
cd "$(dirname "$0")/.."
PY="${PYTHON:-python3}"
[ -d .venv ] || "$PY" -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
pip install -q -r requirements.txt
[ "${1:-}" = "--youtube" ] && pip install -q -r requirements-youtube.txt
mkdir -p secrets && chmod 700 secrets          # gitignored; per-channel folders secrets/<credentials_ref>/
command -v ffmpeg >/dev/null || echo "WARN: ffmpeg not found (install it for video output)"
python -m core render-agents || true           # channels come from git; agents are generated per machine
python -m core list-channels
python -m core doctor || true
echo "Next: python -m core new-channel <slug>   or   python -m core start-script --channel example-story \"an idea\""
