#!/usr/bin/env python3
"""
Sandbox dispatcher - runs a list of PoCs (strategy) using the sandbox runner.
This file is robust about imports: tries core.sandbox.runner first, then sandbox.runner.
Writes individual results to data/results and a dispatch summary to data/decisions.
"""
import sys
import os
import argparse
import json
import datetime
import logging
from typing import List

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# --- ensure project root in sys.path so 'core' package is importable inside containers or CLI runs ---
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# --- try imports with fallback ---
try:
    from core.sandbox.runner import SandboxRunner
except Exception:
    try:
        from sandbox.runner import SandboxRunner
    except Exception as e:
        logging.exception("Failed to import sandbox runner (core.sandbox.runner nor sandbox.runner)")
        raise

def ensure_dirs():
    os.makedirs("data/results", exist_ok=True)
    os.makedirs("data/decisions", exist_ok=True)

def write_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2, default=str)

def run_dispatch(target: str, strategy: List[str], extra: str = "", timeout: int = 60):
    ensure_dirs()
    started_at = datetime.datetime.utcnow().isoformat()
    dispatch_results = []

    runner = SandboxRunner()

    for poc in strategy:
        logging.info(f"[dispatcher] Running PoC: {poc}")
        poc_extra = extra
        if "--poc=" not in poc_extra and poc:
            if poc_extra.strip():
                poc_extra = f"{poc_extra} --poc={poc}"
            else:
                poc_extra = f"--poc={poc}"

        try:
            path, result = runner.run_in_sandbox(target=target, extra=poc_extra, timeout=timeout)
            logging.info(f"[dispatcher] PoC {poc} finished: path={path}")
            dispatch_results.append({
                "poc": poc,
                "status": "ok",
                "result": result
            })
        except Exception as e:
            logging.exception(f"[dispatcher] ERROR running {poc}")
            dispatch_results.append({
                "poc": poc,
                "status": "error",
                "error": str(e)
            })

    ended_at = datetime.datetime.utcnow().isoformat()
    summary = {
        "target": target,
        "strategy": strategy,
        "extra": extra,
        "started_at": started_at,
        "ended_at": ended_at,
        "results": dispatch_results
    }

    fname = f"data/decisions/dispatch_{target.replace('://','_').replace('/','_')}_{int(datetime.datetime.utcnow().timestamp())}.json"
    write_json(fname, summary)
    logging.info(f"[dispatcher] Dispatch summary written to: {fname}")
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
