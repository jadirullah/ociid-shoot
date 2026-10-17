#!/usr/bin/python3
"""Uji toolbar (ikon+label), hintbar, penempatan, dan Enter = full screen."""
import os
import sys
import types

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _load import load  # noqa: E402

mod = load("ociid_shot", "ociid_shot.py")

import gi  # noqa: E402
gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, Gtk  # noqa: E402

Gtk.init([])
mod.runtime_env()
path = mod.capture_fullscreen()

provider = Gtk.CssProvider()
provider.load_from_data(mod.CSS)
Gtk.StyleContext.add_provider_for_screen(
    Gdk.Screen.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

win = mod.Shot(path)
win.show_all()
win.toolbar.hide()
win.hintbar.show()
while Gtk.events_pending():
    Gtk.main_iteration()

print("1) semua ikon tema tersedia")
theme = Gtk.IconTheme.get_default()
missing = [n for _, n, _, _ in mod.TOOLS if not theme.has_icon(n)]
missing += [n for n, _, _, _, _ in mod.ACTIONS if not theme.has_icon(n)]
assert not missing, missing

print("2) setiap tombol = ikon + label")
for tool, icon, label, _tip in mod.TOOLS:
    child = win.tool_buttons[tool].get_child()
    kids = child.get_children()
    assert isinstance(kids[0], Gtk.Image) and isinstance(kids[1], Gtk.Label)
    assert kids[1].get_text() == label, (tool, kids[1].get_text())

print("3) label aksi membedakan gambar vs file")
labels = [label for _i, label, _t, _m, _c in mod.ACTIONS]
assert "Gambar" in labels and "File" in labels, labels

print("4) hintbar memuat shortcut")
markup = win.hintbar.get_text()
for token in ("Ctrl+Shift+C", "Ctrl+S", "Ctrl+Z", "Esc", "tersimpan"):
    assert token in markup, token

print("5) toolbar punya ukuran nyata setelah seleksi")
win.on_press(win.area, types.SimpleNamespace(x=300, y=200, button=1, state=0))
win.on_motion(win.area, types.SimpleNamespace(x=900, y=700, button=1, state=0))
win.on_release(win.area, types.SimpleNamespace(x=900, y=700, button=1, state=0))
while Gtk.events_pending():
    Gtk.main_iteration()
alloc = win.toolbar.get_allocation()
print("   toolbar:", alloc.width, "x", alloc.height)
assert alloc.width > 300 and alloc.height > 40

print("6) Enter tanpa seleksi = seluruh layar")
win2 = mod.Shot(path)
win2.show_all()
win2.toolbar.hide()
while Gtk.events_pending():
    Gtk.main_iteration()
assert win2.on_key(win2.area,
                   types.SimpleNamespace(keyval=Gdk.KEY_Return, state=0)) is True
import cairo  # noqa: E402
surf = cairo.ImageSurface.create_from_png(win2.result)
assert (surf.get_width(), surf.get_height()) == (win2.width_px, win2.height_px)

print("\nOK: ikon+label+hintbar, toolbar tampil, Enter = full screen")
