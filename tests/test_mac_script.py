#!/usr/bin/python3
"""Uji ociid_shot_mac.py tanpa macOS: mock subprocess, cek cmd yang dibentuk.

Bisa dijalankan di Linux/macOS:
    python3 tests/test_mac_script.py
"""
import contextlib
import importlib.machinery
import importlib.util
import io
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
spec = importlib.util.spec_from_loader(
    "ociid_mac",
    importlib.machinery.SourceFileLoader(
        "ociid_mac", os.path.join(ROOT, "ociid_shot_mac.py")))
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

SANDBOX = "/tmp/mactest-shots"
shutil.rmtree(SANDBOX, ignore_errors=True)
mod.SAVE_DIR = SANDBOX

calls = []
state = {"cancel": False, "clipboard_fails": False}


class FakeProc:
    def __init__(self, rc=0, out="", err=""):
        self.returncode = rc
        self.stdout = out
        self.stderr = err


def fake_run(cmd, **kw):
    calls.append(list(cmd))
    if cmd[0] == "screencapture":
        if not state["cancel"]:
            with open(cmd[-1], "wb") as fh:
                fh.write(b"\x89PNG\r\n\x1a\n fake")
        return FakeProc()
    if cmd[0] == "osascript":
        if state["clipboard_fails"]:
            return FakeProc(1, "", "execution error: Not authorized (-1743)")
        return FakeProc()
    return FakeProc()


mod.subprocess.run = fake_run
mod.notify = lambda text: calls.append(["NOTIFY", text])


def last(kind):
    for c in reversed(calls):
        if c[0] == kind:
            return c
    return None


def scripts():
    return [c[2] for c in calls if c[0] == "osascript"]


print("1) default = overlay seleksi bawaan macOS")
calls.clear()
assert mod.main([]) == 0
sc = last("screencapture")
assert "-i" in sc and "-x" in sc and sc[sc.index("-t") + 1] == "png", sc
assert any("PNGf" in s for s in scripts()), scripts()

print("2) --full --clipboard none")
calls.clear()
assert mod.main(["--full", "--clipboard", "none"]) == 0
sc = last("screencapture")
assert "-i" not in sc and "-R" not in sc, sc
assert not [s for s in scripts() if "clipboard" in s]

print("3) --window")
calls.clear()
assert mod.main(["--window", "--clipboard", "none"]) == 0
sc = last("screencapture")
assert "-i" in sc and "-w" in sc and "-o" in sc, sc

print("4) --region + --clipboard file")
calls.clear()
assert mod.main(["--region", "100,80,800,600", "--clipboard", "file"]) == 0
sc = last("screencapture")
assert sc[sc.index("-R") + 1] == "100,80,800,600", sc
assert any("POSIX file" in s and "PNGf" not in s for s in scripts())

print("5) --delay / --display")
calls.clear()
assert mod.main(["--full", "--delay", "3", "--display", "2",
                 "--clipboard", "none"]) == 0
sc = last("screencapture")
assert sc[sc.index("-T") + 1] == "3" and sc[sc.index("-D") + 1] == "2", sc

print("6) capture dibatalkan")
calls.clear()
state["cancel"] = True
assert mod.main(["--clipboard", "none"]) == 1
state["cancel"] = False

print("7) izin clipboard ditolak -> rc 2, file tetap tersimpan")
calls.clear()
state["clipboard_fails"] = True
assert mod.main(["--clipboard", "file"]) == 2
notifs = [c[1] for c in calls if c[0] == "NOTIFY"]
assert any("clipboard gagal" in n for n in notifs), notifs
state["clipboard_fails"] = False

print("8) region format salah ditolak")
try:
    with contextlib.redirect_stderr(io.StringIO()):
        mod.main(["--region", "800x600"])
    raise AssertionError("seharusnya gagal")
except SystemExit as exc:
    assert exc.code != 0

print("\nOK: semua perintah macOS yang dibentuk sudah benar (mock-based)")
