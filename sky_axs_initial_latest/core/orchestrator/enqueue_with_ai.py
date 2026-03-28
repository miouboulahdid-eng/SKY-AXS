import sys
from core.orchestrator.ai_bridge import smart_decision
from redis import Redis
from rq import Queue
import uuid, json
from datetime import datetime

def main():
if len(sys.argv) < 2:
print("Usage: enqueue_with_ai.py <target>")
sys.exit(1)

target = sys.argv[1]
ai_result = smart_decision(target)
job_data = {
"id": str(uuid.uuid4()),
"target": target,
"ai": ai_result,
"created_at": datetime.utcnow().isoformat()
}

r = Redis(host="redis", port=6379)
q = Queue("default", connection=r)
job = q.enqueue("core.worker.tasks.run_job", job_data)
print(f"[+] Job queued {job.id} | target={target} | decision={ai_result['decision']}")

if __name__ == "__main__":
main()
