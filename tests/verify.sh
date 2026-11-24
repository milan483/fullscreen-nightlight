#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")/.."
export PYTHONDONTWRITEBYTECODE=1
python=${PYTHON:-python3}
node --check kwin-script/contents/code/main.js
node tests/test_windows.js
"$python" -m unittest discover -s tests -v
"$python" -m json.tool kwin-script/metadata.json >/dev/null
# The harness creates its own private daemon with no service activation directories.
timeout 120s "$python" tests/dbus_smoke.py
"$python" tests/check_install_payload.py
