from flask import Blueprint, request, jsonify, Response
from pathlib import Path
import subprocess, time, json
from app_tasks import submit, JOBS
bp = Blueprint("cal_api", __name__, url_prefix="/api/cal")
ROOT = Path("/home/pi/polebarn_control")
def run_pipeline(log, targets: list[str], apply_delays: bool):
    cap = ROOT/"calibration"/"lockdown_capture.py"
    log(f"Starting capture: {cap.name} targets={','.join(targets)}")
    subprocess.run(["python3", str(cap), "--targets", ",".join(targets)], check=True)
    ana = ROOT/"analysis"/"analyze_lockdown.py"
    log(f"Analyzing latest: {ana.name}")
    subprocess.run(["python3", str(ana)], check=True)
    if apply_delays:
        d = ROOT/"calibration"/"delay_probe_sub_rear.py"
        log("Applying EARLY-only delays (sub/rear)")
        subprocess.run(["python3", str(d), "--apply-sub", "--apply-rear"], check=True)
    try:
        out = sorted((ROOT/"data").glob("lockdown_select_*"))[-1]
        git = subprocess.check_output(["git","rev-parse","--short","HEAD"], cwd=str(ROOT)).decode().strip()
        (out/"CODE_VERSION.json").write_text(json.dumps({"git": git}, indent=2))
        log(f"Stamped CODE_VERSION.json in {out.name} ({git})")
    except Exception as e:
        log(f"Version stamp skipped: {e}")
    return {"ok": True}
@bp.get("/start")
def start():
    targets = request.args.get("targets","main,sub,rear").split(",")
    apply_delays = request.args.get("apply","false").lower() == "true"
    job = submit(run_pipeline, targets, apply_delays)
    return jsonify({"job": job})
@bp.get("/status/<job>")
def status(job): return jsonify(JOBS.get(job, {"error":"unknown job"}))
@bp.get("/logs/<job>")
def logs(job):
    def gen():
        last = 0
        while True:
            j = JOBS.get(job)
            if not j: break
            chunk = j["log"][last:]
            for line in chunk: yield f"data: {line}\n\n"
            last += len(chunk)
            if j["status"] in ("done","error"): break
            time.sleep(0.3)
    return Response(gen(), mimetype="text/event-stream")
