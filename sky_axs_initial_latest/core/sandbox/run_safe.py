#!/usr/bin/env python3
"""
safe runner helper for PoC execution inside docker container.
Provides run_poc_in_container(container, poc_path, target, extra, workdir)
that calls container.exec_run with argv list (no shell injection).
"""
import shlex
import logging

log = logging.getLogger("sandbox.run_safe")

def build_cmd(poc_filename, target, extra):
    """
    Build command list to run inside the container.
    poc_filename: e.g. "./run.sh" or "run.sh"
    target: target string
    extra: raw extra string (e.g. "--dry-run --poc=sql_injection")
    Returns list suitable for Docker SDK exec_run(cmd=list).
    """
    # normalize poc filename to be executed from workdir
    poc = poc_filename if poc_filename.startswith("./") else f"./{poc_filename}"
    args = [poc, target]
    if extra:
        # split safely (preserves quoted parts)
        extra_args = shlex.split(extra)
        args += extra_args
    return args

def run_poc_in_container(container, poc_filename, target, extra, workdir="/app/pocs"):
    """
    Execute the PoC inside a running container using exec_run with argv list.
    container: docker.models.containers.Container object
    poc_filename: filename inside workdir (e.g. run.sh)
    target, extra: strings
    workdir: directory inside container where PoC resides
    Returns exec result tuple (exit_code, output_bytes)
    """
    cmd = build_cmd(poc_filename, target, extra)
    log.info("Executing PoC inside container with argv list: %s", cmd)
    # Use exec_run with list form to avoid shell interpretation
    # we request demux=False to get combined output, and tty=False
    res = container.exec_run(cmd, workdir=workdir, demux=False)
    # res is ExecResult (exit_code, output) in docker-py
    return res
