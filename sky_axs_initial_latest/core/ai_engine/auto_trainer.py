import os
import json
import logging
from core.ai_engine.axs_ai_engine import AxsAIEngine

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

RESULTS_DIR = "/app/data/results"

def auto_train_from_results():
    """تغذية النموذج بالنتائج الجديدة من Sandbox"""
    engine = AxsAIEngine()
    if not os.path.exists(RESULTS_DIR):
        logging.warning("📂 لا يوجد مجلد نتائج لتحليلها بعد.")
        return

    files = [f for f in os.listdir(RESULTS_DIR) if f.endswith(".json")]
    if not files:
        logging.info("✅ لا توجد نتائج جديدة للتدريب.")
        return

    logging.info(f"🔍 تم العثور على {len(files)} ملفات لتحليلها...")

    for filename in files:
        try:
            full_path = os.path.join(RESULTS_DIR, filename)
            with open(full_path, "r") as f:
                data = json.load(f)
                text_data = json.dumps(data)  # نحولها إلى نص للتحليل
                result = engine.analyze_target(text_data)
                logging.info(f"📈 تم تحليل {filename} - مستوى الخطورة: {result.get('risk')}")
        except Exception as e:
            logging.error(f"❌ خطأ أثناء تحليل {filename}: {e}")

    logging.info("✅ تمت عملية التغذية التلقائية للنموذج بنجاح.")
