import pandas as pd, joblib, os
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import RobustScaler
from sklearn.pipeline import Pipeline

IN_PATH = "data/models/features_all.csv"
OUT_MODEL = "data/models/baseline_iforest.pkl"
os.makedirs(os.path.dirname(OUT_MODEL), exist_ok=True)

df = pd.read_csv(IN_PATH)
X = df.drop(columns=["job_id","target","poc"], errors="ignore").fillna(0)

pipe = Pipeline([
    ("scaler", RobustScaler()),
    ("clf", IsolationForest(n_estimators=200, contamination=0.02, random_state=42))
])
pipe.fit(X)
joblib.dump(pipe, OUT_MODEL)
print(f"[+] Model saved to {OUT_MODEL} with {len(X)} samples")
