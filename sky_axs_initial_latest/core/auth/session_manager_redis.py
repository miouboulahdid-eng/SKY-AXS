import json
import redis
import requests
from typing import Optional, Dict

class RedisSessionManager:
    def __init__(self, redis_client: redis.Redis, prefix: str = "session:"):
        self.redis = redis_client
        self.prefix = prefix

    def _make_key(self, target: str, username: str) -> str:
        return f"{self.prefix}{target}:{username}"

    def login(self, target: str, username: str, password: str, login_endpoint: str = "/rest/user/login") -> bool:
        key = self._make_key(target, username)
        base_url = f"http://{target}"
        session = requests.Session()
        try:
            resp = session.post(
                f"{base_url}{login_endpoint}",
                json={"email": username, "password": password},
                timeout=10
            )
            if resp.status_code == 200:
                cookies = session.cookies.get_dict()
                self.redis.set(key, json.dumps(cookies))
                return True
        except Exception:
            pass
        return False

    def get_session(self, target: str, username: str, password: str = None) -> Optional[requests.Session]:
        key = self._make_key(target, username)
        cookies_json = self.redis.get(key)
        session = requests.Session()
        if cookies_json:
            cookies = json.loads(cookies_json)
            session.cookies.update(cookies)
            # التحقق من صلاحية الجلسة (اختياري)
            # يمكن إضافة طلب تجريبي
            return session
        elif password is not None:
            if self.login(target, username, password):
                cookies_json = self.redis.get(key)
                if cookies_json:
                    session.cookies.update(json.loads(cookies_json))
                    return session
        return None