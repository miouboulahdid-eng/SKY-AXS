import os, json, pandas as pd
from datetime import datetime

RESULTS_DIR = "data/results"
OUT_PATH = "data/models/features_all.csv"
os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)

records = []
for fn in os.listdir(RESULTS_DIR):
    if not fn.endswith(".json"): continue
    path = os.path.join(RESULTS_DIR, fn)
    try:
        with open(path) as f: data = json.load(f)
        out = data.get("output","")
        rec = {
            "job_id": data.get("job_id"),
            "target": data.get("target"),
            "poc": data.get("extra",""),
            "exit_code": data.get("exit_code",0),
            "len_out": len(out),
            "lines": out.count("\n"),
            "contains_error": int("error" in out.lower() or "exception" in out.lower()),
            "contains_vuln": int("vuln" in out.lower()),
            "duration": (
                datetime.fromisoformat(data.get("timestamp_end","2025-01-01T00:00:00")) -
                datetime.fromisoformat(data.get("timestamp","2025-01-01T00:00:00"))
            ).total_seconds(),
            "status_code": 0 if data.get("status")=="ok" else 1
        }
        records.append(rec)
    except Exception as e:
        print("skip", fn, e)

df = pd.DataFrame(records)
df.to_csv(OUT_PATH, index=False)
print(f"[+] Saved features: {OUT_PATH} ({len(df)} rows)")
