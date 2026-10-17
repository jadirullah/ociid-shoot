#!/usr/bin/python3
"""ociid-shot — screenshot + annotate untuk Wayland/COSMIC (Pop!_OS).

Capture lewat `cosmic-screenshot` (portal resmi COSMIC), bukan wlr-screencopy,
sehingga tidak terkena bug kompatibilitas seperti Flameshot di COSMIC.

Mode:
  ociid-shot                 overlay pilih area + anotasi
  ociid-shot --full          seluruh layar, langsung simpan + copy image
  ociid-shot --full --file   seluruh layar, langsung simpan + copy FILE
  ociid-shot --region WxH+X+Y  potong area tetap tanpa GUI
  ociid-shot --selftest      uji render anotasi tanpa GUI (CI-friendly)

Clipboard:
  Copy image -> image/png (paste jadi gambar)
  Copy file  -> text/uri-list (paste jadi file)
"""

import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

import gi

# python3-gi-cairo tidak selalu terpasang di Pop!_OS/COSMIC dan kita tidak pakai
# sudo: kalau modul jembatan cairo belum ada, pakai salinan lokal
# (~/.local/lib/python3.X/site-packages/gi/_gi_cairo*.so hasil `dpkg -x`).
def _ensure_gi_cairo():
    try:
        gi.require_foreign("cairo")
        return
    except Exception:
        pass
    local = os.path.join(os.path.expanduser("~"), ".local", "lib",
                         f"python{sys.version_info.major}.{sys.version_info.minor}",
                         "site-packages", "gi")
    if os.path.isdir(local) and local not in gi.__path__:
        gi.__path__.append(local)
        import importlib
        importlib.invalidate_caches()
        gi.require_foreign("cairo")
        log(f"gi-cairo dimuat dari {local}")


gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gdk, GdkPixbuf, GLib, Gtk  # noqa: E402

import cairo  # noqa: E402

APP_NAME = "ociid-shot"
SAVE_DIR = os.path.join(GLib.get_home_dir(), "Pictures", "Screenshots")
# (id_tool, ikon tema, label, tooltip)
TOOLS = [
    ("arrow", "object-select-symbolic", "Panah", "Panah penunjuk — klik lalu tarik"),
    ("rect", "checkbox-symbolic", "Kotak", "Kotak persegi — klik lalu tarik"),
    ("ellipse", "media-record-symbolic", "Elips", "Lingkaran/elips — klik lalu tarik"),
    ("pen", "document-edit-symbolic", "Pena", "Gambar bebas dengan pena"),
    ("text", "insert-text-symbolic", "Teks", "Tambah teks — klik di area gambar"),
    ("blur", "view-conceal-symbolic", "Sensor", "Sensor/mosaic untuk menutup data sensitif"),
]
# (ikon tema, label, tooltip, nama_method, kelas_css)
ACTIONS = [
    ("edit-undo-symbolic", "Undo", "Batalkan anotasi terakhir (Ctrl+Z)", "on_undo", ""),
    ("edit-copy-symbolic", "Gambar", "Copy gambar ke clipboard (Ctrl+C / Enter)", "on_copy_image", ""),
    ("folder-symbolic", "File", "Copy FILE ke clipboard (Ctrl+Shift+C)", "on_copy_file", ""),
    ("document-save-symbolic", "Simpan", "Simpan saja tanpa copy (Ctrl+S)", "on_save", ""),
    ("window-close-symbolic", "Batal", "Batal tanpa menyimpan (Esc)", "on_cancel", "danger"),
]
ACCENT = (0.94, 0.27, 0.27)  # red, Flameshot-ish default
DIM = 0.45


def log(msg):
    if os.environ.get("OCIID_SHOT_DEBUG"):
        print(f"[{APP_NAME}] {msg}", file=sys.stderr, flush=True)


_ensure_gi_cairo()


def runtime_env():
    """Pastikan env Wayland terisi walau dipanggil dari proses non-grafis."""
    runtime = os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}"
    os.environ.setdefault("XDG_RUNTIME_DIR", runtime)
    if not os.environ.get("WAYLAND_DISPLAY"):
        try:
            for name in sorted(os.listdir(runtime)):
                if re.fullmatch(r"wayland-\d+", name):
                    os.environ["WAYLAND_DISPLAY"] = name
                    break
        except OSError:
            pass


def capture_fullscreen():
    """Ambil screenshot penuh via portal COSMIC. Return path PNG."""
    runtime_env()
    fd, path = tempfile.mkstemp(prefix="ociid-shot-", suffix=".png")
    os.close(fd)
    os.unlink(path)
    savedir = os.path.dirname(path)
    base = os.path.basename(path)
    proc = subprocess.run(
        ["cosmic-screenshot", "--interactive=false", "--notify=false", "-s", savedir],
        capture_output=True, text=True, timeout=30,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"capture gagal: {proc.stderr.strip() or proc.returncode}")
    produced = proc.stdout.strip().splitlines()
    out = produced[-1].strip() if produced else ""
    if not out or not os.path.exists(out):
        raise RuntimeError(f"capture tidak menghasilkan file: {proc.stdout!r}")
    shutil.move(out, path)
    log(f"captured {path} ({os.path.getsize(path)} bytes)")
    return path


def ensure_save_dir():
    os.makedirs(SAVE_DIR, exist_ok=True)
    return SAVE_DIR


def save_png(surface, prefix="Screenshot"):
    directory = ensure_save_dir()
    stamp = time.strftime("%Y-%m-%d_%H-%M-%S")
    path = os.path.join(directory, f"{prefix}_{stamp}.png")
    idx = 1
    while os.path.exists(path):
        path = os.path.join(directory, f"{prefix}_{stamp}_{idx}.png")
        idx += 1
    surface.write_to_png(path)
    log(f"saved {path}")
    return path


def copy_image(path):
    runtime_env()
    with open(path, "rb") as fh:
        subprocess.run(["wl-copy", "--type", "image/png"], stdin=fh, check=True,
                       timeout=20, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL)


def copy_file(path):
    runtime_env()
    uri = GLib.filename_to_uri(os.path.abspath(path), None)
    subprocess.run(["wl-copy", "--type", "text/uri-list"], input=uri + "\r\n",
                   text=True, check=True, timeout=20,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def notify(text):
    try:
        subprocess.Popen(["notify-send", "-a", APP_NAME, "-t", "2500", text],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except FileNotFoundError:
        pass


# ─────────────────────────── annotation model ───────────────────────────


class Annot:
    __slots__ = ("kind", "points", "color", "width", "text")

    def __init__(self, kind, points, color=ACCENT, width=3, text=""):
        self.kind = kind
        self.points = list(points)
        self.color = color
        self.width = width
        self.text = text


def _draw_annot(ctx, a):
    ctx.save()
    ctx.set_source_rgb(*a.color)
    ctx.set_line_width(a.width)
    ctx.set_line_cap(cairo.LINE_CAP_ROUND)
    ctx.set_line_join(cairo.LINE_JOIN_ROUND)
    if a.kind in ("pen", "arrow"):
        if len(a.points) >= 2:
            ctx.move_to(*a.points[0])
            for pt in a.points[1:]:
                ctx.line_to(*pt)
            ctx.stroke()
            if a.kind == "arrow":
                (x1, y1), (x2, y2) = a.points[-2], a.points[-1]
                angle = math.atan2(y2 - y1, x2 - x1)
                size = max(12, a.width * 4)
                for delta in (math.pi / 7, -math.pi / 7):
                    ctx.move_to(x2, y2)
                    ctx.line_to(x2 - size * math.cos(angle + delta),
                                 y2 - size * math.sin(angle + delta))
                ctx.stroke()
    elif a.kind in ("rect", "ellipse"):
        if len(a.points) >= 2:
            (x1, y1), (x2, y2) = a.points[0], a.points[-1]
            left, top = min(x1, x2), min(y1, y2)
            w, h = abs(x2 - x1), abs(y2 - y1)
            if a.kind == "rect":
                ctx.rectangle(left, top, w, h)
            else:
                ctx.save()
                ctx.translate(left + w / 2, top + h / 2)
                ctx.scale(max(w / 2, 0.01), max(h / 2, 0.01))
                ctx.arc(0, 0, 1, 0, 2 * math.pi)
                ctx.restore()
            ctx.stroke()
    elif a.kind == "text" and a.points:
        ctx.select_font_face("DejaVu Sans", cairo.FONT_SLANT_NORMAL,
                             cairo.FONT_WEIGHT_BOLD)
        ctx.set_font_size(a.width * 6)
        ctx.move_to(*a.points[0])
        ctx.show_text(a.text or "")
        ctx.stroke()
    ctx.restore()


def render_region(base_surface, mosaic_surface, annots, box):
    """Render potongan `box` (x, y, w, h) + anotasi ke surface baru."""
    x, y, w, h = [int(round(v)) for v in box]
    w, h = max(w, 1), max(h, 1)
    out = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
    ctx = cairo.Context(out)
    ctx.set_source_surface(base_surface, -x, -y)
    ctx.paint()
    for a in annots:
        if a.kind == "blur":
            (x1, y1), (x2, y2) = a.points[0], a.points[-1]
            bx, by = min(x1, x2), min(y1, y2)
            bw, bh = abs(x2 - x1), abs(y2 - y1)
            ctx.save()
            ctx.rectangle(bx, by, bw, bh)
            ctx.clip()
            ctx.set_source_surface(mosaic_surface, -x, -y)
            ctx.paint()
            ctx.restore()
        else:
            # Anotasi disimpan dalam koordinat layar; geser ke koordinat hasil.
            shifted = Annot(a.kind, [(px - x, py - y) for px, py in a.points],
                            a.color, a.width, a.text)
            _draw_annot(ctx, shifted)
    out.flush()
    return out


def crop_surface(base_surface, box):
    x, y, w, h = [int(round(v)) for v in box]
    out = cairo.ImageSurface(cairo.FORMAT_ARGB32, max(w, 1), max(h, 1))
    ctx = cairo.Context(out)
    ctx.set_source_surface(base_surface, -x, -y)
    ctx.paint()
    out.flush()
    return out


# ──────────────────────────────── overlay ────────────────────────────────


CSS = b"""
window.ociid { background-color: #000000; }
.toolbar { background-color: rgba(28,28,32,0.97); border-radius: 10px;
           padding: 5px 7px; }
.toolbar button { background-image: none; background-color: transparent;
                  color: #f2f2f4; border: none; box-shadow: none;
                  min-width: 44px; min-height: 44px; padding: 3px 7px; }
.toolbar button:hover { background-color: rgba(255,255,255,0.16);
                        border-radius: 7px; }
.toolbar button:checked { background-color: rgba(240,70,70,0.90);
                          border-radius: 7px; color: #ffffff; }
.toolbar button.danger:hover { background-color: rgba(240,70,70,0.90); }
.toolbar .tool-label { color: #b9b9c2; font-size: 11px; }
.toolbar button:checked .tool-label { color: #ffffff; }
.toolbar button:hover .tool-label { color: #ffffff; }
.hintbar { background-color: rgba(20,20,24,0.82); border-radius: 8px;
           color: #d6d6de; font-size: 12px; padding: 7px 14px; }
.hintbar b { color: #ffffff; }
.hintbar .accent { color: #ff6b6b; }
"""


class Shot(Gtk.Window):
    def __init__(self, path):
        super().__init__(type=Gtk.WindowType.TOPLEVEL)
        self.set_title(APP_NAME)
        self.get_style_context().add_class("ociid")
        self.set_decorated(False)
        self.set_keep_above(True)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        self.set_app_paintable(True)
        self.fullscreen()

        self.pixbuf = GdkPixbuf.Pixbuf.new_from_file(path)
        self.width_px = self.pixbuf.get_width()
        self.height_px = self.pixbuf.get_height()

        self.base_surface = self._pixbuf_to_surface(self.pixbuf)
        self.mosaic_surface = self._pixelated(self.base_surface)

        self.annots = []
        self.tool = "select"
        self.sel = None            # (x1, y1, x2, y2) in image coords
        self.drag_start = None
        self.preview = []          # annot in progress
        self.text_entry = None
        self.result = None
        self.result_mode = None

        self.area = Gtk.DrawingArea()
        self.area.set_can_focus(True)
        self.area.add_events(Gdk.EventMask.BUTTON_PRESS_MASK
                             | Gdk.EventMask.BUTTON_RELEASE_MASK
                             | Gdk.EventMask.POINTER_MOTION_MASK
                             | Gdk.EventMask.KEY_PRESS_MASK)
        self.area.connect("draw", self.on_draw)
        self.area.connect("button-press-event", self.on_press)
        self.area.connect("button-release-event", self.on_release)
        self.area.connect("motion-notify-event", self.on_motion)
        self.area.connect("key-press-event", self.on_key)

        self.overlay = Gtk.Overlay()
        self.overlay.add(self.area)
        self.toolbar = self._build_toolbar()
        self.toolbar.set_halign(Gtk.Align.START)
        self.toolbar.set_valign(Gtk.Align.START)
        self.overlay.add_overlay(self.toolbar)
        self.hintbar = self._build_hintbar()
        self.hintbar.set_halign(Gtk.Align.CENTER)
        self.hintbar.set_valign(Gtk.Align.END)
        self.hintbar.set_margin_bottom(24)
        self.overlay.add_overlay(self.hintbar)
        self.add(self.overlay)

        self.connect("key-press-event", self.on_key)
        self.connect("destroy", Gtk.main_quit)
        self.show_all()
        self.toolbar.hide()
        self.area.grab_focus()
        self._place_toolbar(None)
        if os.environ.get("OCIID_SHOT_DEMO"):
            # Mode QA: tampilkan seleksi contoh + toolbar supaya bisa difoto.
            w, h = self.width_px, self.height_px
            self.sel = (int(w * 0.15), int(h * 0.15), int(w * 0.75), int(h * 0.7))
            box = self.sel_box()
            self.annots = [Annot("rect", [(box[0] + 30, box[1] + 30),
                                          (box[0] + 260, box[1] + 160)], ACCENT, 4)]
            self.toolbar.show_all()
            self._place_toolbar(box)
            self.queue_draw()

    # -- helpers ---------------------------------------------------------
    @staticmethod
    def _pixbuf_to_surface(pixbuf):
        w, h = pixbuf.get_width(), pixbuf.get_height()
        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
        ctx = cairo.Context(surface)
        Gdk.cairo_set_source_pixbuf(ctx, pixbuf, 0, 0)
        ctx.paint()
        return surface

    @staticmethod
    def _pixelated(surface, factor=14):
        """Mosaic/redaction murni cairo (tanpa PIL): downscale lalu upscale NEAREST."""
        w, h = surface.get_width(), surface.get_height()
        sw, sh = max(w // factor, 1), max(h // factor, 1)
        small = cairo.ImageSurface(cairo.FORMAT_ARGB32, sw, sh)
        sctx = cairo.Context(small)
        sctx.scale(sw / w, sh / h)
        sctx.set_source_surface(surface, 0, 0)
        sctx.get_source().set_filter(cairo.FILTER_GOOD)
        sctx.paint()
        small.flush()

        big = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
        bctx = cairo.Context(big)
        bctx.scale(w / sw, h / sh)
        bctx.set_source_surface(small, 0, 0)
        bctx.get_source().set_filter(cairo.FILTER_NEAREST)
        bctx.paint()
        big.flush()
        return big

    def sel_box(self, sel=None):
        sel = sel if sel is not None else self.sel
        if not sel:
            return None
        x1, y1, x2, y2 = sel
        left, top = min(x1, x2), min(y1, y2)
        return (left, top, max(abs(x2 - x1), 1), max(abs(y2 - y1), 1))

    def _build_toolbar(self):
        bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=2)
        bar.get_style_context().add_class("toolbar")
        self.tool_buttons = {}
        for tool, icon, label, tip in TOOLS:
            btn = Gtk.ToggleButton()
            btn.add(self._button_body(icon, label))
            btn.set_tooltip_text(tip)
            btn.set_relief(Gtk.ReliefStyle.NONE)
            btn.connect("toggled", self.on_tool_toggled, tool)
            bar.pack_start(btn, False, False, 0)
            self.tool_buttons[tool] = btn
            if tool == "blur":
                bar.pack_start(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL),
                               False, False, 4)
        for icon, label, tip, cb, cls in ACTIONS:
            btn = Gtk.Button()
            btn.add(self._button_body(icon, label))
            btn.set_tooltip_text(tip)
            btn.set_relief(Gtk.ReliefStyle.NONE)
            if cls:
                btn.get_style_context().add_class(cls)
            btn.connect("clicked", getattr(self, cb))
            bar.pack_start(btn, False, False, 0)
        return bar

    @staticmethod
    def _button_body(icon_name, label):
        """Ikon tema + label kecil, supaya tombol tidak ambigu."""
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
        if Gtk.IconTheme.get_default().has_icon(icon_name):
            image = Gtk.Image.new_from_icon_name(icon_name, Gtk.IconSize.BUTTON)
        else:
            image = Gtk.Image.new_from_icon_name("image-missing",
                                                 Gtk.IconSize.BUTTON)
        box.pack_start(image, False, False, 0)
        text = Gtk.Label(label=label)
        text.get_style_context().add_class("tool-label")
        box.pack_start(text, False, False, 0)
        return box

    def _place_toolbar(self, box):
        if box is None:
            self.toolbar.set_margin_top(12)
            self.toolbar.set_margin_start(12)
            return
        x, y, w, h = box
        screen_w, screen_h = self.width_px, self.height_px
        try:
            bar_h = self.toolbar.get_preferred_height()[1] or 74
        except Exception:
            bar_h = 74
        top = y + h + 10
        if top + bar_h > screen_h - 8:
            top = max(8, y - bar_h - 10)
        left = min(max(8, x), max(8, screen_w - 480))
        self.toolbar.set_margin_top(int(top))
        self.toolbar.set_margin_start(int(left))

    def _build_hintbar(self):
        bar = Gtk.Label()
        bar.set_markup(
            "<b>Enter</b> / <b>Ctrl+C</b> copy gambar   ·   "
            "<b>Ctrl+Shift+C</b> copy <span foreground='#ff6b6b'>file</span>   ·   "
            "<b>Ctrl+S</b> simpan   ·   <b>Ctrl+Z</b> undo   ·   <b>Esc</b> batal"
            "   —   file selalu tersimpan otomatis"
        )
        bar.get_style_context().add_class("hintbar")
        return bar

    # -- drawing ---------------------------------------------------------
    def on_draw(self, widget, cr):
        # Jendela overlay opaque: gambar dulu screenshot penuh, baru diredupkan.
        cr.set_source_surface(self.base_surface, 0, 0)
        cr.paint()
        cr.set_source_rgba(0, 0, 0, DIM)
        cr.paint()
        cr.save()
        cr.rectangle(0, 0, self.width_px, self.height_px)
        cr.clip()
        if self.sel:
            box = self.sel_box()
            cr.set_source_surface(self.base_surface, 0, 0)
            cr.rectangle(*box)
            cr.fill()
            for a in self.annots + self.preview:
                if a.kind == "blur":
                    (x1, y1), (x2, y2) = a.points[0], a.points[-1]
                    cr.save()
                    cr.rectangle(min(x1, x2), min(y1, y2), abs(x2 - x1),
                                 abs(y2 - y1))
                    cr.clip()
                    cr.set_source_surface(self.mosaic_surface, 0, 0)
                    cr.paint()
                    cr.restore()
                else:
                    _draw_annot(cr, a)
            x, y, w, h = box
            cr.set_source_rgba(*ACCENT)
            cr.set_line_width(1.5)
            cr.rectangle(x + 0.5, y + 0.5, w - 1, h - 1)
            cr.stroke()
            cr.set_font_size(13)
            label = f"{int(w)} \u00d7 {int(h)}"
            cr.move_to(x + 4, max(14, y - 8))
            cr.set_source_rgba(1, 1, 1, 0.92)
            cr.show_text(label)
        elif self.drag_start and self.drag_current:
            (x1, y1), (x2, y2) = self.drag_start, self.drag_current
            cr.set_source_rgba(*ACCENT, 0.95)
            cr.set_line_width(1.5)
            cr.rectangle(min(x1, x2) + 0.5, min(y1, y2) + 0.5, abs(x2 - x1),
                         abs(y2 - y1))
            cr.stroke()
        cr.restore()
        if not self.sel and not self.drag_start:
            cr.set_source_rgba(1, 1, 1, 0.78)
            cr.set_font_size(16)
            cr.move_to(24, 40)
            cr.show_text("Tarik untuk memilih area  \u2022  Esc batal")
        return False

    # -- events ----------------------------------------------------------
    def on_press(self, widget, event):
        if event.button != 1:
            return False
        pt = (event.x, event.y)
        if self.tool == "select" or not self.sel:
            self.drag_start = pt
            self.drag_current = pt
            self.preview = []
            self.queue_draw()
            return True
        if self.tool == "text":
            self._ask_text(pt)
            return True
        self.preview = [Annot(self.tool, [pt, pt])]
        self.queue_draw()
        return True

    def on_motion(self, widget, event):
        pt = (event.x, event.y)
        if self.drag_start:
            self.drag_current = pt
            self.queue_draw()
            return True
        if self.preview:
            a = self.preview[0]
            if a.kind in ("pen", "arrow"):
                a.points[-1] = pt
                if a.kind == "pen":
                    a.points.append(pt)
            else:
                a.points[-1] = pt
            self.queue_draw()
            return True
        return False

    def on_release(self, widget, event):
        pt = (event.x, event.y)
        if self.drag_start:
            start = self.drag_start
            self.drag_start = None
            self.drag_current = None
            box = self.sel_box((start[0], start[1], pt[0], pt[1]))
            if box and box[2] > 6 and box[3] > 6:
                self.sel = (start[0], start[1], pt[0], pt[1])
                self.toolbar.show_all()
                self._place_toolbar(box)
            self.queue_draw()
            return True
        if self.preview:
            a = self.preview[0]
            a.points[-1] = pt
            self.annots.append(a)
            self.preview = []
            self.queue_draw()
            return True
        return False

    def _ask_text(self, pt):
        dialog = Gtk.Dialog(title="Teks", transient_for=self, modal=True)
        dialog.add_button("Batal", Gtk.ResponseType.CANCEL)
        dialog.add_button("Tambah", Gtk.ResponseType.OK)
        entry = Gtk.Entry()
        entry.set_placeholder_text("Tulis keterangan…")
        entry.set_width_chars(28)
        dialog.get_content_area().add(entry)
        dialog.show_all()
        entry.grab_focus()

        def on_response(dlg, resp):
            if resp == Gtk.ResponseType.OK and entry.get_text().strip():
                self.annots.append(Annot("text", [pt], ACCENT, 3,
                                         entry.get_text().strip()))
                self.queue_draw()
            dlg.destroy()
            self.area.grab_focus()

        dialog.connect("response", on_response)
        dialog.run()

    def on_tool_toggled(self, btn, tool):
        if btn.get_active():
            self.tool = tool
            for name, other in self.tool_buttons.items():
                if name != tool and other.get_active():
                    other.handler_block_by_func(self.on_tool_toggled)
                    other.set_active(False)
                    other.handler_unblock_by_func(self.on_tool_toggled)
        elif self.tool == tool:
            self.tool = "select"

    def on_key(self, widget, event):
        key = Gdk.keyval_name(event.keyval) or ""
        ctrl = bool(event.state & Gdk.ModifierType.CONTROL_MASK)
        shift = bool(event.state & Gdk.ModifierType.SHIFT_MASK)
        if key == "Escape":
            self.on_cancel(None)
            return True
        if key in ("Return", "KP_Enter"):
            if not self.sel:
                # Tanpa seleksi: Enter = ambil seluruh layar.
                self.sel = (0, 0, self.width_px, self.height_px)
                self._place_toolbar((0, 0, self.width_px, self.height_px))
            self.on_copy_image(None)
            return True
        if ctrl and key.lower() == "z":
            self.on_undo(None)
            return True
        if ctrl and shift and key.lower() == "c":
            self.on_copy_file(None)
            return True
        if ctrl and key.lower() == "c":
            self.on_copy_image(None)
            return True
        if ctrl and key.lower() == "s":
            self.on_save(None)
            return True
        return False

    # -- actions ---------------------------------------------------------
    def _finish(self, mode):
        if not self.sel:
            notify("Pilih area dulu")
            return
        box = self.sel_box()
        surface = render_region(self.base_surface, self.mosaic_surface, self.annots,
                                box)
        path = save_png(surface)
        self.result = path
        self.result_mode = mode
        try:
            if mode in ("image", "both"):
                copy_image(path)
            if mode in ("file", "both"):
                copy_file(path)
            notify({"image": "Gambar disalin + tersimpan",
                    "file": "File disalin + tersimpan",
                    "save": "Tersimpan",
                    "both": "Gambar & file disalin"}[mode])
        except Exception as exc:
            log(f"clipboard error: {exc}")
            notify(f"Tersimpan, clipboard gagal: {exc}")
        self.destroy()

    def on_copy_image(self, _btn):
        self._finish("image")

    def on_copy_file(self, _btn):
        self._finish("file")

    def on_save(self, _btn):
        self._finish("save")

    def on_cancel(self, _btn):
        self.result = None
        self.destroy()

    def on_undo(self, _btn):
        if self.annots:
            self.annots.pop()
            self.queue_draw()


# ─────────────────────────────── CLI paths ───────────────────────────────


def run_full(copy_mode):
    path = capture_fullscreen()
    try:
        surface = cairo.ImageSurface.create_from_png(path)
        out = save_png(surface)
        if copy_mode == "file":
            copy_file(out)
            notify("File disalin + tersimpan")
        elif copy_mode == "none":
            notify("Tersimpan")
        else:
            copy_image(out)
            notify("Gambar disalin + tersimpan")
        print(out)
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


def run_region(spec, copy_mode):
    m = re.fullmatch(r"(\d+)x(\d+)(?:\+(-?\d+)\+(-?\d+))?", spec)
    if not m:
        raise SystemExit("format region: WxH+X+Y (contoh 800x600+100+50)")
    w, h = int(m.group(1)), int(m.group(2))
    x = int(m.group(3) or 0)
    y = int(m.group(4) or 0)
    path = capture_fullscreen()
    try:
        full = cairo.ImageSurface.create_from_png(path)
        surface = crop_surface(full, (x, y, w, h))
        out = save_png(surface)
        if copy_mode == "file":
            copy_file(out)
        elif copy_mode != "none":
            copy_image(out)
        notify("Tersimpan")
        print(out)
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


def run_gui():
    path = capture_fullscreen()
    provider = Gtk.CssProvider()
    provider.load_from_data(CSS)
    Gtk.StyleContext.add_provider_for_screen(
        Gdk.Screen.get_default(), provider,
        Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
    win = Shot(path)
    log("overlay ready")
    Gtk.main()
    try:
        os.unlink(path)
    except OSError:
        pass
    if win.result:
        print(win.result)


def run_selftest(target=None):
    """Tanpa GUI: render anotasi ke PNG dan laporkan hasilnya."""
    path = target or capture_fullscreen()
    surface = cairo.ImageSurface.create_from_png(path)
    blur = Shot._pixelated(surface)
    annots = [
        Annot("rect", [(40, 40), (240, 160)], (0.1, 0.7, 0.3), 4),
        Annot("arrow", [(50, 220), (300, 120)], ACCENT, 4),
        Annot("ellipse", [(330, 40), (480, 150)], (0.2, 0.5, 1.0), 4),
        Annot("text", [(40, 300)], (1, 1, 1), 3, "ociid-shot"),
        Annot("blur", [(500, 40), (700, 200)], ACCENT, 3),
    ]
    out = render_region(surface, blur, annots, (20, 20, 700, 320))
    tmp = tempfile.mktemp(suffix="-selftest.png")
    out.write_to_png(tmp)
    print(f"selftest png: {tmp} ({os.path.getsize(tmp)} bytes, "
          f"{out.get_width()}x{out.get_height()})")
    return tmp


def main(argv):
    copy_mode = "image"
    if "--file" in argv:
        copy_mode = "file"
    if "--no-copy" in argv:
        copy_mode = "none"
    if "--selftest" in argv:
        run_selftest()
        return 0
    if "--full" in argv:
        run_full(copy_mode)
        return 0
    for i, arg in enumerate(argv):
        if arg == "--region" and i + 1 < len(argv):
            run_region(argv[i + 1], copy_mode)
            return 0
    Gtk.init(argv)
    run_gui()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
