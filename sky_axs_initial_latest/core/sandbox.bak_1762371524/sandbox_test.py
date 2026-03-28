# quick test runner for the hardened sandbox
from core.sandbox.runner import run_in_sandbox
import json, sys

target = "example.com"
cmd = 'echo "POC: started for {t}"; uname -a; echo "done"'.format(t=target)
path, res = run_in_sandbox(target, cmd, timeout=15)
print("Result JSON:", path)
print(json.dumps(res, indent=2))
