#!/bin/bash
# BIG Hat Standalone — macOS app launcher
#
# Lives at: BIG Hat Standalone.app/Contents/MacOS/BIGHatStandalone
# Resources sit at:  BIG Hat Standalone.app/Contents/Resources/
#   - python/bin/python3      ← embedded CPython (relocatable)
#   - backend/launcher.py     ← the actual FastAPI bootstrap
#   - packaging/, VERSION.txt, etc.
#
# We forward all argv to backend/launcher.py and exec the embedded Python.
# The launcher itself opens http://127.0.0.1:8001/ in the default browser.

set -e

# Resolve the directory containing this script, then climb up to Contents/.
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CONTENTS="$(cd "$SCRIPT_DIR/.." && pwd)"
RES="$CONTENTS/Resources"

PY="$RES/python/bin/python3"
LAUNCHER="$RES/backend/launcher.py"

if [ ! -x "$PY" ]; then
    /usr/bin/osascript -e 'display alert "BIG Hat Standalone" message "Embedded Python runtime is missing. Reinstall the app." as critical' || true
    exit 1
fi
if [ ! -f "$LAUNCHER" ]; then
    /usr/bin/osascript -e 'display alert "BIG Hat Standalone" message "backend/launcher.py is missing. Reinstall the app." as critical' || true
    exit 1
fi

# User data lives outside the .app bundle (which is signed/read-only).
# We honour ~/Library/Application Support/BIG Hat Standalone/ as the default
# data root, so the .app stays pristine.
export BIGHAT_NATIVE_MODE=1
export BIGHAT_DATA_ROOT="${BIGHAT_DATA_ROOT:-$HOME/Library/Application Support/BIG Hat Standalone}"
mkdir -p "$BIGHAT_DATA_ROOT"

cd "$RES"
exec "$PY" "$LAUNCHER" "$@"
