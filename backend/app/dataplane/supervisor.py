"""Timeout supervision; stale leases terminate the child before publication."""
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
import psutil
from backend.app.dataplane.storage import write_new_json


class WorkerCapacityError(ValueError):
    """A bounded child failed without publishing a partial result."""


def directory_bytes(root: Path, cap: int):
    total = 0
    for parent, directories, files in os.walk(root, followlinks=False):
        directories[:] = [name for name in directories if not (Path(parent)/name).is_symlink()]
        for name in files:
            path = Path(parent)/name
            if path.is_symlink():
                raise WorkerCapacityError('WORKER_TEMP_LINK_REJECTED')
            try:
                total += path.stat().st_size
            except FileNotFoundError:
                continue  # DuckDB may remove a completed spill block.
            if total > cap:
                raise WorkerCapacityError('TEMP_DISK_BUDGET_EXCEEDED: narrow the job or increase its approved worker capacity')
    return total


def terminate(process):
    if process.poll() is None:
        if os.name == "posix":
            os.killpg(process.pid, signal.SIGKILL)
        else:
            process.kill()
    process.wait()


def execute(request: dict, directory: Path, heartbeat, *, timeout_s: int):
    directory.mkdir(parents=True, exist_ok=False)
    incoming, outgoing = directory/"request.json", directory/"result.json"
    write_new_json(incoming, request)
    if os.name == "posix":
        incoming.chmod(0o600)
    # Only operational variables; no app secrets or provider keys inherited.
    env = {key: os.environ[key] for key in ("PATH", "SYSTEMROOT", "PYTHONPATH") if key in os.environ}
    env.update(PYTHONDONTWRITEBYTECODE="1", OMP_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1",
               PYTHONUNBUFFERED="1", HOME=str(directory), TMPDIR=str(directory))
    process = subprocess.Popen([sys.executable, "-m", "backend.app.dataplane.task", str(incoming), str(outgoing)],
        env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=os.name == "posix")
    started, renewed, measured = time.monotonic(), 0.0, 0.0
    peak_rss, peak_disk = 0, 0
    worker_mb = request['limits'].get('worker_memory_mb', 1024)
    rss_cap = int(worker_mb * .875 * 1024**2)  # reserve one eighth for the parent
    disk_cap = request['limits'].get('spill_mb', 2048) * 1024**2
    budget_root = directory.parent if request.get('output') else directory
    observed = psutil.Process(process.pid)
    try:
        while process.poll() is None:
            if time.monotonic()-started > timeout_s:
                raise TimeoutError("Dataplane wall-clock budget exceeded")
            if time.monotonic()-renewed > 5:
                heartbeat()
                renewed = time.monotonic()
            try:
                rss = observed.memory_info().rss
                rss += sum(child.memory_info().rss for child in observed.children(recursive=True)
                    if child.is_running())
                peak_rss = max(peak_rss, rss)
                if rss > rss_cap:
                    raise WorkerCapacityError('PROCESS_MEMORY_BUDGET_EXCEEDED: narrow the job or increase its approved worker capacity')
            except psutil.NoSuchProcess:
                pass
            if time.monotonic() - measured > .5:
                peak_disk = max(peak_disk, directory_bytes(budget_root, disk_cap))
                measured = time.monotonic()
            time.sleep(0.1)
        heartbeat()
        peak_disk = max(peak_disk, directory_bytes(budget_root, disk_cap))
        if not outgoing.is_file() or outgoing.stat().st_size > request["limits"]["result_bytes"] + 4*1024**2:
            raise WorkerCapacityError("WORKER_EXIT_OR_OUTPUT_BUDGET: no complete bounded result was published")
        value = json.loads(outgoing.read_text())
        if not value["ok"]:
            if value['error'] in {'MemoryError', 'OutOfMemoryException', 'OutOfMemoryError'}:
                raise WorkerCapacityError('MEMORY_ALLOCATION_FAILED: narrow the job or increase approved capacity')
            raise ValueError(value["error"])
        if process.returncode:
            raise ValueError("Worker exited unsuccessfully")
        return value["result"]
    finally:
        terminate(process)
        try:
            write_new_json(directory/'supervision.json', {'peak_observed_rss_bytes': peak_rss,
                'peak_observed_temporary_bytes': peak_disk, 'rss_limit_bytes': rss_cap,
                'temporary_limit_bytes': disk_cap, 'timeout_seconds': timeout_s,
                'elapsed_seconds': time.monotonic()-started, 'returncode': process.returncode,
                'sampling': 'RSS at approximately 100ms; temporary disk at approximately 500ms; not an instantaneous peak guarantee'})
        finally:
            # Even a failed diagnostic write must not retain source credentials.
            incoming.unlink(missing_ok=True)
