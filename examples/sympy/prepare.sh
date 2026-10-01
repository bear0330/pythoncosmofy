#!/bin/sh
# Download SymPy and extract it into Lib/site-packages for pythoncosmofy.
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PY=${1:-}
STAGE=$(mktemp -d)
trap 'rm -rf "$STAGE"' EXIT

if [ -z "$PY" ] || [ ! -f "$PY" ]; then
  echo "usage: ./prepare.sh /path/to/python.com" >&2
  exit 1
fi

python3 -m pip download --disable-pip-version-check -d "$STAGE" 'sympy==1.14.0'

rm -rf "$ROOT/Lib"
mkdir -p "$ROOT/Lib/site-packages"
for wheel in "$STAGE"/*.whl; do
  python3 -m zipfile -e "$wheel" "$ROOT/Lib/site-packages"
done
find "$ROOT/Lib/site-packages" -mindepth 1 -maxdepth 1 \( -name '*.dist-info' -o -name '*.data' \) -exec rm -rf {} +

ROOT="$ROOT" python3 - <<'PY'
from pathlib import Path
import os
import sys

path = Path(os.environ["ROOT"]) / "Lib/site-packages/sympy/external/gmpy.py"
text = path.read_text(encoding="utf-8")
old_import = "from ctypes import c_long, sizeof\n"
new_import = (
    "try:\n"
    "    from ctypes import c_long, sizeof\n"
    "except ImportError:\n"
    "    c_long = sizeof = None\n"
)
old_max = "LONG_MAX = (1 << (8*sizeof(c_long) - 1)) - 1\n"
new_max = (
    "if sizeof is not None:\n"
    "    LONG_MAX = (1 << (8*sizeof(c_long) - 1)) - 1\n"
    "else:\n"
    "    LONG_MAX = (1 << 63) - 1\n"
)
if old_import not in text or old_max not in text:
    sys.exit("sympy/external/gmpy.py does not match the ctypes patch")
path.write_text(text.replace(old_import, new_import, 1).replace(old_max, new_max, 1), encoding="utf-8")
PY

cd "$ROOT"
"$PY" -m compileall --invalidation-mode=unchecked-hash -b -q Lib
find Lib -type f -name '*.py' -delete
find Lib -type d -name '__pycache__' -exec rm -rf {} +
echo "Prepared $ROOT/Lib/site-packages"
