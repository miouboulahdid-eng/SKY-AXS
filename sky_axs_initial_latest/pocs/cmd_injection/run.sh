#!/bin/sh
TARGET="${AXS_TARGET:-$1}"
EXTRA="${AXS_EXTRA:-$2}"
echo "PoC: Command Injection (SIMULATED - echo only)"
echo "Target: $TARGET"
sleep 1
# emulate safe payload
echo "Executed: echo hello (SIMULATED)"
exit 0
