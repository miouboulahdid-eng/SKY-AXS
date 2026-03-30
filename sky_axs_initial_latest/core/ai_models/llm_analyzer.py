import os
import json
import logging
from typing import Dict, Any

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")  # أرخص موديل

def analyze_endpoint_with_llm(endpoint_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    إرسال معلومات endpoint إلى LLM لتحليل احتمالية IDOR/BAC
    """
    if not OPENAI_API_KEY:
        logger.warning("OPENAI_API_KEY not set. Skipping LLM analysis.")
        return {"error": "OPENAI_API_KEY not set", "vulnerable": False, "confidence": 0}
    
    try:
        from openai import OpenAI
        client = OpenAI(api_key=OPENAI_API_KEY)
    except ImportError:
        logger.error("OpenAI library not installed")
        return {"error": "OpenAI library not installed"}

    system_prompt = """You are a security expert analyzing web application endpoints for vulnerabilities.
Your task is to detect potential IDOR (Insecure Direct Object Reference) and Broken Access Control (BAC) issues.
Return a JSON object with:
- vulnerable: boolean (true if you suspect a vulnerability)
- confidence: integer (0-100)
- explanation: string (why you think so)
- testing_steps: string (how to manually test using Burp Suite or curl)
"""

    user_prompt = f"""
Endpoint details:
- Method: {endpoint_data.get('method', 'GET')}
- URL: {endpoint_data.get('url', '')}
- Parameters: {json.dumps(endpoint_data.get('params', {}))}
- Headers: {json.dumps(endpoint_data.get('headers', {}))}
- Cookies: {json.dumps(endpoint_data.get('cookies', {}))}
- Response Body Snippet: {endpoint_data.get('response_body', '')[:1000]}

Analyze if this endpoint might be vulnerable to IDOR or broken access control.
"""

    try:
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.2,
            max_tokens=800,
            response_format={"type": "json_object"}
        )
        result_text = response.choices[0].message.content
        result = json.loads(result_text)
        logger.info(f"LLM analysis completed for {endpoint_data.get('url')}")
        return result
    except Exception as e:
        logger.error(f"LLM call failed: {e}")
        return {"error": str(e), "vulnerable": False, "confidence": 0}