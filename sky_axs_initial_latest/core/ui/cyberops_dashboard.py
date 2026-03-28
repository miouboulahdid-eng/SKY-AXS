#!/usr/bin/env python3
# path: core/ui/cyberops_dashboard.py
# AXS CyberOps Dashboard — Interactive Terminal Interface with command channel (Redis/file)

from rich.live import Live
from rich.table import Table
from rich.panel import Panel
from rich.console import Console
from rich.text import Text
from rich.layout import Layout
from rich.align import Align
from rich import box
import os, time, json, subprocess, datetime, traceback, threading

console = Console()
REFRESH_INTERVAL = 2.0
TITLE = "AXS SECURITY ENGINE v3.1.4"
SUBTITLE = "CyberOps Command Dashboard"

# ------ command channel config ------
USE_REDIS = True
REDIS_HOST = os.environ.get("REDIS_HOST", "redis")
REDIS_PORT = int(os.environ.get("REDIS_PORT", "6379"))
REDIS_STREAM = "axs_commands"          # stream where cmd_client will XADD
FALLBACK_CMD_DIR = "data/commands"     # fallback: drop JSON files here

# ==== helpers ====
def safe_run(cmd, timeout=6):
    try:
        out = subprocess.check_output(cmd, shell=True, stderr=subprocess.STDOUT, timeout=timeout)
        return out.decode().strip()
    except subprocess.CalledProcessError as e:
        return f"ERR:{e.returncode} {e.output.decode().strip()}"
    except Exception:
        return None

def get_system_stats():
    try:
        import psutil
        cpu = psutil.cpu_percent()
        mem = psutil.virtual_memory().percent
        uptime = int(time.time() - psutil.boot_time())
        return cpu, mem, uptime
    except Exception:
        return None, None, None

def get_redis_status():
    try:
        import redis
        r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, socket_connect_timeout=1)
        if r.ping():
            return "Online ✅"
    except Exception:
        pass
    return "Offline ⚠️"

def get_docker_summary():
    out = safe_run("docker ps --format '{{.Names}}\t{{.Image}}\t{{.Status}}'")
    if not out:
        return []
    return [x.split("\t") for x in out.splitlines()]

def get_latest_sandbox_results():
    results_dir = "/app/data/results"
    if not os.path.exists(results_dir):
        results_dir = "data/results"
    if not os.path.exists(results_dir):
        return []
    files = sorted(
        [os.path.join(results_dir, f) for f in os.listdir(results_dir) if f.endswith(".json")],
        key=os.path.getmtime, reverse=True
    )[:4]
    out = []
    for f in files:
        try:
            data = json.load(open(f))
            out.append((os.path.basename(f), data.get("status", "?")))
        except Exception:
            out.append((os.path.basename(f), "ERR"))
    return out

# ---------- command executor ----------
class CommandExecutor(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True)
        self._stop = False
        # Redis client will be created lazily
        self.redis = None

    def stop(self):
        self._stop = True

    def run(self):
        # Ensure fallback dir exists
        os.makedirs(FALLBACK_CMD_DIR, exist_ok=True)
        while not self._stop:
            try:
                # Prefer Redis if enabled
                if USE_REDIS:
                    try:
                        import redis
                        if self.redis is None:
                            self.redis = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, socket_timeout=1)
                        # XREAD last entries (block 0 means no block), we will use XRANGE from - to +
                        items = self.redis.xrange(REDIS_STREAM, min='-', max='+', count=10)
                        # items is list of (id, {b'k': b'v', ...})
                        for item_id, fields in items:
                            # mark executed by deleting or moving to processed stream (best-effort)
                            try:
                                cmd = fields.get(b'cmd', b'').decode()
                                payload = fields.get(b'payload', b'').decode()
                            except Exception:
                                cmd = ""
                                payload = ""
                            if cmd:
                                self._handle_cmd(cmd, payload)
                                try:
                                    # trim stream (optional): create a processed stream or delete id (XDEL)
                                    self.redis.xdel(REDIS_STREAM, item_id)
                                except Exception:
                                    pass
                    except Exception:
                        # Redis not available; fallback to file-based queue
                        self.redis = None
                        self._file_fallback()
                else:
                    self._file_fallback()
            except Exception:
                pass
            time.sleep(1.0)

    def _file_fallback(self):
        # read files placed in FALLBACK_CMD_DIR
        for fn in sorted(os.listdir(FALLBACK_CMD_DIR)):
            if not fn.endswith(".json"):
                continue
            path = os.path.join(FALLBACK_CMD_DIR, fn)
            try:
                data = json.load(open(path))
                cmd = data.get("cmd")
                payload = data.get("payload", "")
                if cmd:
                    self._handle_cmd(cmd, payload)
            except Exception:
                pass
            try:
                os.remove(path)
            except Exception:
                pass

    def _handle_cmd(self, cmd, payload):
        console.log(f"[bold yellow]EXEC CMD:[/bold yellow] {cmd} {payload}")
        # parse simple commands:
        # run_poc --target URL --strategy s1,s2 --extra "...", restart container NAME, logs NAME 100
        try:
            parts = cmd.split()
            op = parts[0]
            if op == "run_poc":
                # payload contains JSON or we parse args from cmd
                # example: run_poc --target https://example.com --strategy sql_injection,xss_reflected --extra "--dry-run"
                import shlex, subprocess, json
                args = shlex.split(cmd)
                target = None; strategy = None; extra = ""
                for i, a in enumerate(args):
                    if a == "--target" and i+1 < len(args):
                        target = args[i+1]
                    if a == "--strategy" and i+1 < len(args):
                        strategy = args[i+1]
                    if a == "--extra" and i+1 < len(args):
                        extra = args[i+1]
                if target and strategy:
                    # call dispatcher inside container or local: prefer docker exec if orchestrator container exists
                    # try running inside orchestrator container
                    try:
                        chk = safe_run("docker ps --format '{{.Names}}' | grep -w sky_axs_initial-orchestrator || true")
                        if chk:
                            # docker exec orchestrator python3 /app/core/sandbox/dispatcher.py ...
                            cmdline = (
                                f"docker exec -i sky_axs_initial-orchestrator "
                                f"python3 /app/core/sandbox/dispatcher.py {shlex.quote(target)} --strategy={shlex.quote(strategy)} --extra={shlex.quote(extra)} --timeout=120"
                            )
                        else:
                            cmdline = f"python3 core/sandbox/dispatcher.py {shlex.quote(target)} --strategy={shlex.quote(strategy)} --extra={shlex.quote(extra)} --timeout=120"
                        out = safe_run(cmdline, timeout=180)
                        console.log(f"[green]run_poc output:[/green] {out}")
                    except Exception as e:
                        console.log_exception()
                else:
                    console.log("[red]run_poc missing target/strategy[/red]")
            elif op in ("restart", "reboot"):
                # restart <container_name>
                if len(parts) >= 2:
                    cname = parts[1]
                    out = safe_run(f"docker restart {shlex_quote(cname)}")
                    console.log(f"[green]restart result:[/green] {out}")
            elif op == "logs":
                # logs <container> [lines]
                if len(parts) >= 2:
                    cname = parts[1]
                    lines = parts[2] if len(parts) >= 3 else "200"
                    out = safe_run(f"docker logs --tail {lines} {shlex_quote(cname)}")
                    # write to data/ui_last_logs.txt for viewing
                    with open("data/ui_last_logs.txt", "w") as f:
                        f.write(out or "")
                    console.log(f"[green]saved logs to data/ui_last_logs.txt[/green]")
            elif op == "stop":
                if len(parts) >= 2:
                    cname = parts[1]
                    out = safe_run(f"docker stop {shlex_quote(cname)}")
                    console.log(f"[green]stop result:[/green] {out}")
            else:
                console.log(f"[magenta]unknown cmd:[/magenta] {cmd}")
        except Exception:
            console.log_exception()

# small helper to safely shell-quote a token
def shlex_quote(s):
    import shlex
    return shlex.quote(s)

# ---------- build UI ------
def build_dashboard():
    cpu, mem, uptime = get_system_stats()
    redis_state = get_redis_status()
    dockers = get_docker_summary()
    sandbox = get_latest_sandbox_results()

    sys_table = Table.grid(padding=1)
    sys_table.add_column("Metric", justify="left", style="cyan")
    sys_table.add_column("Value", justify="right", style="bold green")
    sys_table.add_row("CPU Usage", f"{cpu or '?'}%")
    sys_table.add_row("Memory", f"{mem or '?'}%")
    sys_table.add_row("Uptime", f"{uptime or '?'}s")
    sys_table.add_row("Redis", redis_state)
    system_panel = Panel(sys_table, title="SYSTEM STATUS", border_style="bright_blue", padding=(1,2))

    dock_table = Table(title="ACTIVE CONTAINERS", box=box.SQUARE, show_lines=True)
    dock_table.add_column("Name", style="yellow")
    dock_table.add_column("Image", style="green")
    dock_table.add_column("Status", style="cyan")
    if dockers:
        for row in dockers:
            if len(row) == 3:
                name,image,status = row
            else:
                name = row[0]; image = row[1] if len(row)>1 else ""; status = row[-1]
            dock_table.add_row(name, image, status)
    else:
        dock_table.add_row("—", "—", "No containers running")
    docker_panel = Panel(dock_table, border_style="green")

    sb_table = Table(title="LATEST SANDBOX RESULTS", box=box.SIMPLE)
    sb_table.add_column("File", style="cyan")
    sb_table.add_column("Status", style="bold magenta")
    if sandbox:
        for fn, st in sandbox:
            sb_table.add_row(fn, str(st))
    else:
        sb_table.add_row("No results yet", "-")
    sandbox_panel = Panel(sb_table, border_style="magenta")

    layout = Layout()
    layout.split_column(
        Layout(name="header", size=3),
        Layout(name="body", ratio=1),
        Layout(name="footer", size=2)
    )
    layout["body"].split_row(
        Layout(system_panel, ratio=1),
        Layout(docker_panel, ratio=2),
        Layout(sandbox_panel, ratio=1)
    )

    layout["header"].update(
        Panel(
            f"[bold cyan]{TITLE}[/bold cyan]  [white]{SUBTITLE}[/white]\n{datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}",
            style="bold white on black",
            border_style="cyan",
        )
    )

    footer = Text(f"[1] Dashboard  [2] Sandbox  [3] AI Analyzer  [4] Logs  [Q] Quit", style="bright_black")
    layout["footer"].update(Align.center(footer))
    return layout

def main():
    console.clear()
    console.rule("[bold green]Launching AXS CyberOps Dashboard[/bold green]")
    # start command thread
    cmd_thread = CommandExecutor()
    cmd_thread.start()
    try:
        with Live(build_dashboard(), refresh_per_second=1, screen=True) as live:
            while True:
                time.sleep(REFRESH_INTERVAL)
                live.update(build_dashboard())
    except KeyboardInterrupt:
        pass
    finally:
        cmd_thread.stop()
    console.rule("[red]Session Ended[/red]")

if __name__ == "__main__":
    main()
