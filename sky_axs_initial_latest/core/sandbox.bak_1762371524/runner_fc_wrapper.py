#!/usr/bin/env python3
"""
Docker-hardened sandbox wrapper.
تعمد هذه النسخة إلى تشغيل runner Docker دائمًا (لا تحاول Firecracker).
تسمح الوسيط poc بتمرير مسار PoC إن وُجد.
"""
import logging, os
logger = logging.getLogger("sandbox_wrapper")
logger.setLevel(logging.INFO)
if not logger.handlers:
    import sys
    h = logging.StreamHandler(sys.stdout)
    h.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    logger.addHandler(h)

def run_in_sandbox(target, extra="", timeout=30, poc=None):
    """
    واجهة ثابتة: تحاول استدعاء core.sandbox.runner.run_in_sandbox (docker).
    Args:
      target (str): الهدف أو URL
      extra (str): اضافات سطر الأوامر مثل --poc=sql_injection
      timeout (int): زمن الانتظار
      poc (str): مسار PoC أو اسم (فقط لتمريره)
    Returns:
      whatever runner returns (dict / str) — أو يرفع Exception في حال فشل.
    """
    logger.info("Using Docker-hardened sandbox runner (forced). target=%s poc=%s extra=%s", target, poc, extra)
    try:
        # استدعاء runner الأصلي (Docker)
        from core.sandbox.runner import run_in_sandbox as docker_runner
    except Exception as e:
        logger.exception("Failed to import docker runner: %s", e)
        raise

    # استدعاء
    return docker_runner(target=target, extra=extra, timeout=timeout, poc=poc)
