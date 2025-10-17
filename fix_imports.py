#!/usr/bin/env python3
"""
fix_imports.py — automatic import updater
-----------------------------------------
Scans all .py files in the project root (excluding env/, polebarn-venv/, utils/)
and fixes imports that reference moved utility modules.
"""

import re, pathlib, shutil

root = pathlib.Path(__file__).resolve().parent
pattern_map = [
    # modules that used to be top-level but are now under utils/
    (r'\bfrom\s+(parse_qxw)\b',       r'from utils.\1'),
    (r'\bfrom\s+(parse_qxf)\b',       r'from utils.\1'),
    (r'\bfrom\s+(scene_loader)\b',    r'from utils.\1'),
    (r'\bfrom\s+(scene_parser)\b',    r'from utils.\1'),
    (r'\bfrom\s+(mode_set)\b',        r'from utils.\1'),
    (r'\bfrom\s+(qlc_watchdog)\b',    r'from utils.\1'),
    (r'\bfrom\s+(auto_eq_rta)\b',     r'from utils.\1'),
    (r'\bfrom\s+(auto_volume_lufs)\b',r'from utils.\1'),
    (r'\bfrom\s+(beat_detect_xair_or_irig)\b', r'from utils.\1'),

    # handle simple "import module" lines
    (r'(^|\s)import\s+(parse_qxw)\b',          r'from utils import \2'),
    (r'(^|\s)import\s+(parse_qxf)\b',          r'from utils import \2'),
    (r'(^|\s)import\s+(scene_loader)\b',       r'from utils import \2'),
    (r'(^|\s)import\s+(scene_parser)\b',       r'from utils import \2'),
    (r'(^|\s)import\s+(mode_set)\b',           r'from utils import \2'),
    (r'(^|\s)import\s+(qlc_watchdog)\b',       r'from utils import \2'),
    (r'(^|\s)import\s+(auto_eq_rta)\b',        r'from utils import \2'),
    (r'(^|\s)import\s+(auto_volume_lufs)\b',   r'from utils import \2'),
    (r'(^|\s)import\s+(beat_detect_xair_or_irig)\b', r'from utils import \2'),
]

def fix_imports():
    for py_file in root.glob("*.py"):
        if py_file.name in ["fix_imports.py", "__init__.py"]:
            continue
        original = py_file.read_text()
        updated = original
        for pat, repl in pattern_map:
            updated = re.sub(pat, repl, updated)

        if original != updated:
            backup = py_file.with_suffix(py_file.suffix + ".bak")
            shutil.copy2(py_file, backup)
            py_file.write_text(updated)
            print(f"✅ Fixed imports in: {py_file.name} (backup saved as {backup.name})")

    print("\nAll done! If no files were listed, everything was already clean.")

if __name__ == "__main__":
    fix_imports()
