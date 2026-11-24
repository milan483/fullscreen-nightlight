#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")/.."
export PYTHONDONTWRITEBYTECODE=1
python=${PYTHON:-python3}
node --check kwin-script/contents/code/main.js
node tests/test_windows.js
"$python" -m unittest discover -s tests -v
"$python" -m json.tool kwin-script/metadata.json >/dev/null
# A private bus is created by dbus-run-session. Check that it has no real KWin.
timeout 45s dbus-run-session -- bash -eu -c '
    test "$(gdbus call --session --dest org.freedesktop.DBus --object-path /org/freedesktop/DBus --method org.freedesktop.DBus.NameHasOwner org.kde.KWin)" = "(false,)"
    FULLSCREEN_TEST_BUS=1 "$1" tests/dbus_smoke.py
' verify "$python"
"$python" tests/check_install_payload.py
