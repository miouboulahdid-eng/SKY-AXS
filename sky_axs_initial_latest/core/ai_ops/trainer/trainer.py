#!/usr/bin/env python3
import os, time, json
import redis
import pandas as pd
import numpy as np
from sklearn.ensemble import IsolationForest
from joblib import dump

REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
STREAM_KEY = os.getenv("STREAM_KEY", "metrics")
WINDOW_SEC = int(os.getenv("WINDOW_SEC", "1800"))  # 30 دقيقة
TRAIN_EVERY_SEC = int(os.getenv("TRAIN_EVERY_SEC", "300"))  # كل 5 دقائق
MODEL_DIR = os.getenv("MODEL_DIR", "/data/models")
MODEL_PATH = os.path.join(MODEL_DIR, "isoforest.pkl")

r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)

FEATURES = [
    "api_latency_ms","api_status","used_memory",
    "connected_clients","blocked_clients","ops","rq_queue_default_len"
]

def load_last_window():
    now = int(time.time()*1000)  # ms
    start = now - WINDOW_SEC*1000
    # XRANGE يعيد (id, map)
    records = r.xrange(STREAM_KEY, min=f"{start}-0", max="+", count=5000)
    rows = []
    for _id, m in records:
        try:
            row = {k: float(m.get(k, 0)) for k in FEATURES}
            row["ts"] = float(m.get("ts", 0))
            rows.append(row)
        except Exception:
            continue
    return pd.DataFrame(rows) if rows else pd.DataFrame(columns=FEATURES+["ts"])

def build_feature_vector(df):
    if df.empty:
        return None
    agg = {}
    for col in FEATURES:
        s = df[col].astype(float)
        agg[f"{col}_mean"] = s.mean()
        agg[f"{col}_std"]  = s.std(ddof=0) if len(s)>1 else 0.0
        agg[f"{col}_p95"]  = s.quantile(0.95)
    return pd.DataFrame([agg])

def train_and_save(X):
    if X is None or X.empty:
        print("[trainer] not enough data, skip", flush=True)
        return
    clf = IsolationForest(n_estimators=200, contamination="auto", random_state=42)
    clf.fit(X.values)
    os.makedirs(MODEL_DIR, exist_ok=True)
    dump({"model": clf, "columns": list(X.columns)}, MODEL_PATH)
    print(f"[trainer] model saved => {MODEL_PATH} with cols={X.columns.tolist()}", flush=True)

def main():
    print(f"[trainer] start window={WINDOW_SEC}s every={TRAIN_EVERY_SEC}s", flush=True)
    while True:
        df = load_last_window()
        X = build_feature_vector(df)
        train_and_save(X)
        time.sleep(TRAIN_EVERY_SEC)

if __name__ == "__main__":
    main()
