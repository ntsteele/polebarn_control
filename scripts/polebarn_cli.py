#!/usr/bin/env python3
"""
Polebarn CLI – one place to run calibration tasks safely.

Usage:
  python scripts/polebarn_cli.py capture  --targets main,sub,rear [--duration 10]
  python scripts/polebarn_cli.py analyze
  python scripts/polebarn_cli.py delay    [--apply]
  python scripts/polebarn_cli.py mics     [--multi]
  python scripts/polebarn_cli.py preamps

All commands log paths and non-zero exits.
"""
import argparse, subprocess, sys, os, shlex, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CAL  = ROOT / "calibration"
ANA  = ROOT / "analysis"
DATA = ROOT / "data"
PYEXE = sys.executable  # use venv python

def run(cmd:list, cwd=None):
    print("▶", " ".join(shlex.quote(c) for c in cmd))
    r = subprocess.run(cmd, cwd=cwd)
    if r.returncode != 0:
        print(f"❌ Exit {r.returncode} for: {' '.join(cmd)}", file=sys.stderr)
        sys.exit(r.returncode)

def latest_folder(prefix:str) -> Path|None:
    items = sorted(DATA.glob(f"{prefix}_*"), key=os.path.getmtime, reverse=True)
    return items[0] if items else None

def cmd_capture(args):
    t = args.targets.lower()
    if t not in {"main,sub,rear","main,sub","main"}:
        print("⚠️ targets must be one of: main,sub,rear | main,sub | main", file=sys.stderr)
        sys.exit(2)
    # use your existing lockdown script that mutes/unmutes safely
    script = CAL / "deep_venue_lockdown_lr_sub_rear.py"
    if not script.exists():
        print(f"❌ Missing: {script}", file=sys.stderr); sys.exit(1)
    os.environ["POLEBARN_SWEEP_SECONDS"] = str(int(args.duration))
    run([PYEXE, str(script)])

def cmd_analyze(_):
    # analyze last LR/Sub/Rear capture
    script = ANA / "analyze_lr_sub_rear.py"
    if not script.exists():
        print(f"❌ Missing: {script}", file=sys.stderr); sys.exit(1)
    run([PYEXE, str(script)])
    print("✅ Analyze done.")
    lf = latest_folder("lockdown_LR_SubRear")
    if lf: print("  →", lf)

def cmd_delay(args):
    script = CAL / "delay_probe_sub_rear.py"
    if not script.exists():
        print(f"❌ Missing: {script}", file=sys.stderr); sys.exit(1)
    if args.apply:
        run([PYEXE, str(script), "--apply-sub", "--apply-rear"])
    else:
        run([PYEXE, str(script)])

def cmd_mics(args):
    script = CAL / ("mic_compare_dbx_multi.py" if args.multi else "mic_compare_dbx.py")
    if not script.exists():
        print(f"❌ Missing: {script}", file=sys.stderr); sys.exit(1)
    run([PYEXE, str(script)])

def cmd_preamps(_):
    script = CAL / "preamp_match_irig.py"
    if not script.exists():
        print(f"❌ Missing: {script}", file=sys.stderr); sys.exit(1)
    run([PYEXE, str(script)])

def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd",required=True)

    ap_cap = sub.add_parser("capture", help="Record Main/Sub/Rear with safe mutes")
    ap_cap.add_argument("--targets", default="main,sub,rear")
    ap_cap.add_argument("--duration", type=float, default=10)
    ap_cap.set_defaults(func=cmd_capture)

    ap_ana = sub.add_parser("analyze", help="Analyze the most recent capture")
    ap_ana.set_defaults(func=cmd_analyze)

    ap_del = sub.add_parser("delay", help="Measure (and optionally apply) delays")
    ap_del.add_argument("--apply", action="store_true")
    ap_del.set_defaults(func=cmd_delay)

    ap_mic = sub.add_parser("mics", help="Compare DBX mics with calibrator")
    ap_mic.add_argument("--multi", action="store_true")
    ap_mic.set_defaults(func=cmd_mics)

    ap_pre = sub.add_parser("preamps", help="Match iRig input gain with calibrator")
    ap_pre.set_defaults(func=cmd_preamps)

    args = ap.parse_args()
    DATA.mkdir(exist_ok=True, parents=True)
    args.func(args)

if __name__ == "__main__":
    main()
