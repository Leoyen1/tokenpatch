#!/usr/bin/env sh
set -eu

WORKDIR="${1:-.}"
HOST="${TOKENPATCH_WEB_HOST:-127.0.0.1}"
PORT="${TOKENPATCH_WEB_PORT:-8787}"

python -m mmdev.cli web --workdir "$WORKDIR" --host "$HOST" --port "$PORT"
