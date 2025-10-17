#!/usr/bin/env python3
from pathlib import Path; import py_compile, re, sys
root=Path(__file__).resolve().parents[1]
weird=re.compile(r"[\u2018\u2019\u201C\u201D\u2013\u2014\u00A0]")
bad=[]
for p in root.rglob("*.py"):
    try: src=p.read_text(errors="replace")
    except Exception as e: print("skip",p,e); continue
    if weird.search(src): bad.append(str(p))
    py_compile.compile(str(p), doraise=True)
print("✅ All .py compiled OK.")
if bad:
    print("⚠️ Smart punctuation found in:"); [print("  -",b) for b in bad]
