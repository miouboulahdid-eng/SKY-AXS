#!/usr/bin/env python3
import argparse, datetime
from rq import Queue
from redis import Redis
parser = argparse.ArgumentParser()
parser.add_argument("--target", "-t", required=True)
parser.add_argument("--extra", "-e", default="")
args = parser.parse_args()
r = Redis(host="redis", port=6379)
q = Queue("default", connection=r)
job = q.enqueue("core.worker.tasks.run_sky", args.target, args.extra)
print(f"Enqueued job id={job.id} target={args.target} queued_at={datetime.datetime.utcnow().isoformat()}")
