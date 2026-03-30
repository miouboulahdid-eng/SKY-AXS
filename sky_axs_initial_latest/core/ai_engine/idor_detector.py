import json
import logging
import requests
from typing import Optional
from core.db.database import get_connection
from core.auth.session_manager_redis import RedisSessionManager

logger = logging.getLogger(__name__)

def test_idor(endpoint: dict, session: Optional[requests.Session] = None) -> dict:
    target = endpoint['target']
    url = endpoint['url']
    params = json.loads(endpoint['params'])

    # البحث عن معامل رقمي
    id_param = None
    for k, v in params.items():
        if isinstance(v, str) and v.isdigit():
            id_param = k
            break

    if not id_param:
        return {"vulnerable": False, "reason": "No numeric ID parameter found"}

    original_id = params[id_param]
    new_id = str(int(original_id) + 1)
    modified_params = params.copy()
    modified_params[id_param] = new_id

    # بناء الـ URL الكامل
    base_url = f"http://{target}"
    # نستخرج المسار من الـ url (نزيل base_url إن وجد)
    if url.startswith(base_url):
        path = url[len(base_url):]
    else:
        path = url
    if not path:
        path = "/"
    full_url = f"{base_url}{path}"

    try:
        if session:
            # استخدام الجلسة العادية مع الـ URL الكامل
            resp = session.get(full_url, params=modified_params)
        else:
            resp = requests.get(full_url, params=modified_params, timeout=10)
        output = resp.text
    except Exception as e:
        return {"vulnerable": False, "reason": f"Request failed: {e}"}

    # تحليل بسيط: إذا عادت البيانات تحتوي على user أو email
    if output and ('user' in output.lower() or 'email' in output.lower()):
        return {
            "vulnerable": True,
            "reason": f"Changing {id_param} from {original_id} to {new_id} returned data",
            "original_id": original_id,
            "new_id": new_id,
            "response_snippet": output[:200]
        }
    return {"vulnerable": False, "reason": "No difference or no data returned"}

def detect_idor(target: str, session_manager: RedisSessionManager, username: str = None, password: str = None):
    session = None
    if username and password:
        session = session_manager.get_session(target, username, password)
        if session is None:
            logger.warning(f"Could not obtain session for {username} on {target}")
        else:
            logger.info(f"Session obtained for {username} on {target}")

    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM endpoints WHERE target=? AND sensitive=1",
            (target,)
        ).fetchall()

    results = []
    for row in rows:
        ep = dict(row)
        logger.info(f"Testing IDOR on {ep['url']}")
        res = test_idor(ep, session)
        results.append({
            "endpoint_id": ep['id'],
            "url": ep['url'],
            "params": ep['params'],
            "vulnerable": res.get('vulnerable', False),
            "details": res
        })
    return results