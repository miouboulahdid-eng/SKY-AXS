#!/usr/bin/env python3
import os
import time
import datetime
from tenacity import retry, stop_after_attempt, wait_fixed
import docker

WATCH = [x.strip() for x in os.environ.get("WATCH", "").split(",") if x.strip()]
INTERVAL = int(os.environ.get("INTERVAL", "10"))
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
MAX_UNHEALTHY = int(os.environ.get("MAX_UNHEALTHY", "3"))

def log(*a, level="INFO"):
    if level == "DEBUG" and LOG_LEVEL != "DEBUG":
        return
    ts = datetime.datetime.utcnow().isoformat() + "Z"
    msg = " ".join(str(x) for x in a)
    print(f"[{ts}] [{level}] {msg}", flush=True)

@retry(stop=stop_after_attempt(5), wait=wait_fixed(2))
def get_client():
    docker_host = os.environ.get("DOCKER_HOST", "unix:///var/run/docker.sock")
    try:
        if docker_host.startswith("unix://"):
            client = docker.DockerClient(base_url=docker_host)
        else:
            client = docker.from_env()
        client.ping()
        log("Docker client connected.", level="INFO")
        return client
    except Exception as e:
        log(f"Failed to connect to Docker: {e}", level="ERROR")
        raise

def should_watch(name: str) -> bool:
    if not WATCH:
        return True
    for w in WATCH:
        if w in name:
            return True
    return False

def main():
    unhealthy_counts = {}
    cli = get_client()
    log("Healer started.", "interval=", INTERVAL, "watch=", ",".join(WATCH) or "<ALL>")
    while True:
        try:
            for c in cli.containers.list(all=True):
                name = c.name
                if not should_watch(name):
                    continue
                try:
                    c.reload()
                except Exception as e:
                    log("reload failed for", name, ":", e, level="DEBUG")
                    continue

                state = c.attrs.get("State", {})
                running = state.get("Running", False)
                health = state.get("Health", {})
                health_status = health.get("Status")

                if not running:
                    log("Container not running -> restarting:", name, level="WARN")
                    try:
                        c.restart()
                        log("Restarted:", name)
                        unhealthy_counts[name] = 0
                    except Exception as e:
                        log("Restart failed for", name, ":", e, level="ERROR")
                    continue

                if health_status == "unhealthy":
                    cnt = unhealthy_counts.get(name, 0) + 1
                    unhealthy_counts[name] = cnt
                    log(f"{name} health={health_status} (strike {cnt}/{MAX_UNHEALTHY})", level="WARN")
                    if cnt >= MAX_UNHEALTHY:
                        log("Health strikes exceeded -> restarting:", name, level="WARN")
                        try:
                            c.restart()
                            log("Restarted:", name)
                            unhealthy_counts[name] = 0
                        except Exception as e:
                            log("Restart failed for", name, ":", e, level="ERROR")
                else:
                    if unhealthy_counts.get(name):
                        unhealthy_counts[name] = 0
                        log(name, "is healthy again", level="INFO")

                log(f"{name} running={running} health={health_status or 'n/a'}", level="DEBUG")
        except Exception as e:
            log("Loop error:", e, level="ERROR")

        time.sleep(INTERVAL)

if __name__ == "__main__":
    main()
