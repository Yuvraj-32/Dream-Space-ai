#!/bin/bash
# DreamSpace door/window training on a Mac. See PLAN.md.
#   bash run_mac.sh trial    short test: is this Mac's GPU trustworthy, and how long will it take?
#   bash run_mac.sh train    the full run (run it again after any stop: it resumes)
#   bash run_mac.sh status   how far training has got
set -euo pipefail
cd "$(dirname "$0")"

fail() { echo "STOP: $*" >&2; exit 1; }

[ "$(uname -s)" = "Darwin" ] || fail "this script is for macOS."
[ "$(uname -m)" = "arm64" ] || fail "this Mac has an Intel chip, with no Apple GPU. Use the Colab notebook instead (PLAN.md)."
macos_major="$(sw_vers -productVersion | cut -d. -f1)"
[ "$macos_major" -ge 14 ] || fail "macOS 14 or newer is needed (this Mac has $(sw_vers -productVersion))."

if [ ! -x .venv/bin/python ]; then
    PY=""
    for candidate in python3.12 python3.11; do
        if command -v "$candidate" >/dev/null 2>&1; then PY="$candidate"; break; fi
    done
    [ -n "$PY" ] || fail "Python 3.11 or 3.12 is needed. Install 3.12 from python.org, then run this again."
    echo "Setting up (first time only, about 1 GB)..."
    "$PY" -m venv .venv
    .venv/bin/python -m pip install --upgrade --quiet pip
    .venv/bin/python -m pip install --quiet -r requirements-mac.txt
fi

export PYTORCH_ENABLE_MPS_FALLBACK=1
# caffeinate keeps the Mac awake for as long as this command runs.
caffeinate -ims .venv/bin/python pipeline.py "$@"
