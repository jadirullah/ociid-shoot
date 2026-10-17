# ociid-shot

Screenshot cepat untuk **Pop!_OS / COSMIC (Wayland)**, dibuat karena Flameshot
tidak bisa menangkap layar di COSMIC: `cosmic-comp` tidak mengimplementasikan
`wlr-screencopy-unstable-v1`, jadi `grim` (dan Flameshot via XWayland) gagal.

## Kelebihan dibanding Flameshot di COSMIC

| | Flameshot 12.1 (X11/XWayland) | ociid-shot |
|---|---|---|
| Capture di COSMIC | gagal / hitam | lewat portal resmi `cosmic-screenshot` (~0,07 s) |
| Pilih area | tidak muncul | overlay GTK3 fullscreen |
| Anotasi | ada, tapi UI sering tidak tampil | panah, kotak, elips, pena, teks, mosaic/blur |
| Copy gambar | ya | ya (`image/png`) |
| **Copy file** | **tidak** | **ya** (`text/uri-list`) → paste jadi file di Telegram/Files |
| Dependensi | Qt5 + X11 | python3-gi + pycairo (sudah ada di Pop!_OS) |

## Pakai

```bash
ociid-shot                  # overlay: pilih area → anotasi → copy/simpan
ociid-shot --full           # seluruh layar, simpan + copy gambar
ociid-shot --full --file    # seluruh layar, simpan + copy FILE
ociid-shot --region 800x600+100+50   # potong area tetap, tanpa GUI
ociid-shot --selftest       # render anotasi ke PNG (tanpa GUI)
OCIID_SHOT_DEBUG=1 ociid-shot  # log ke stderr
```

Hotkey COSMIC (sudah dipasang di `~/.config/cosmic/.../Shortcuts/v1/custom`):

- `Ctrl+Shift+P` → overlay pilih area
- `Alt+S` → full screen + copy file

Di overlay:

| Aksi | Fungsi |
|---|---|
| drag | pilih area |
| klik tool lalu drag | gambar anotasi |
| `Enter` (tanpa seleksi) | ambil seluruh layar + copy gambar |
| `Ctrl+Z` | undo |
| `Ctrl+C` / `Enter` | copy gambar + simpan |
| `Ctrl+Shift+C` | copy **file** + simpan |
| `Ctrl+S` | simpan saja |
| `Esc` | batal |

Toolbar memakai ikon tema Adwaita **plus label teks** (Panah, Kotak, Elips,
Pena, Teks, Sensor / Undo, Gambar, File, Simpan, Batal) dan tooltip berisi
shortcut. Di bawah layar ada hintbar berisi daftar shortcut aktif.

`OCIID_SHOT_DEMO=1 ociid-shot` menampilkan seleksi contoh + toolbar (dipakai
untuk QA visual tanpa perlu klik).

Hasil disimpan di `~/Pictures/Screenshots/Screenshot_YYYY-MM-DD_HH-MM-SS.png`.

## Arsitektur

- Capture: `cosmic-screenshot --interactive=false --notify=false -s <dir>`
  (portal XDG `org.freedesktop.portal.Screenshot` v2).
- Overlay: GTK3 + cairo, jendela opaque fullscreen yang menggambar screenshot
  penuh lalu meredupkannya 45 %; area seleksi digambar ulang terang.
- Anotasi disimpan dalam **koordinat layar** dan digeser `(-x, -y)` saat
  merender hasil (`render_region`) — pernah jadi bug: hasil meleset sebesar
  offset seleksi walau preview benar.
- Mosaic/blur: murni cairo (downscale → upscale `FILTER_NEAREST`), tanpa PIL.
- Clipboard: `wl-copy --type image/png` atau `--type text/uri-list`
  (pipa stdout/stderr **wajib** di-`DEVNULL`, kalau tidak `wl-copy` meng-fork
  daemon dan `subprocess.run` menggantung).

## Catatan instalasi

`python3-gi-cairo` tidak terpasang di sistem ini. Modul jembatan cairo diambil
tanpa sudo:

```bash
apt-get download python3-gi-cairo
dpkg -x python3-gi-cairo_*.deb /tmp/gicairo
mkdir -p ~/.local/lib/python3.12/site-packages/gi
cp /tmp/gicairo/usr/lib/python3/dist-packages/gi/_gi_cairo*.so \
   ~/.local/lib/python3.12/site-packages/gi/
```

Skrip menambahkan direktori itu ke `gi.__path__` otomatis kalau
`gi.require_foreign("cairo")` gagal.

## Uji

```bash
/usr/bin/python3 /tmp/test_interaction.py   # handler: drag→anotasi→undo→shortcut
ociid-shot --selftest                       # render anotasi tanpa GUI
```

## macOS (versi terpisah)

`ociid_shot_mac.py` = port untuk MacBook. Bukan port 1:1: capture memakai
`screencapture` bawaan (overlay seleksi macOS, `Space` = pilih window),
clipboard memakai `osascript`, tanpa GTK/pyobjc/PIL.

```bash
python3 ociid_shot_mac.py                        # seleksi area (overlay macOS)
python3 ociid_shot_mac.py --full --clipboard file
python3 ociid_shot_mac.py --window --open        # window + buka Preview untuk Markup
python3 ociid_shot_mac.py --region 100,80,800,600 --delay 3
```

Izin sekali saja: System Settings → Privacy & Security → **Screen Recording**
(untuk Terminal/iTerm/Hermes), dan **Automation** kalau muncul dialog saat copy.
Hasil disimpan di `~/Pictures/OciidShots/`. File ini sudah diuji dengan mock
(command line per mode, pembatalan, kegagalan izin) di Linux, **belum dijalankan
di macOS**.

## Struktur repo & lanjutan development

```
ociid-shot/
├── ociid_shot.py        # aplikasi utama (Linux/COSMIC, GTK3 + cairo)
├── ociid_shot_mac.py    # versi macOS (screencapture + osascript)
├── ociid-shot.desktop   # launcher + desktop actions
├── install.sh           # pasang symlink + desktop entry (tanpa sudo)
├── tests/
│   ├── _load.py             # loader modul dari path repo
│   ├── test_interaction.py  # drag → anotasi → undo → shortcut (butuh sesi Wayland)
│   ├── test_toolbar.py      # ikon+label, hintbar, Enter = full screen
│   ├── test_mac_script.py   # mock macOS: cek perintah tanpa Mac
│   └── run_all.sh           # jalankan semuanya
└── README.md
```

Menambah tool anotasi baru:

1. Tambah entri di `TOOLS` (`id, ikon, label, tooltip`).
2. Tangani bentuknya di `_draw_annot()` (cairo) — anotasi disimpan dalam
   **koordinat layar**.
3. Kalau perlu render khusus (mis. mosaic), tangani di `render_region()`.
4. Tambah tes di `tests/test_interaction.py` lalu `bash tests/run_all.sh`.

Titik-titik yang gampang bikin bug: koordinat anotasi harus digeser
`(-x, -y)` saat render hasil, dan `wl-copy` wajib `stdout/stderr=DEVNULL`.

## Batasan

- Belum ada resize/move seleksi setelah drag (ulangi drag untuk koreksi).
- Hanya monitor yang di-capture `cosmic-screenshot` (single output 1920×1080).
- Copy gambar dan copy file tidak bisa aktif bersamaan (Wayland hanya satu
  pemilik clipboard) — pilih salah satu, file tetap tersimpan.
