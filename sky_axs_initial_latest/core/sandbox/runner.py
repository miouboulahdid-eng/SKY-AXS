#!/usr/bin/env python3
"""
Sandbox runner (Docker-based) - compatible replacement.

Provides:
 - class SandboxRunner with methods run(...) and run_in_sandbox(...)
 - module-level run_in_sandbox(...) helper
 - writes result JSON files to data/results/<target>_<ts>_<id>.json
 - simple, robust: handles extra flags (--poc=..., --cmd=...) and timeouts.
 - mounts core/sandbox/pocs as /pocs inside the container (read-only) when present.
"""

import os
import json
import time
import uuid
import shlex
import logging
import datetime
import tempfile
import pathlib
import traceback
from typing import Tuple, Optional

# try import docker SDK; fall back to subprocess if missing
try:
    import docker
    from docker.errors import DockerException
    DOCKER_SDK = True
except Exception:
    DOCKER_SDK = False

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
_log = logging.getLogger("sandbox.runner")

RESULTS_DIR = os.environ.get("AXS_RESULTS_DIR", "/app/data/results")
IMAGE = os.environ.get("AXS_SANDBOX_IMAGE", "python:3.11-slim")
CONTAINER_PREFIX = os.environ.get("AXS_SANDBOX_PREFIX", "axs_sandbox_")
DEFAULT_TIMEOUT = int(os.environ.get("AXS_SANDBOX_TIMEOUT", "30"))

os.makedirs(RESULTS_DIR, exist_ok=True)

# compute host pocs path (relative to this file)
_THIS_DIR = os.path.abspath(os.path.dirname(__file__))
HOST_POCS_DIR = os.path.abspath(os.path.join(_THIS_DIR, "pocs"))
HAS_HOST_POCS = os.path.isdir(HOST_POCS_DIR)

def _safe_name(target: str) -> str:
    # replace non-alnum with underscore
    name = target.replace("://", "_").replace("/", "_").replace("?", "_").replace("=", "_")
    return "".join(c if (c.isalnum() or c in '._-') else '_' for c in name)

def _write_result_file(target: str, poc_name: str, result: dict) -> str:
    ts = datetime.datetime.utcnow().strftime("%Y%m%d%H%M%S")
    fname = f"{_safe_name(target)}_{ts}_{uuid.uuid4().hex[:12]}.json"
    path = os.path.join(RESULTS_DIR, fname)
    try:
        with open(path, "w") as f:
            json.dump(result, f, indent=2, default=str)
        _log.info("Wrote sandbox result to: %s", path)
    except Exception:
        _log.error("Failed to write result file: %s", traceback.format_exc())
        raise
    return path

class SandboxRunner:
    """
    Simple Docker-based sandbox runner.
    Methods:
      - run(target, extra, timeout) -> (result_path, result_dict)
      - run_in_sandbox(...): same as run (compat wrapper)
    """
    def __init__(self, image: str = IMAGE, timeout: int = DEFAULT_TIMEOUT):
        self.image = image
        self.timeout = timeout
        self.client = None
        if DOCKER_SDK:
            try:
                self.client = docker.from_env()
            except Exception as e:
                _log.warning("Docker SDK present but docker.from_env() failed: %s", e)
                self.client = None

    def _create_cmd(self, extra: str) -> Tuple[str, str]:
        """
        Interpret extra:
         - if contains --poc=NAME or --poc NAME -> run /pocs/NAME/run.sh (we will expect env AXS_TARGET/AXS_EXTRA)
         - if startswith --cmd=... or -c=... -> run given inline command in sh -c
         - else treat as '--dry-run' or bare args -> run stub
        Return (mode, cmd)
        """
        extra = (extra or "").strip()
        # Handle --poc= or --poc NAME
        if "--poc=" in extra or " --poc " in (" " + extra + " "):
            # extract name
            poc = "unknown"
            try:
                if "--poc=" in extra:
                    poc = extra.split("--poc=", 1)[1].split()[0]
                else:
                    parts = shlex.split(extra)
                    if "--poc" in parts:
                        i = parts.index("--poc")
                        poc = parts[i+1]
            except Exception:
                poc = "unknown"
            # Do not inline AXS_TARGET here; rely on environment variables passed when container is created.
            cmd = (
                f"cd /pocs/{poc} 2>/dev/null || true; "
                f"if [ -x ./run.sh ]; then ./run.sh; "
                f"else echo \"PoC not found or not executable: /pocs/{poc}/run.sh\"; fi"
            )
            return ("poc", cmd)

        if extra.startswith("--cmd=") or extra.startswith("-c="):
            # inline command
            if extra.startswith("--cmd="):
                cmdstr = extra.split("--cmd=",1)[1]
            else:
                cmdstr = extra.split("-c=",1)[1]
            return ("cmd", f"sh -c {shlex.quote(cmdstr)}")

        # fallback: dry-run stub
        return ("stub", "echo 'SANDBOX STUB: no-op' && echo 'done'")

    def run(self, target: str, extra: str = "", timeout: Optional[int] = None) -> Tuple[str, dict]:
        """
        Execute the sandbox job and return (result_path, result_dict).
        """
        timeout = timeout or self.timeout or DEFAULT_TIMEOUT
        job_id = uuid.uuid4().hex[:12]
        mode, cmd = self._create_cmd(extra)

        result = {
            "job_id": job_id,
            "target": target,
            "extra": extra,
            "status": "ok",
            "timestamp": datetime.datetime.utcnow().isoformat(),
            "container": None,
            "output": "",
            "exit_code": None,
            "notes": []
        }

        # If Docker SDK available, prefer it. Otherwise fallback to `docker run` via subprocess.
        if self.client:
            try:
                _log.info("Creating container %s%s", CONTAINER_PREFIX, job_id)

                # prepare volumes mapping if host pocs dir exists
                volumes = None
                if HAS_HOST_POCS:
                    # docker SDK expects a dict: { host_path: {'bind': container_path, 'mode': 'ro'} }
                    volumes = { HOST_POCS_DIR: {'bind': '/pocs', 'mode': 'ro'} }

                container = self.client.containers.create(
                    image=self.image,
                    command=["/bin/sh", "-lc", cmd],
                    name=CONTAINER_PREFIX + job_id,
                    detach=True,
                    stdin_open=False,
                    tty=False,
                    network_disabled=True,
                    working_dir="/tmp",
                    environment={"AXS_TARGET": target, "AXS_EXTRA": extra},
                    volumes=volumes,
                )
                result["container"] = container.name
                container.start()
                try:
                    exit_status = container.wait(timeout=timeout)
                    rc = exit_status.get("StatusCode", 0) if isinstance(exit_status, dict) else int(exit_status)
                except Exception:
                    _log.warning("Container timeout or error; trying to kill")
                    try:
                        container.kill()
                    except Exception:
                        pass
                    rc = -1
                # collect logs (stdout+stderr)
                try:
                    logs = container.logs(stdout=True, stderr=True, stream=False)
                    if isinstance(logs, bytes):
                        logs = logs.decode(errors="replace")
                except Exception:
                    logs = "<failed to read logs>"
                result["output"] = logs
                result["exit_code"] = rc
                if rc != 0:
                    result["status"] = "failed"
                # cleanup container (best-effort)
                try:
                    container.remove(force=True)
                except Exception:
                    pass
            except Exception as e:
                _log.error("Docker runner error: %s", traceback.format_exc())
                result["status"] = "failed"
                result["notes"].append(str(e))
        else:
            # fallback to docker CLI
            import subprocess
            cname = CONTAINER_PREFIX + job_id
            result["container"] = cname

            # if host pocs directory exists, mount it read-only
            vflag = ""
            if HAS_HOST_POCS:
                # quote the host path for CLI
                host_pocs_quoted = shlex.quote(HOST_POCS_DIR)
                vflag = f"-v {host_pocs_quoted}:/pocs:ro "

            # build full docker run command (careful with quoting)
            full_cmd = (
                f"docker run --rm --name {shlex.quote(cname)} --network none "
                f"{vflag}"
                f"-e AXS_TARGET={shlex.quote(target)} -e AXS_EXTRA={shlex.quote(extra)} "
                f"{shlex.quote(self.image)} /bin/sh -lc {shlex.quote(cmd)}"
            )
            _log.info("Running fallback docker CLI: %s", full_cmd)
            try:
                completed = subprocess.run(full_cmd, shell=True, capture_output=True, timeout=timeout, text=True)
                result["output"] = (completed.stdout or "") + (completed.stderr or "")
                result["exit_code"] = completed.returncode
                if completed.returncode != 0:
                    result["status"] = "failed"
            except subprocess.TimeoutExpired as te:
                result["status"] = "failed"
                result["notes"].append("timeout")
                result["output"] = (te.stdout or "") + (te.stderr or "") if hasattr(te, "stdout") else "<timeout>"
                result["exit_code"] = -1
            except Exception as e:
                result["status"] = "failed"
                result["notes"].append(str(e))

        # finalize timestamp_end
        result["timestamp_end"] = datetime.datetime.utcnow().isoformat()
        # write result
        path = _write_result_file(target, poc_name=(mode or "inline"), result=result)
        return path, result

    # compatibility wrapper
    def run_in_sandbox(self, target: str, extra: str = "", timeout: Optional[int] = None):
        return self.run(target=target, extra=extra, timeout=timeout)

# module-level helper for backward-compatible callers
def run_in_sandbox(target: str, extra: str = "", timeout: Optional[int] = None):
    r = SandboxRunner()
    return r.run(target=target, extra=extra, timeout=timeout)

# if executed as script, provide small CLI
if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: runner.py <target> [<extra>] [<timeout>]")
        sys.exit(2)
    tgt = sys.argv[1]
    extra = sys.argv[2] if len(sys.argv) > 2 else ""
    timeout = int(sys.argv[3]) if len(sys.argv) > 3 else DEFAULT_TIMEOUT
    p, r = run_in_sandbox(tgt, extra=extra, timeout=timeout)
    print("Result JSON:", p)
    print(json.dumps(r, indent=2))
