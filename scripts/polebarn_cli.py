#!/usr/bin/env python3
import argparse, subprocess
from pathlib import Path
ROOT = Path("/home/pi/polebarn_control")
def run(cmd): print("+"," ".join(cmd)); subprocess.run(cmd, check=True)
def main():
    ap = argparse.ArgumentParser(description="Polebarn CLI")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_cap = sub.add_parser("capture"); p_cap.add_argument("--targets", default="main,sub,rear")
    sub.add_parser("analyze")
    p_del = sub.add_parser("delay"); p_del.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    if a.cmd=="capture": run(["python3", str(ROOT/"calibration"/"lockdown_capture.py"), "--targets", a.targets])
    elif a.cmd=="analyze": run(["python3", str(ROOT/"analysis"/"analyze_lockdown.py")])
    elif a.cmd=="delay":
        cmd=["python3", str(ROOT/"calibration"/"delay_probe_sub_rear.py")]
        if a.apply: cmd+=["--apply-sub","--apply-rear"]
        run(cmd)
if __name__=="__main__": main()
