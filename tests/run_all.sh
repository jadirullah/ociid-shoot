#!/bin/bash
# Jalankan semua tes. Butuh sesi Wayland/COSMIC hidup untuk tes GUI.
set -u
cd "$(dirname "$0")/.." || exit 1
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
if [ -z "${WAYLAND_DISPLAY:-}" ]; then
  for s in "$XDG_RUNTIME_DIR"/wayland-*; do
    case "$s" in *.lock) continue ;; esac
    export WAYLAND_DISPLAY="$(basename "$s")"
    break
  done
fi

fail=0
run() {
  echo "── $1"
  shift
  if "$@"; then echo "   PASS"; else echo "   FAIL"; fail=1; fi
  echo
}

run "selftest render (tanpa GUI)" /usr/bin/python3 ociid_shot.py --selftest
run "toolbar / ikon / hintbar" /usr/bin/python3 tests/test_toolbar.py
run "interaksi / anotasi / clipboard" /usr/bin/python3 tests/test_interaction.py
run "skrip macOS (mock)" /usr/bin/python3 tests/test_mac_script.py

exit "$fail"
