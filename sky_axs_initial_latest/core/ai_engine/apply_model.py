import joblib, json, pandas as pd, sys

MODEL_PATH = "data/models/baseline_iforest.pkl"
model = joblib.load(MODEL_PATH)

def score_sample(feature_dict: dict):
    X = pd.DataFrame([feature_dict])
    s = model.decision_function(X)[0]
    return float(s)

if __name__ == "__main__":
    data = json.load(sys.stdin)
    print(json.dumps({"score": score_sample(data)}))
