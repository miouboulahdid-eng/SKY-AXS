import os
import json
import datetime
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

def sandbox_task_run_in_sandbox(target: str, extra: str = "", **kwargs):
    """
    مهمة تشغيل الهدف داخل sandbox وهمي (stub).
    تكتب النتيجة في /app/data/results مع timestamp.
    """
    timestamp = datetime.datetime.utcnow().isoformat()
    result = {
        "target": target,
        "extra": extra,
        "status": "OK",
        "timestamp": timestamp
    }

    result_dir = "/app/data/results"
    os.makedirs(result_dir, exist_ok=True)

    safe_name = target.replace("://", "_").replace("/", "_").replace(".", "_")
    result_path = os.path.join(result_dir, f"{safe_name}_{int(datetime.datetime.now().timestamp())}.json")

    # Log full path to confirm writing location
    logging.info(f"[*] Writing sandbox result file to: {result_path}")

    with open(result_path, "w") as f:
        json.dump(result, f, indent=2)

    return {"status": "success", "path": result_path, "result": result}


   # تدريب تلقائي بعد كل تنفيذ Sandbox
try:
    from core.ai_engine.auto_trainer import auto_train_from_results
    auto_train_from_results()
except Exception as e:
    import logging
    logging.error(f"❌ فشل التدريب التلقائي: {e}")
