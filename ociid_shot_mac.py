#!/usr/bin/env python3
"""ociid-shot (macOS) — capture lewat `screencapture`, clipboard via `osascript`.

Dependensi: NOL (semua biner bawaan macOS). Tidak butuh pyobjc/PIL/GTK.

Mode:
  ociid_shot_mac.py                 overlay select bawaan macOS (drag area, Space = window)
  ociid_shot_mac.py --full          seluruh layar
  ociid_shot_mac.py --window        pilih window (dengan bayangan)
  ociid_shot_mac.py --region 100,80,800,600   area tetap (x,y,w,h)
  ociid_shot_mac.py --delay 3       tunda 3 detik (untuk menu yang suka menutup)

Clipboard:
  --clipboard image  (default)  → paste jadi gambar
  --clipboard file              → paste jadi FILE (ini yang Flameshot tidak bisa)
  --clipboard none              → simpan saja
  (tidak ada mode "both": macOS hanya punya satu pemilik clipboard, isi
   terakhir yang menang — jadi pilih salah satu, file tetap tersimpan)

Izin macOS yang dibutuhkan (sekali saja):
  System Settings → Privacy & Security → Screen Recording → aktifkan untuk
  Terminal/iTerm/Hermes yang menjalankan skrip ini.
  Kalau muncul dialog "wants to control System Events" saat pertama copy,
  izinkan juga di Privacy & Security → Automation.

CATATAN: skrip ini ditulis & di-syntax-check di Linux, BELUM dijalankan di
macOS. Uji pertama dengan `--full --clipboard none` sebelum dipakai harian.
"""

import argparse
import os
import subprocess
import sys
import time

APP = "Ociid Shot"
SAVE_DIR = os.path.expanduser("~/Pictures/OciidShots")


def log(msg, quiet=False):
    if not quiet:
        print(msg, file=sys.stderr, flush=True)


def ensure_dir():
    os.makedirs(SAVE_DIR, exist_ok=True)
    return SAVE_DIR


def unique_path():
    stamp = time.strftime("%Y-%m-%d_%H-%M-%S")
    base = os.path.join(ensure_dir(), f"Screenshot_{stamp}")
    path = base + ".png"
    idx = 1
    while os.path.exists(path):
        path = f"{base}_{idx}.png"
        idx += 1
    return path


def capture(mode, region=None, delay=0, display=None):
    """Ambil screenshot. Return path, atau None kalau user membatalkan."""
    path = unique_path()
    cmd = ["screencapture", "-x", "-t", "png"]
    if delay:
        cmd += ["-T", str(delay)]
    if display:
        cmd += ["-D", str(display)]
    if mode == "region" and region:
        cmd += ["-R", region]
    elif mode == "region":
        cmd += ["-i"]                     # drag area; tekan Space = pilih window
    elif mode == "window":
        cmd += ["-i", "-w", "-o"]         # window tanpa bayangan
    elif mode == "full":
        pass                              # default = seluruh layar utama
    cmd.append(path)
    log("jalankan: " + " ".join(cmd))
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        log(f"screencapture gagal: {proc.stderr.strip() or proc.returncode}")
        return None
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        log("dibatalkan (tidak ada file)")
        return None
    return path


def _osascript(script):
    proc = subprocess.run(["osascript", "-e", script], capture_output=True,
                          text=True)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "osascript gagal")
    return proc.stdout.strip()


def copy_image(path):
    _osascript(
        'set the clipboard to (read (POSIX file "%s") as \u00abclass PNGf\u00bb)'
        % path.replace('"', '\\"')
    )


def copy_file(path):
    # Menaruh file reference di clipboard: paste di Finder/Mail/Telegram = file.
    _osascript('set the clipboard to (POSIX file "%s")'
               % path.replace('"', '\\"'))


def notify(text):
    try:
        _osascript('display notification "%s" with title "%s"'
                   % (text.replace('"', '\\"'), APP))
    except Exception:
        pass


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="ociid_shot_mac", description="Screenshot macOS + copy file/gambar")
    ap.add_argument("--full", action="store_true", help="seluruh layar")
    ap.add_argument("--window", action="store_true", help="pilih window")
    ap.add_argument("--region", metavar="X,Y,W,H", help="area tetap")
    ap.add_argument("--delay", type=int, default=0, help="tunda N detik")
    ap.add_argument("--display", type=int, help="nomor display (1,2,...)")
    ap.add_argument("--clipboard", choices=["image", "file", "none"],
                    default="image", help="isi clipboard setelah capture")
    ap.add_argument("--open", action="store_true",
                    help="buka hasil di Preview (untuk anotasi Markup)")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)

    if args.region and args.region.count(",") != 3:
        ap.error("--region formatnya X,Y,W,H (contoh 100,80,800,600)")
    if args.window:
        mode = "window"
    elif args.full:
        mode = "full"
    else:
        mode = "region"   # default: seleksi area/window interaktif

    path = capture(mode, region=args.region, delay=args.delay,
                   display=args.display)
    if not path:
        return 1

    log(f"tersimpan: {path}")
    if args.open:
        subprocess.run(["open", "-a", "Preview", path], check=False)

    try:
        if args.clipboard == "file":
            copy_file(path)
            notify("File disalin ke clipboard")
        elif args.clipboard == "image":
            copy_image(path)
            notify("Gambar disalin ke clipboard")
        else:
            notify("Tersimpan")
    except Exception as exc:                      # izin Automation ditolak, dll
        log(f"clipboard gagal: {exc}")
        notify("Tersimpan, tapi clipboard gagal")
        print(path)
        return 2

    print(path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
