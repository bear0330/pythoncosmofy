#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
PYTHON_APE=${1:-}
OUT=${2:-"$ROOT/dist/pythoncosmofy.com"}
HOST=${PYTHONCOSMOFY_PYTHON:-python3}

if [ -z "$PYTHON_APE" ]; then
  echo "usage: ./scripts/bootstrap.sh /path/to/python.com [output]" >&2
  echo "Download the latest python.com from https://github.com/bear0330/python-ape/releases" >&2
  exit 1
fi
test -f "$PYTHON_APE" || { echo "missing Python APE: $PYTHON_APE" >&2; exit 1; }

mkdir -p "$(dirname -- "$OUT")"
cd "$ROOT"
PYTHONPATH="$ROOT/src" "$HOST" -m cosmofy \
  --python "$PYTHON_APE" \
  --output "$OUT" \
  --args '-m cosmofy --cosmo --clone' \
  src/cosmofy
printf 'Output: %s\n' "$OUT"
