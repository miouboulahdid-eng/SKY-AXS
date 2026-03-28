#!/usr/bin/env python3
import os, json
from core.sandbox.runner import run_in_sandbox

# مثال: تشغيل PoC الموجود في core/sandbox/pocs/sql_injection/run.sh
target = "example.com"
extra = "--poc=sql_injection"   # <-- غيّر إلى اسم المجلد داخل core/sandbox/pocs
path, res = run_in_sandbox(target, extra, timeout=30)
print("Result JSON:", path)
print(json.dumps(res, indent=2))
