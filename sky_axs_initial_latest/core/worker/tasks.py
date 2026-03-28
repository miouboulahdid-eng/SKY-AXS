import time, json

def run_job(job_data):
target = job_data.get("target")
ai = job_data.get("ai", {})
decision = ai.get("decision", "light_scan")

print(f"[Worker] Running job for {target} - Mode: {decision}")
time.sleep(2)

result = {
"target": target,
"decision": decision,
"completed": True,
"timestamp": time.time()
}

print(json.dumps(result, indent=2))
return result
