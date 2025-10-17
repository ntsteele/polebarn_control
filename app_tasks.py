from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4
from typing import Any, Callable
executor = ThreadPoolExecutor(max_workers=2)
JOBS: dict[str, dict[str, Any]] = {}
def submit(fn: Callable, *args, **kwargs) -> str:
    job = uuid4().hex
    JOBS[job] = {"status": "queued", "log": [], "result": None}
    def run():
        JOBS[job]["status"] = "running"
        log = JOBS[job]["log"]
        try:
            res = fn(lambda s: log.append(str(s)), *args, **kwargs)
            JOBS[job]["result"] = res
            JOBS[job]["status"] = "done"
        except Exception as e:
            log.append(f"ERROR: {e}")
            JOBS[job]["status"] = "error"
    executor.submit(run)
    return job
