#!/usr/bin/python3
"""Uji logika interaksi tanpa klik manual: drag -> anotasi -> undo -> shortcut.

Jalankan di sesi Wayland/COSMIC yang hidup:
    /usr/bin/python3 tests/test_interaction.py
"""
import os
import subprocess
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
while Gtk.events_pending():
    Gtk.main_iteration()


def ev(x, y, button=1, state=0):
    return types.SimpleNamespace(x=x, y=y, button=button, state=state)


print("1) drag seleksi 200,200 -> 800,600")
assert win.on_press(win.area, ev(200, 200)) is True
assert win.on_motion(win.area, ev(500, 400)) is True
assert win.on_release(win.area, ev(800, 600)) is True
box = win.sel_box()
print("   selection:", box)
assert box == (200, 200, 600, 400), box
assert win.toolbar.get_visible(), "toolbar tidak muncul setelah seleksi"

print("2) tool rect")
win.tool_buttons["rect"].set_active(True)
assert win.tool == "rect"
assert win.on_press(win.area, ev(250, 250)) is True
assert win.on_motion(win.area, ev(450, 450)) is True
assert win.on_release(win.area, ev(450, 450)) is True
assert len(win.annots) == 1, win.annots

print("3) tool arrow")
win.tool_buttons["arrow"].set_active(True)
assert win.on_press(win.area, ev(300, 520)) is True
assert win.on_motion(win.area, ev(700, 300)) is True
assert win.on_release(win.area, ev(700, 300)) is True

print("4) tool blur (mosaic)")
win.tool_buttons["blur"].set_active(True)
assert win.on_press(win.area, ev(600, 250)) is True
assert win.on_motion(win.area, ev(780, 400)) is True
assert win.on_release(win.area, ev(780, 400)) is True
assert [a.kind for a in win.annots] == ["rect", "arrow", "blur"], win.annots

print("5) undo")
win.on_undo(None)
assert [a.kind for a in win.annots] == ["rect", "arrow"]

print("6) Ctrl+Shift+C -> copy FILE")
key = types.SimpleNamespace(keyval=Gdk.KEY_c,
                            state=Gdk.ModifierType.CONTROL_MASK
                            | Gdk.ModifierType.SHIFT_MASK)
assert win.on_key(win.area, key) is True
assert win.result and os.path.exists(win.result)
types_out = subprocess.run(["wl-paste", "--list-types"], capture_output=True,
                           text=True).stdout
assert "text/uri-list" in types_out, types_out

import cairo  # noqa: E402
surf = cairo.ImageSurface.create_from_png(win.result)
print("   hasil:", os.path.basename(win.result), surf.get_width(), "x",
      surf.get_height())
assert (surf.get_width(), surf.get_height()) == (600, 400)

print("\nOK: seleksi, 3 anotasi, undo, shortcut copy-file, crop 600x400")
