import json, joblib, pandas as pd
from pathlib import Path

MODEL_PATH = "data/models/baseline_iforest.pkl"
RESULTS_DIR = Path("data/results")
OUT_PATH = Path("data/models/latest_analysis.json")
model = joblib.load(MODEL_PATH)

records = []
for f in RESULTS_DIR.glob("*.json"):
    j = json.loads(f.read_text())
    out = j.get("output","").lower()
    feat = {
        "len_out": len(out),
        "lines": out.count("\n"),  # added to match training features
        "contains_error": int("error" in out or "exception" in out),
        "contains_vuln": int("vuln" in out),
        "duration": 0,
        "exit_code": j.get("exit_code",0),
        "status_code": 0 if j.get("status")=="ok" else 1  # added to match training features
    }
    feat["score"] = float(model.decision_function(pd.DataFrame([feat]))[0])
    feat["job_id"] = j.get("job_id")
    feat["target"] = j.get("target")
    records.append(feat)

OUT_PATH.write_text(json.dumps(records, indent=2))
print(f"[+] Analysis written to {OUT_PATH}")
