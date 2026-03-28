#!/bin/sh
TARGET="${AXS_TARGET:-$1}"
EXTRA="${AXS_EXTRA:-$2}"
echo "PoC: SSRF (SIMULATED)"
echo "Target: $TARGET"
sleep 1
echo "Result: SSRF_POSSIBLE_SIMULATED"
exit 0
