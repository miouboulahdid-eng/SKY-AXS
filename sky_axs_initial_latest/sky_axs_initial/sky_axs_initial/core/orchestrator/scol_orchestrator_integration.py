#!/usr/bin/env python3
"""
Simple, robust orchestrator helper for SkyAXS.
- If rq/redis present it will enqueue to queue "sky".
- If not present it will simulate and print the job payload (safe).
Usage:
python3 scol_orchestrator_integration.py --target example.com [--extra "--dry-run"]
python3 scol_orchestrator_integration.py --list
"""
import argparse, os, sys, json
from datetime import datetime

# Try imports, but degrade gracefully if missing
HAVE_RQ = False
try:
    from rq import Queue
    from redis import Redis
HAVE_RQ = True
except Exception:
HAVE_RQ = False

def connect_redis(host='redis', port=6379, db=0, timeout=5):
return Redis(host=host, port=port, db=db, socket_connect_timeout=timeout)

def list_jobs(host='redis', port=6379):
if not HAVE_RQ:
print("RQ/Redis not available: cannot list jobs.")
return
r = connect_redis(host=host, port=port)
q = Queue('sky', connection=r)
jobs = q.jobs
if not jobs:
print("No jobs in queue 'sky'")
return
for j in jobs:
print(f"- id={j.id} func={getattr(j,'func_name',None)} status={j.get_status()} enqueued_at={j.enqueued_at}")

def enqueue_job(target, extra=None, host='redis', port=6379):
payload = {"target": target, "extra": extra or "", "queued_at": datetime.utcnow().isoformat()}
if HAVE_RQ:
r = connect_redis(host=host, port=port)
q = Queue('sky', connection=r)
try:
from core.worker.tasks import run_sky
job = q.enqueue(run_sky, target, extra or "", job_timeout=3600)
except Exception:
job = q.enqueue('core.worker.tasks.run_sky', target, extra or "", job_timeout=3600)
return job.id
else:
print("[SIMULATION] Would enqueue:", json.dumps(payload))
return "SIM-" + datetime.utcnow().strftime("%Y%m%d%H%M%S")

def main():
p = argparse.ArgumentParser()
p.add_argument('--target', '-t', help='Target (domain or IP)')
p.add_argument('--extra', '-e', help='Extra args to pass to sky.sh', default=None)
p.add_argument('--host', help='Redis host', default=os.environ.get('REDIS_HOST', 'redis'))
p.add_argument('--port', help='Redis port', default=int(os.environ.get('REDIS_PORT', '6379')))
p.add_argument('--list', action='store_true', help='List queued jobs')
args = p.parse_args()

if args.list:
list_jobs(host=args.host, port=args.port)
return

if not args.target:
print("ERROR: --target required", file=sys.stderr)
sys.exit(1)

jobid = enqueue_job(args.target, args.extra, host=args.host, port=args.port)
print(f"Enqueued job id={jobid} target={args.target} queued_at={datetime.utcnow().isoformat()}")

if __name__ == "__main__":
main()
