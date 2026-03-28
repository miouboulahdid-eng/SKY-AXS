#!/usr/bin/env python3
"""
Enhanced Sandbox Runner (wrapper around existing SandboxRunner)

Features:
 - Runs PoC in sandbox using existing runner (Docker SDK or docker CLI fallback)
 - Supports multiple attempts (retries) with delay
 - Collects attempt outputs, hashes, exit codes, timings
 - Simple heuristic analyser to derive verdict and confidence
 - Optional upload of result JSON to S3 if AWS_UPLOAD_RESULTS=1 and boto3 available
 - Writes enriched JSON to AXS_RESULTS_DIR (default /app/data/results)

Usage:
  python3 core/sandbox/runner_enhanced.py <target> --poc=<name> [--retries=2] [--delay=3] [--timeout=30]

Environment:
  AXS_RESULTS_DIR (default /app/data/results)
  AWS_UPLOAD_RESULTS=1 to enable S3 upload (optional)
  S3_BUCKET (required if AWS_UPLOAD_RESULTS=1)
  AWS_REGION (optional, default from env/aws config)
"""
import os, sys, time, json, uuid, hashlib, datetime, subprocess, shlex, logging, traceback

# try import docker SDK if available - runner will use whatever method available
try:
    import docker
    DOCKER_SDK = True
except Exception:
    DOCKER_SDK = False

# boto3 optional for S3 upload
try:
    import boto3
    from botocore.exceptions import BotoCoreError, ClientError
    BOTO3_AVAIL = True
except Exception:
    BOTO3_AVAIL = False

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
_log = logging.getLogger("sandbox.runner_enhanced")

# reuse defaults from original runner if present
RESULTS_DIR = os.environ.get("AXS_RESULTS_DIR", "/app/data/results")
IMAGE = os.environ.get("AXS_SANDBOX_IMAGE", "python:3.11-slim")
CONTAINER_PREFIX = os.environ.get("AXS_SANDBOX_PREFIX", "axs_sandbox_")
DEFAULT_TIMEOUT = int(os.environ.get("AXS_SANDBOX_TIMEOUT", "30"))

os.makedirs(RESULTS_DIR, exist_ok=True)

# compute host pocs path relative to this file
_THIS_DIR = os.path.abspath(os.path.dirname(__file__))
HOST_POCS_DIR = os.path.abspath(os.path.join(_THIS_DIR, "pocs"))
HAS_HOST_POCS = os.path.isdir(HOST_POCS_DIR)

def _safe_name(target: str) -> str:
    name = target.replace("://", "_").replace("/", "_").replace("?", "_").replace("=", "_")
    return "".join(c if (c.isalnum() or c in '._-') else '_' for c in name)

def _hash_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()

def _write_result_file(result: dict) -> str:
    ts = datetime.datetime.utcnow().strftime("%Y%m%d%H%M%S")
    fname = f"{_safe_name(result.get('target','unknown'))}_{ts}_{uuid.uuid4().hex[:12]}.json"
    path = os.path.join(RESULTS_DIR, fname)
    with open(path, "w") as f:
        json.dump(result, f, indent=2, default=str)
    _log.info("Wrote sandbox result to: %s", path)
    return path

class SimpleSandboxInvoker:
    """
    Lightweight invoker that mimics original runner behavior:
      - uses docker SDK when available and working
      - otherwise falls back to docker CLI
    Provides run_once(target, extra, timeout) -> (attempt_info_dict)
    attempt_info contains keys: attempt, job_id, container, exit_code, output, stdout_bytes_hash, duration
    """
    def __init__(self, image=IMAGE, timeout=DEFAULT_TIMEOUT):
        self.image = image
        self.timeout = timeout
        self.client = None
        if DOCKER_SDK:
            try:
                self.client = docker.from_env()
            except Exception as e:
                _log.warning("docker.from_env() failed, will fallback to CLI: %s", e)
                self.client = None

    def _run_with_sdk(self, job_id, cmd, env=None, volumes=None, timeout=None):
        try:
            container = self.client.containers.create(
                image=self.image,
                command=["/bin/sh", "-lc", cmd],
                name=CONTAINER_PREFIX + job_id,
                detach=True,
                stdin_open=False,
                tty=False,
                network_disabled=True,
                working_dir="/tmp",
                environment=env or {},
                volumes=volumes or {}
            )
            container.start()
            try:
                exit_status = container.wait(timeout=timeout or self.timeout)
                rc = exit_status.get("StatusCode", 0) if isinstance(exit_status, dict) else int(exit_status)
            except Exception:
                _log.warning("Container timeout or wait error - killing")
                try:
                    container.kill()
                except Exception:
                    pass
                rc = -1
            try:
                logs = container.logs(stdout=True, stderr=True, stream=False)
                if isinstance(logs, bytes):
                    logs_bytes = logs
                    logs = logs.decode(errors="replace")
                else:
                    logs_bytes = str(logs).encode()
            except Exception:
                logs = "<failed to read logs>"
                logs_bytes = b""
            # best-effort cleanup
            try:
                container.remove(force=True)
            except Exception:
                pass
            return rc, logs, logs_bytes
        except Exception as e:
            _log.error("SDK run failed: %s", traceback.format_exc())
            return -2, f"SDK runner error: {e}", b""

    def _run_with_cli(self, job_id, cmd, env=None, timeout=None):
        cname = CONTAINER_PREFIX + job_id
        vflag = ""
        if HAS_HOST_POCS:
            host_pocs_quoted = shlex.quote(HOST_POCS_DIR)
            vflag = f"-v {host_pocs_quoted}:/pocs:ro "
        env_flags = ""
        if env:
            for k,v in env.items():
                env_flags += f"-e {shlex.quote(k)}={shlex.quote(str(v))} "
        full_cmd = (
            f"docker run --rm --name {shlex.quote(cname)} --network none "
            f"{vflag}{env_flags}{shlex.quote(self.image)} /bin/sh -lc {shlex.quote(cmd)}"
        )
        _log.info("Running CLI docker: %s", full_cmd)
        try:
            completed = subprocess.run(full_cmd, shell=True, capture_output=True, timeout=(timeout or self.timeout))
            out = (completed.stdout or b"") + (completed.stderr or b"")
            try:
                out_decoded = out.decode(errors="replace")
            except Exception:
                out_decoded = str(out)
            return completed.returncode, out_decoded, out
        except subprocess.TimeoutExpired as te:
            _log.warning("CLI docker timeout")
            data = (te.stdout or b"") + (te.stderr or b"") if hasattr(te, "stdout") else b""
            try:
                dd = data.decode(errors="replace")
            except Exception:
                dd = "<timeout>"
            return -1, dd, data
        except Exception as e:
            _log.error("CLI run error: %s", traceback.format_exc())
            return -2, f"CLI runner error: {e}", b""

    def run_once(self, target: str, extra: str, timeout: int = None):
        job_id = uuid.uuid4().hex[:12]
        # determine command like original runner._create_cmd logic (simple)
        cmd = None
        if "--poc=" in (extra or "") or " --poc " in (" " + (extra or "") + " "):
            poc = "unknown"
            try:
                if "--poc=" in extra:
                    poc = extra.split("--poc=",1)[1].split()[0]
                else:
                    parts = shlex.split(extra)
                    if "--poc" in parts:
                        i = parts.index("--poc")
                        poc = parts[i+1]
            except Exception:
                poc = "unknown"
            cmd = f"cd /pocs/{poc} 2>/dev/null || true; if [ -x ./run.sh ]; then ./run.sh; else echo 'PoC not found /pocs/{poc}/run.sh'; fi"
        elif extra.startswith("--cmd=") or extra.startswith("-c="):
            if extra.startswith("--cmd="):
                cmdstr = extra.split("--cmd=",1)[1]
            else:
                cmdstr = extra.split("-c=",1)[1]
            cmd = f"sh -c {shlex.quote(cmdstr)}"
        else:
            cmd = "echo 'SANDBOX STUB: no-op' && echo 'done'"

        env = {"AXS_TARGET": target, "AXS_EXTRA": extra}
        timeout = timeout or self.timeout

        if self.client:
            rc, out, out_bytes = self._run_with_sdk(job_id, cmd, env=env, volumes=( { HOST_POCS_DIR: {'bind': '/pocs', 'mode': 'ro'} } if HAS_HOST_POCS else None ), timeout=timeout)
        else:
            rc, out, out_bytes = self._run_with_cli(job_id, cmd, env=env, timeout=timeout)

        attempt_info = {
            "attempt_id": job_id,
            "container": CONTAINER_PREFIX + job_id,
            "exit_code": int(rc),
            "output": out if isinstance(out, str) else str(out),
            "output_hash": _hash_bytes(out_bytes if isinstance(out_bytes, (bytes,bytearray)) else str(out).encode()),
            "duration": None
        }
        # duration is not trivial to compute here; leave None or compute if we measured
        return attempt_info

def analyse_attempts(attempts):
    """
    Simple heuristic analyzer:
     - looks for keywords in outputs
     - votes among attempts
     - computes confidence
    """
    verdict_votes = []
    for a in attempts:
        out = (a.get("output","") or "").lower()
        v = "no_issue"
        if any(k in out for k in ["vulnerable", "vuln", "vulnerability", "vulnerable_simulated", "vulnerable_simulation"]):
            v = "vulnerable"
        elif any(k in out for k in ["xss", "cross-site", "reflected", "possible_xss", "xss_simulated"]):
            v = "possible_xss"
        elif any(k in out for k in ["sql syntax", "mysql", "postgres", "sql error", "syntax error"]):
            # could be indicative of sqli
            v = "possible_sqli"
        elif "timeout" in out or "error" in out and len(out) < 200:
            v = "error"
        verdict_votes.append(v)

    # majority rules
    if verdict_votes.count("vulnerable") >= 1 and verdict_votes.count("vulnerable") >= (len([v for v in verdict_votes if v!="no_issue"])/2 if len(verdict_votes)>0 else 1):
        verdict = "vulnerable"
        confidence = 0.85 + 0.05 * (verdict_votes.count("vulnerable") - 1)
    elif any(v.startswith("possible_") for v in verdict_votes):
        # pick best possible
        verdict = "possible"
        confidence = 0.5 + 0.1 * sum(1 for v in verdict_votes if v.startswith("possible_"))
        if confidence > 0.85: confidence = 0.85
    elif any(v == "error" for v in verdict_votes):
        verdict = "error"
        confidence = 0.2
    else:
        verdict = "ok"
        confidence = 0.05
    # clamp confidence
    confidence = max(0.0, min(0.99, confidence))
    return verdict, round(confidence, 2), verdict_votes

def upload_to_s3_if_enabled(local_path):
    if os.environ.get("AWS_UPLOAD_RESULTS", "0") != "1":
        return None
    if not BOTO3_AVAIL:
        _log.warning("AWS_UPLOAD_RESULTS requested but boto3 not available")
        return None
    bucket = os.environ.get("S3_BUCKET")
    if not bucket:
        _log.warning("AWS_UPLOAD_RESULTS=1 but S3_BUCKET not set")
        return None
    region = os.environ.get("AWS_REGION")
    key = f"results/{os.path.basename(local_path)}"
    s3 = boto3.client("s3", region_name=region) if region else boto3.client("s3")
    try:
        s3.upload_file(local_path, bucket, key)
        url = f"s3://{bucket}/{key}"
        _log.info("Uploaded %s -> %s", local_path, url)
        return url
    except (BotoCoreError, ClientError) as e:
        _log.error("S3 upload failed: %s", e)
        return None

def run_enhanced(target: str, extra: str = "", retries: int = 2, retry_delay: int = 3, timeout: int = None):
    inv = SimpleSandboxInvoker(timeout=timeout or DEFAULT_TIMEOUT)
    attempts = []
    for i in range(1, max(1, retries)+1):
        _log.info("Enhanced runner: attempt %d/%d", i, retries)
        t0 = time.time()
        att = inv.run_once(target=target, extra=extra, timeout=timeout)
        att["attempt"] = i
        att["duration"] = round(time.time() - t0, 3)
        attempts.append(att)
        # small delay between attempts unless last
        if i < retries:
            time.sleep(retry_delay)

    verdict, confidence, votes = analyse_attempts(attempts)
    result = {
        "job_id": uuid.uuid4().hex[:12],
        "target": target,
        "poc_extra": extra,
        "status": verdict,
        "confidence": confidence,
        "votes": votes,
        "attempts": attempts,
        "timestamp": datetime.datetime.utcnow().isoformat(),
        "notes": []
    }

    # write result locally
    path = _write_result_file(result)
    # optional upload
    s3url = upload_to_s3_if_enabled(path)
    if s3url:
        result["evidence_s3"] = s3url
        # rewrite with s3 field
        with open(path, "w") as f:
            json.dump(result, f, indent=2, default=str)

    return path, result

def _usage():
    print("Usage: runner_enhanced.py <target> --poc=<name> [--retries=N] [--delay=secs] [--timeout=secs]")
    print("Env: AWS_UPLOAD_RESULTS=1 S3_BUCKET=... AWS_REGION=... to enable upload")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        _usage()
        sys.exit(2)
    tgt = sys.argv[1]
    # parse simple args
    extra = ""
    retries = 2
    delay = 3
    timeout = DEFAULT_TIMEOUT
    for a in sys.argv[2:]:
        if a.startswith("--poc="):
            extra = a
        elif a.startswith("--retries="):
            try:
                retries = int(a.split("=",1)[1])
            except:
                pass
        elif a.startswith("--delay="):
            try:
                delay = int(a.split("=",1)[1])
            except:
                pass
        elif a.startswith("--timeout="):
            try:
                timeout = int(a.split("=",1)[1])
            except:
                pass
        else:
            # pass-through (e.g. --cmd= or others)
            extra = extra + " " + a if extra else a
    path, res = run_enhanced(tgt, extra=extra, retries=retries, retry_delay=delay, timeout=timeout)
    print("Result JSON:", path)
    print(json.dumps(res, indent=2))
