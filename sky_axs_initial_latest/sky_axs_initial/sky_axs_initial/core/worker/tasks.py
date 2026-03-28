#!/usr/bin/env python3
import os, subprocess, json, shlex
from datetime import datetime
DATA_DIR = os.environ.get("DATA_DIR", "/data/jobs")
LEGACY_SCRIPT = os.environ.get("LEGACY_SCRIPT", "/app/core/legacy/sky.sh")
def run_sky(target, extra_args=""):
    ts = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    outdir = os.path.join(DATA_DIR, f"{target}_{ts}")
    os.makedirs(outdir, exist_ok=True)
    logfile = os.path.join(outdir, "sky_run.log")
    cmd = f"{shlex.quote(LEGACY_SCRIPT)} -t {shlex.quote(target)} --outbase {shlex.quote(outdir)} {extra_args or ''}"
    with open(logfile, "w") as fh:
        fh.write(f"Running: {cmd}\n\n")
        try:
            p = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=60*60)
            fh.write("=== STDOUT ===\n")
            fh.write(p.stdout + "\n")
            fh.write("=== STDERR ===\n")
            fh.write(p.stderr + "\n")
            result = {"target": target, "returncode": p.returncode}
        except Exception as e:
            fh.write("=== EXCEPTION ===\n")
            fh.write(str(e) + "\n")
            result = {"target": target, "error": str(e)}
    with open(os.path.join(outdir, "result.json"), "w") as rf:
        json.dump(result, rf, indent=2)
    return result
