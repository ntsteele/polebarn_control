#!/usr/bin/env python3
from pathlib import Path
import json, sys, re

ROOT = Path("/home/pi/polebarn_control")
expected = {
  "scripts": ["polebarn_cli.py","health_check.py"],
  "calibration": [
    "deep_venue_lockdown_lr_sub_rear.py",
    "delay_probe_sub_rear.py",
    "preamp_match_irig.py",
    "mic_compare_dbx.py",
    "mic_compare_dbx_multi.py",
    "audio_io.py",
    "set_mic_offset.py",
    "mic_offsets.json",
  ],
  "analysis": ["analyze_lr_sub_rear.py"],
}
checks = []

def ok(flag, msg, path=None):
    checks.append({"ok": bool(flag), "msg": msg, "path": str(path) if path else None})

# venv
venv_ok = (ROOT/"env/bin/python").exists()
ok(venv_ok, "venv found at ./env", ROOT/"env/bin/python")

# .gitignore
gi = ROOT/".gitignore"
gi_ok = gi.exists() and "qlcplus/" in gi.read_text() and any(x in gi.read_text() for x in ("env/",".venv/","venv/"))
ok(gi_ok, ".gitignore ignores qlcplus/ and venv", gi)

# structure & key files
for folder, files in expected.items():
    base = ROOT/folder
    ok(base.exists(), f"{folder}/ exists", base)
    for f in files:
        ok((base/f).exists(), f"{folder}/{f} present", base/f)

# web app entry
wc = ROOT/"web_control.py"
ok(wc.exists(), "web_control.py present", wc)
if wc.exists():
    txt = wc.read_text(errors="ignore")
    ok("Flask(" in txt, "web_control.py creates a Flask app", wc)

# any smart punctuation lingering?
weird = re.compile(r"[\u2018\u2019\u201C\u201D\u2013\u2014\u00A0]")
badfiles = []
for p in ROOT.rglob("*.py"):
    s = p.read_text(errors="replace")
    if weird.search(s):
        badfiles.append(str(p.relative_to(ROOT)))
ok(len(badfiles)==0, "no smart punctuation in .py files", None)

summary = {
  "root": str(ROOT),
  "pass": all(c["ok"] for c in checks),
  "fail_count": sum(1 for c in checks if not c["ok"]),
  "checks": checks,
  "bad_punctuation_files": badfiles,
}
print(json.dumps(summary, indent=2))
