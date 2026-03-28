#!/usr/bin/env bash
set -euo pipefail

# helper: create /opt/firecracker and explain requirements.
# You must supply:
#  - vmlinux.bin (kernel image compatible with Firecracker)
#  - rootfs.ext4 (root filesystem image with an autorun/ssh agent if you need to run PoCs inside)
#
# Example (manual) steps (host must have debootstrap or prebuilt rootfs):
# 1) mkdir -p /opt/firecracker
# 2) copy vmlinux.bin -> /opt/firecracker/vmlinux.bin
# 3) create ext4 rootfs (example using a prepared file) -> /opt/firecracker/rootfs.ext4
#
# Quick notes:
# - rootfs must contain an init that will run PoC scripts automatically or an SSH server for remote exec.
# - Keep VM network disabled for safer PoC runs; enable only if you know the risks.
# - Paths are used by firecracker_runner.py by default.
#
echo "[*] Creating directory /opt/firecracker if missing..."
sudo mkdir -p /opt/firecracker
sudo chown $(id -u):$(id -g) /opt/firecracker
echo "Place your vmlinux.bin and rootfs.ext4 into /opt/firecracker"
echo "Examples (not included):"
echo " - Get a kernel from kernel-images repo or build a vmlinux"
echo " - Use a prebuilt rootfs with cloud-init or SSH"
echo ""
echo "After placing files, test with:"
echo " PYTHONPATH=. python3 -c \"from core.sandbox.runner_fc_wrapper import run_in_sandbox; print(run_in_sandbox('test', extra='--dry-run', timeout=10))\""
