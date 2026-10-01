#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
PYTHON_APE=${1:-}
OUT=${2:-"$ROOT/dist/pythoncosmofy.com"}
HOST=${PYTHONCOSMOFY_PYTHON:-python3}
PYTHON_URL=https://github.com/bear0330/python-ape/releases/latest/download/python.com

if [ -n "$PYTHON_APE" ]; then
  test -f "$PYTHON_APE" || { echo "missing Python APE: $PYTHON_APE" >&2; exit 1; }
  set -- --python "$PYTHON_APE"
else
  set -- --python-url "$PYTHON_URL"
fi

mkdir -p "$(dirname -- "$OUT")"
cd "$ROOT"
PYTHONPATH="$ROOT/src" "$HOST" -m cosmofy \
  "$@" \
  --output "$OUT" \
  --args '-m cosmofy --cosmo --clone' \
  src/cosmofy
printf 'Output: %s\n' "$OUT"
