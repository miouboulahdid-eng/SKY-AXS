#!/usr/bin/env python3
"""
Sandbox dispatcher - runs PoCs and publishes results to Redis stream for real-time consumption.
"""
import sys, os, argparse, json, datetime, logging
from typing import List, Tuple

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
_log = logging.getLogger("sandbox.dispatcher")

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

USE_ENHANCED = False
_enhanced_runner = None
SandboxRunner = None

try:
    from core.sandbox import runner_enhanced as _re
    if hasattr(_re, "run_enhanced"):
        _enhanced_runner = _re.run_enhanced
        USE_ENHANCED = True
        _log.info("Using core.sandbox.runner_enhanced.run_enhanced as sandbox runner")
except Exception:
    _log.debug("core.sandbox.runner_enhanced not available")

if not USE_ENHANCED:
    try:
        from core.sandbox.runner import SandboxRunner as _SR
        SandboxRunner = _SR
        _log.info("Using core.sandbox.runner.SandboxRunner")
    except Exception:
        try:
            from sandbox.runner import SandboxRunner as _SR2
            SandboxRunner = _SR2
            _log.info("Using sandbox.runner.SandboxRunner")
        except Exception as e:
            logging.exception("Failed to import sandbox runner")
            raise

# Redis client (optional) - publish to stream if available
try:
    import redis
    REDIS_HOST = os.environ.get("REDIS_HOST", "redis")
    REDIS_PORT = int(os.environ.get("REDIS_PORT", "6379"))
    REDIS_DB = int(os.environ.get("REDIS_DB", "0"))
    rds = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB, socket_connect_timeout=5)
    # test connection lazily when used
except Exception:
    rds = None

def ensure_dirs():
    os.makedirs("data/results", exist_ok=True)
    os.makedirs("data/decisions", exist_ok=True)
    os.makedirs("data/healer", exist_ok=True)

def write_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2, default=str)

def _safe_target_fname(t: str) -> str:
    return t.replace("://", "_").replace("/", "_").replace("?", "_").replace("=", "_")

def _publish_to_stream(result_obj, stream_name="stream:sandbox_results"):
    if not rds:
        return None
    try:
        fields = {
            "target": str(result_obj.get("target","")),
            "poc": str(result_obj.get("poc","")),
            "status": str(result_obj.get("status", result_obj.get("result",{}).get("status",""))),
            "confidence": str(result_obj.get("result",{}).get("confidence", "")),
            "timestamp": str(result_obj.get("result",{}).get("timestamp", datetime.datetime.utcnow().isoformat())),
            "file": str(result_obj.get("result",{}).get("_result_file",""))
        }
        # remove empty
        fields = {k:v for k,v in fields.items() if v is not None and v != ""}
        msg_id = rds.xadd(stream_name, fields, maxlen=1000, approximate=True)
        _log.info("Published result to stream %s id=%s", stream_name, msg_id)
        return msg_id
    except Exception as e:
        _log.warning("Failed to publish to redis stream: %s", e)
        return None

def run_dispatch(target: str, strategy: List[str], extra: str = "", timeout: int = 60):
    ensure_dirs()
    started_at = datetime.datetime.utcnow().isoformat()
    dispatch_results = []
    runner_instance = None
    if not USE_ENHANCED and SandboxRunner is not None:
        try:
            runner_instance = SandboxRunner()
        except Exception as e:
            _log.warning("Failed to instantiate SandboxRunner: %s", e)
            runner_instance = None

    for poc in strategy:
        _log.info("[dispatcher] Running PoC: %s", poc)
        poc_extra = extra
        if "--poc=" not in poc_extra and poc:
            poc_extra = f"{poc_extra} --poc={poc}" if poc_extra.strip() else f"--poc={poc}"

        try:
            if USE_ENHANCED:
                # enhanced runner returns (path, result)
                path, result = _enhanced_runner(target, poc_extra)
            else:
                path, result = runner_instance.run_in_sandbox(target=target, extra=poc_extra, timeout=timeout)
            # attach path in result for tracing
            result["_result_file"] = path
            _log.info("[dispatcher] PoC %s finished: path=%s", poc, path)
            entry = {"poc": poc, "status": "ok", "result": result}
            dispatch_results.append(entry)

            # publish to redis stream for real-time consumers
            _publish_to_stream({"target": target, "poc": poc, "status": "ok", "result": result})

        except Exception as e:
            logging.exception(f"[dispatcher] ERROR running {poc}")
            entry = {"poc": poc, "status": "error", "error": str(e)}
            dispatch_results.append(entry)
            _publish_to_stream({"target": target, "poc": poc, "status": "error", "result": {"error": str(e)}})

    ended_at = datetime.datetime.utcnow().isoformat()
    summary = {
        "target": target,
        "strategy": strategy,
        "extra": extra,
        "started_at": started_at,
        "ended_at": ended_at,
        "results": dispatch_results
    }

    fname = f"data/decisions/dispatch_{_safe_target_fname(target)}_{int(datetime.datetime.utcnow().timestamp())}.json"
    write_json(fname, summary)
    _log.info("[dispatcher] Dispatch summary written to: %s", fname)
    return fname, summary

def parse_args():
    p = argparse.ArgumentParser(description="Sandbox dispatcher")
    p.add_argument("target", help="Target (url or host)")
    p.add_argument("--strategy", help="Comma separated PoC names", required=True)
    p.add_argument("--extra", help="Extra args forwarded to runner", default="")
    p.add_argument("--timeout", type=int, default=60)
    return p.parse_args()

if __name__ == "__main__":
    args = parse_args()
    strategy = [s.strip() for s in args.strategy.split(",") if s.strip()]
    run_dispatch(target=args.target, strategy=strategy, extra=args.extra, timeout=args.timeout)
