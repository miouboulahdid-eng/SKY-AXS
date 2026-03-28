#!/usr/bin/env python3
# path: core/ui/cmd_client.py
# Simple command client: sends commands to Redis stream or drops JSON to commands dir

import argparse, json, os, time

REDIS_HOST = os.environ.get("REDIS_HOST", "redis")
REDIS_PORT = int(os.environ.get("REDIS_PORT", "6379"))
REDIS_STREAM = "axs_commands"
FALLBACK_DIR = "data/commands"

def send_redis(cmd, payload=""):
    try:
        import redis
        r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, socket_timeout=2)
        r.xadd(REDIS_STREAM, {"cmd": cmd, "payload": payload})
        print("Sent via Redis.")
        return
    except Exception as e:
        print("Redis send failed:", e)
    # fallback
    send_file(cmd, payload)

def send_file(cmd, payload=""):
    os.makedirs(FALLBACK_DIR, exist_ok=True)
    fname = f"{int(time.time())}_{os.getpid()}.json"
    path = os.path.join(FALLBACK_DIR, fname)
    with open(path, "w") as f:
        json.dump({"cmd": cmd, "payload": payload}, f)
    print("Wrote fallback command file:", path)

def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmdname")
    runp = sub.add_parser("run_poc")
    runp.add_argument("--target", required=True)
    runp.add_argument("--strategy", required=True)
    runp.add_argument("--extra", default="")

    restart = sub.add_parser("restart")
    restart.add_argument("container")

    logs = sub.add_parser("logs")
    logs.add_argument("container")
    logs.add_argument("--lines", default="200")

    stop = sub.add_parser("stop")
    stop.add_argument("container")

    args = p.parse_args()
    if not args.cmdname:
        p.print_help(); return

    if args.cmdname == "run_poc":
        cmd = f"run_poc --target {args.target} --strategy {args.strategy} --extra {repr(args.extra)}"
        send_redis(cmd)
    elif args.cmdname == "restart":
        send_redis(f"restart {args.container}")
    elif args.cmdname == "logs":
        send_redis(f"logs {args.container} {args.lines}")
    elif args.cmdname == "stop":
        send_redis(f"stop {args.container}")

if __name__ == "__main__":
    main()
