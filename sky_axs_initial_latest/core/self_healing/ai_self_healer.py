#!/usr/bin/env python3
"""
Simple AI-ish Self-Healer (rule-based) - consumes stream:sandbox_results and acts.

Behaviour:
 - Blocks on stream (XREAD) and processes new events.
 - If event.status == 'vulnerable' and confidence >= HEAL_CONFIDENCE -> perform action
 - Default action: restart worker container (docker) or run configured command
 - Safe mode: set SELF_HEALER_DRYRUN=1 to only log (no action)
 - Publishes alerts to stream:stream:alerts
"""
import os, time, json, logging, traceback, subprocess
from decimal import Decimal

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
_log = logging.getLogger("self_healer")

try:
    import redis
except Exception:
    redis = None

# docker SDK optional
try:
    import docker
    DOCKER_SDK = True
except Exception:
    DOCKER_SDK = False

REDIS_HOST = os.environ.get("REDIS_HOST", "redis")
REDIS_PORT = int(os.environ.get("REDIS_PORT", "6379"))
REDIS_DB = int(os.environ.get("REDIS_DB", "0"))

STREAM_NAME = os.environ.get("SH_STREAM_NAME", "stream:sandbox_results")
ALERT_STREAM = os.environ.get("SH_ALERT_STREAM", "stream:alerts")
HEAL_CONFIDENCE = float(os.environ.get("HEAL_CONFIDENCE", "0.8"))
DRYRUN = os.environ.get("SELF_HEALER_DRYRUN", "1") == "1"
RESTART_CMD = os.environ.get("SELF_HEALER_RESTART_CMD", "docker restart sky_axs_initial-worker")
# allow multiple restarts in window guard
RESTART_WINDOW = int(os.environ.get("SELF_HEALER_WINDOW_SEC", "300"))
LAST_RESTART_AT = 0

if redis is None:
    _log.error("redis package not available; self-healer cannot run.")
    raise SystemExit(2)

r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB, socket_connect_timeout=5)

def publish_alert(payload: dict):
    try:
        r.xadd(ALERT_STREAM, payload)
        _log.info("Published alert to %s", ALERT_STREAM)
    except Exception as e:
        _log.warning("Failed publish alert: %s", e)

def perform_action_for_event(event: dict):
    global LAST_RESTART_AT
    status = event.get("status")
    try:
        confidence = float(event.get("confidence") or 0.0)
    except Exception:
        confidence = 0.0
    target = event.get("target")
    poc = event.get("poc")

    _log.info("Decision check: status=%s confidence=%s target=%s poc=%s", status, confidence, target, poc)

    if status == "vulnerable" and confidence >= HEAL_CONFIDENCE:
        # rate-limit restarts
        now = time.time()
        if now - LAST_RESTART_AT < RESTART_WINDOW:
            _log.info("Restart recently performed (within window). Skipping actual restart; publishing alert.")
            publish_alert({"target": target or "", "poc": poc or "", "action": "skipped_restart", "confidence": str(confidence)})
            return

        if DRYRUN:
            _log.info("(dry-run) Would perform restart action: %s", RESTART_CMD)
            publish_alert({"target": target or "", "poc": poc or "", "action": "dryrun_restart", "confidence": str(confidence)})
            return

        # perform actual restart (try docker SDK first)
        try:
            if DOCKER_SDK:
                client = docker.from_env()
                # try to find worker container name; default known
                name = os.environ.get("SELF_HEALER_TARGET_CONTAINER", "sky_axs_initial-worker")
                _log.info("Attempting docker SDK restart for %s", name)
                c = client.containers.get(name)
                c.restart(timeout=10)
                _log.info("Restarted container via docker SDK: %s", name)
                publish_alert({"target": target or "", "poc": poc or "", "action": "restart", "method": "docker_sdk", "container": name, "confidence": str(confidence)})
            else:
                _log.info("Running shell restart cmd: %s", RESTART_CMD)
                subprocess.run(RESTART_CMD, shell=True, check=False)
                publish_alert({"target": target or "", "poc": poc or "", "action": "restart", "method": "shell", "cmd": RESTART_CMD, "confidence": str(confidence)})
            LAST_RESTART_AT = time.time()
        except Exception as e:
            _log.error("Failed to perform restart: %s", e)
            publish_alert({"target": target or "", "poc": poc or "", "action": "restart_failed", "error": str(e), "confidence": str(confidence)})
    else:
        _log.debug("No action required for this event.")

def parse_event_data(raw_fields):
    # redis returns bytes; decode
    return {k.decode(): v.decode() for k, v in raw_fields.items()}

def run_loop():
    last_id = "0-0"  # start from earliest; you may set '$' to get only new
    # to avoid processing historic on each restart, set last_id to '$' or store offset in file/db
    if os.path.exists("data/healer/last_stream_id.txt"):
        try:
            last_id = open("data/healer/last_stream_id.txt").read().strip() or "0-0"
        except:
            last_id = "0-0"
    _log.info("Starting self-healer stream consumer from id=%s", last_id)

    while True:
        try:
            res = r.xread({STREAM_NAME: last_id}, block=20000, count=5)
            if not res:
                continue
            for stream, events in res:
                for ev_id, fields in events:
                    last_id = ev_id.decode()
                    try:
                        data = parse_event_data(fields)
                        event = {
                            "target": data.get("target"),
                            "poc": data.get("poc"),
                            "status": data.get("status"),
                            "confidence": float(data.get("confidence") or 0.0),
                            "timestamp": data.get("timestamp")
                        }
                        _log.info("Received stream event id=%s %s", last_id, event)
                        perform_action_for_event(event)
                    except Exception as e:
                        _log.error("Error handling event %s: %s", ev_id, e)
                    # persist last processed id
                    try:
                        with open("data/healer/last_stream_id.txt","w") as f:
                            f.write(last_id)
                    except:
                        pass
        except Exception as e:
            _log.error("Stream read error: %s", e)
            time.sleep(2)

if __name__ == "__main__":
    run_loop()
