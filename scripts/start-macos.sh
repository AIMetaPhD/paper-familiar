#!/usr/bin/env bash
# PaperFamiliar native launcher for macOS (Apple Silicon arm64).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
PORT="${PORT:-8420}"
NO_BROWSER="${NO_BROWSER:-0}"

fail() {
  echo ""
  echo "PaperFamiliar could not start:" >&2
  echo "  $1" >&2
  echo "" >&2
  echo "Diagnostics:" >&2
  echo "  root:   $ROOT" >&2
  echo "  arch:   $(uname -m)" >&2
  echo "  python: ${PYTHON:-not found}" >&2
  echo "  port:   $PORT" >&2
  exit "${2:-2}"
}

if [[ "$(uname -m)" != "arm64" ]]; then
  echo "warning: this build targets Apple Silicon (arm64); running on $(uname -m)." >&2
fi

PYTHON=""
for candidate in python3.13 python3.12 python3.11 python3; do
  if command -v "$candidate" >/dev/null 2>&1; then
    version="$("$candidate" -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null || true)"
    major="${version%%.*}"; minor="${version##*.}"
    if [[ "$major" == "3" && "$minor" -ge 11 && "$minor" -le 13 ]]; then
      PYTHON="$candidate"
      break
    fi
  fi
done
[[ -n "$PYTHON" ]] || fail "Python 3.11-3.13 was not found. Install it from https://www.python.org/downloads/." 3

echo "PaperFamiliar"
echo "  python: $PYTHON ($($PYTHON -c 'import platform; print(platform.machine())'))"
echo "  root:   $ROOT"

VENV="$ROOT/.venv"
if [[ ! -x "$VENV/bin/python" ]]; then
  echo "  creating .venv ..."
  "$PYTHON" -m venv "$VENV" || fail "python -m venv failed." 4
fi

[[ -f "$ROOT/src/paperfamiliar/web/dist/index.html" ]] || \
  fail "The web build is missing. Run 'npm --prefix web install && npm --prefix web run build' once in a development checkout." 5

if ! "$VENV/bin/python" -c 'import fastapi, uvicorn, pylatexenc' >/dev/null 2>&1; then
  if [[ -d "$ROOT/wheelhouse" ]]; then
    echo "  installing from the offline wheelhouse ..."
    "$VENV/bin/python" -m pip install --disable-pip-version-check --no-index --find-links "$ROOT/wheelhouse" -e .
  else
    echo "  installing from the network (first run only) ..."
    "$VENV/bin/python" -m pip install --disable-pip-version-check --upgrade pip setuptools wheel
    "$VENV/bin/python" -m pip install --disable-pip-version-check -e .
  fi
fi

if command -v lsof >/dev/null 2>&1 && lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  fail "Port $PORT is already in use. Close it or run PORT=8421 ./scripts/start-macos.sh." 7
fi

export PYTHONUTF8=1
export PYTHONIOENCODING=utf-8
ARGS=(-m paperfamiliar serve --port "$PORT")
if [[ "$NO_BROWSER" == "1" ]]; then
  ARGS+=(--no-browser)
fi

echo "  starting http://127.0.0.1:$PORT"
echo "  press Ctrl+C to stop"
exec "$VENV/bin/python" "${ARGS[@]}"
