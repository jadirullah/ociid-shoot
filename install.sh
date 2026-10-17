#!/bin/bash
# Pasang ociid-shot untuk user ini (tanpa sudo).
set -eu
REPO="$(cd "$(dirname "$0")" && pwd)"
BIN="$HOME/.local/bin"
APPS="$HOME/.local/share/applications"

mkdir -p "$BIN"
ln -sf "$REPO/ociid_shot.py" "$BIN/ociid-shot"
chmod +x "$REPO/ociid_shot.py"
echo "✓ launcher: $BIN/ociid-shot -> $REPO/ociid_shot.py"

if [ -f "$REPO/ociid-shot.desktop" ]; then
  mkdir -p "$APPS"
  sed "s|^Exec=.*|Exec=$BIN/ociid-shot|" "$REPO/ociid-shot.desktop" > "$APPS/ociid-shot.desktop"
  command -v update-desktop-database >/dev/null && update-desktop-database "$APPS" 2>/dev/null || true
  echo "✓ desktop entry: $APPS/ociid-shot.desktop"
fi

echo
echo "Uji cepat:  ociid-shot --full --file"
echo "Hotkey COSMIC: tambahkan manual di Settings → Keyboard, atau pakai"
echo "~/.config/cosmic/com.system76.CosmicSettings.Shortcuts/v1/custom"
echo "  (modifiers: [Ctrl, Shift], key: \"p\", description: Some(\"Screenshot\")): Spawn(\"$BIN/ociid-shot\")"
