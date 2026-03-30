import json
import re
from typing import List, Dict
from core.sandbox.runner import run_in_sandbox

SENSITIVE_KEYWORDS = ['admin', 'user', 'profile', 'account', 'order', 'payment', 'transfer', 'delete', 'update', 'api/v1/user', 'api/v2/user', 'internal']

def classify_sensitive(url: str, params: dict = None, response: str = "") -> bool:
    url_lower = url.lower()
    if any(kw in url_lower for kw in SENSITIVE_KEYWORDS):
        return True
    if response:
        resp_lower = response.lower()
        if any(kw in resp_lower for kw in ['email', 'password', 'credit_card', 'ssn']):
            return True
    return False

def collect_endpoints(target: str) -> List[Dict]:
    """
    تشغيل sky.sh في الوضع السلبي داخل sandbox واستخراج جميع الـ URLs
    """
    # تشغيل السكربت داخل sandbox
    path, result = run_in_sandbox(
        target=target,
        extra="--poc=passive",
        timeout=120
    )
    
    # النتيجة تحتوي على مخرجات الأمر (output) في result['output']
    output = result.get('output', '')
    
    # استخراج الـ URLs من المخرجات (كل سطر هو URL)
    urls = [line.strip() for line in output.split('\n') if line.strip() and line.startswith('http')]
    
    # تحويل كل URL إلى endpoint object
    endpoints = []
    for url in urls:
        # استخراج method (افتراضي GET)
        method = 'GET'
        # إذا كان URL يحتوي على علامة استفهام، يمكن اعتبار المعاملات
        params = {}
        if '?' in url:
            query = url.split('?', 1)[1]
            for pair in query.split('&'):
                if '=' in pair:
                    k, v = pair.split('=', 1)
                    params[k] = v
            url = url.split('?')[0]
        
        endpoints.append({
            "method": method,
            "url": url,
            "params": params,
            "headers": {},
            "cookies": {},
            "response_body": "",  # لا توجد استجابة في هذه المرحلة
            "status_code": 0,
            "content_type": "",
            "sensitive": classify_sensitive(url, params)
        })
    
    return endpoints