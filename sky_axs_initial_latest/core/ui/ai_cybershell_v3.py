#!/usr/bin/env python3
"""
AXS Terminal Control Panel (ai_cybershell_v3.py)
- curses-based TUI with:
  * left: system status + cost info
  * center: controls, containers list, command buttons
  * right: latest sandbox results
  * bottom: command input line (axs>), keybindings
- Safe by default: writes commands JSON files to data/commands/
  optional Redis publish if redis package and connection available.
- To allow direct docker actions (risky), set env DIRECT_EXEC=1
"""

from __future__ import annotations
import curses
import time
import json
import os
import subprocess
import threading
import datetime
import glob
import pathlib
import traceback
from typing import List, Dict, Optional

PROJECT_ROOT = os.path.abspath(os.getcwd())
DATA_COMMANDS = os.path.join(PROJECT_ROOT, "data", "commands")
DATA_RESULTS = os.path.join(PROJECT_ROOT, "data", "results")
COST_CONFIG = os.path.join(PROJECT_ROOT, "cost_config.json")
REDIS_STREAM = "stream:commands"

os.makedirs(DATA_COMMANDS, exist_ok=True)
os.makedirs(DATA_RESULTS, exist_ok=True)

# Try redis (optional)
REDIS_CLIENT = None
try:
    import redis
    rhost = os.environ.get("REDIS_HOST", "127.0.0.1")
    rport = int(os.environ.get("REDIS_PORT", "6379"))
    REDIS_CLIENT = redis.Redis(host=rhost, port=rport, db=0, socket_connect_timeout=1)
    try:
        REDIS_CLIENT.ping()
    except Exception:
        REDIS_CLIENT = None
except Exception:
    REDIS_CLIENT = None

DIRECT_EXEC = os.environ.get("DIRECT_EXEC", "0") in ("1", "true", "True")

REFRESH_INTERVAL = 2.0  # seconds


def now_ts() -> int:
    return int(time.time())


def write_command_file(payload: dict) -> str:
    fname = f"{now_ts()}_{os.getpid()}.json"
    path = os.path.join(DATA_COMMANDS, fname)
    with open(path, "w") as f:
        json.dump(payload, f, indent=2, default=str)
    return path


def publish_command(payload: dict) -> bool:
    """
    Publish to Redis stream if available; otherwise fallback to writing file.
    Returns True if published to Redis.
    """
    if REDIS_CLIENT:
        try:
            REDIS_CLIENT.xadd(REDIS_STREAM, payload)
            return True
        except Exception:
            pass
    write_command_file(payload)
    return False


def safe_shell(cmd: List[str], timeout: int = 10) -> (int, str):
    try:
        p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout, text=True)
        return p.returncode, p.stdout
    except Exception as e:
        return -1, f"error: {e}"


def get_docker_containers() -> List[Dict]:
    """
    Returns list of containers via docker ps; each entry: {name,image,status,ports}
    If docker not available or error -> empty list.
    """
    try:
        ret, out = safe_shell(["docker", "ps", "--format", "{{.Names}}\t{{.Image}}\t{{.Status}}"])
        if ret != 0:
            return []
        lines = [l for l in out.splitlines() if l.strip()]
        result = []
        for l in lines:
            parts = l.split("\t")
            name = parts[0] if len(parts) > 0 else ""
            image = parts[1] if len(parts) > 1 else ""
            status = parts[2] if len(parts) > 2 else ""
            result.append({"name": name, "image": image, "status": status})
        return result
    except Exception:
        return []


def list_recent_results(limit: int = 10) -> List[Dict]:
    files = sorted(glob.glob(os.path.join(DATA_RESULTS, "*.json")), key=os.path.getmtime, reverse=True)[:limit]
    out = []
    for f in files:
        try:
            mtime = datetime.datetime.fromtimestamp(os.path.getmtime(f)).isoformat()
            with open(f, "r") as fh:
                j = json.load(fh)
            status = j.get("status", "ok")
            out.append({"file": os.path.basename(f), "status": status, "ts": mtime})
        except Exception:
            out.append({"file": os.path.basename(f), "status": "error", "ts": ""})
    return out


def read_cost_config() -> dict:
    if not os.path.exists(COST_CONFIG):
        return {}
    try:
        with open(COST_CONFIG, "r") as f:
            return json.load(f)
    except Exception:
        return {}


def format_bytes(b: int) -> str:
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if b < 1024:
            return f"{b:.1f}{unit}"
        b /= 1024
    return f"{b:.1f}PB"


def system_stats() -> dict:
    # basic stats: cpu% via top? use /proc for linux
    stats = {"cpu_percent": "-", "mem_percent": "-", "uptime": "-", "disk_avail": "-", "redis": "online" if REDIS_CLIENT else "offline"}
    try:
        # uptime
        with open("/proc/uptime", "r") as f:
            uptime_s = float(f.readline().split()[0])
            stats["uptime"] = f"{int(uptime_s)}s"
        # mem
        meminfo = {}
        with open("/proc/meminfo", "r") as f:
            for line in f:
                k, v = line.split(":", 1)
                meminfo[k.strip()] = int(v.strip().split()[0])  # kB
        total_k = meminfo.get("MemTotal", 0)
        free_k = meminfo.get("MemAvailable", meminfo.get("MemFree", 0))
        if total_k:
            stats["mem_percent"] = f"{(1 - free_k/total_k)*100:.1f}%"
        # cpu: use top 1 snapshot via mpstat? approximated with /proc/stat
        with open("/proc/stat", "r") as f:
            for line in f:
                if line.startswith("cpu "):
                    parts = line.split()
                    vals = list(map(int, parts[1:]))
                    idle = vals[3]
                    total = sum(vals)
                    stats["cpu_percent"] = f"~{0.0:.1f}%"  # placeholder, calculating proper needs diff sampling
                    break
    except Exception:
        pass
    try:
        st = os.statvfs("/")
        free = st.f_bavail * st.f_frsize
        stats["disk_avail"] = format_bytes(free)
    except Exception:
        pass
    return stats


# -----------------------------
# Curses UI implementation
# -----------------------------
class AXSPanel:
    def __init__(self, stdscr):
        self.stdscr = stdscr
        self.containers = []
        self.results = []
        self.stats = {}
        self.selected_index = 0
        self.command_input = ""
        self.log_lines: List[str] = []
        self.running = True
        self.last_refresh = 0.0
        self.lock = threading.Lock()

    def log(self, msg: str):
        ts = datetime.datetime.utcnow().isoformat(timespec="seconds")
        with self.lock:
            self.log_lines.append(f"[{ts}] {msg}")
            if len(self.log_lines) > 200:
                self.log_lines = self.log_lines[-200:]

    def refresh_data(self):
        try:
            self.containers = get_docker_containers()
            self.results = list_recent_results(limit=10)
            self.stats = system_stats()
        except Exception as e:
            self.log(f"refresh error: {e}")

    def background_refresher(self):
        while self.running:
            now = time.time()
            if now - self.last_refresh >= REFRESH_INTERVAL:
                self.refresh_data()
                self.last_refresh = now
            time.sleep(0.5)

    def draw_borders(self):
        h, w = self.stdscr.getmaxyx()
        # outer border
        self.stdscr.border()
        # vertical splits: left 0.25, center 0.55, right 0.20 (approx)
        left_w = max(20, int(w * 0.22))
        right_w = max(20, int(w * 0.22))
        center_w = w - left_w - right_w - 4  # margins
        # columns positions
        x_left = 1
        x_center = x_left + left_w + 1
        x_right = x_center + center_w + 1
        # draw column vertical lines
        for y in range(1, h-1):
            self.stdscr.addch(y, x_center-1, curses.ACS_VLINE)
            self.stdscr.addch(y, x_right-1, curses.ACS_VLINE)
        # titles
        self.stdscr.addstr(0, 2, " AXS SECURITY ENGINE v3 ", curses.A_REVERSE)
        return (left_w, center_w, right_w, x_left, x_center, x_right)

    def draw_left(self, x, w):
        # System status + cost
        win = curses.newwin(curses.LINES-4, w, 1, x)
        win.box()
        win.addstr(0, 2, " SYSTEM STATUS ")
        stats = self.stats
        lines = [
            f"CPU: {stats.get('cpu_percent','-')}",
            f"Memory: {stats.get('mem_percent','-')}",
            f"Uptime: {stats.get('uptime','-')}",
            f"Disk avail: {stats.get('disk_avail','-')}",
            f"Redis: {stats.get('redis','offline')}"
        ]
        y = 2
        for L in lines:
            win.addstr(y, 2, L)
            y += 1
        # cost config
        cfg = read_cost_config()
        y += 1
        win.addstr(y, 2, "Cost estimator:")
        y += 1
        if cfg:
            per_hour = cfg.get("per_instance_hour_usd", None)
            if per_hour:
                win.addstr(y, 2, f"Instance $/hr: {per_hour}")
                y += 1
                est_month = per_hour * 24 * 30
                win.addstr(y, 2, f"Est monthly (24/7): ${est_month:.2f}")
                y += 1
            else:
                win.addstr(y, 2, "Edit cost_config.json to add rates.")
                y += 1
        else:
            win.addstr(y, 2, "(no cost_config.json found)")
            y += 1
            win.addstr(y, 2, "See cost_config.example.json")
        win.noutrefresh()

    def draw_center(self, x, w):
        # Main control panel
        h = curses.LINES - 6
        win = curses.newwin(h, w, 1, x)
        win.box()
        win.addstr(0, 2, " CONTROLS ")
        # Buttons row
        btns = ["[F1] Run PoC", "[F2] Restart", "[F3] Stop", "[F4] Logs", "[r] Refresh", "[q] Quit"]
        row = 1
        col = 2
        for b in btns:
            win.addstr(row, col, b, curses.color_pair(2))
            col += len(b) + 2
        # containers table header
        y = 3
        win.addstr(y, 2, "ACTIVE CONTAINERS:")
        y += 1
        win.addstr(y, 2, f"{'Name':30.30}{'Image':25.25}{'Status':25}")
        y += 1
        # rows
        for idx, c in enumerate(self.containers):
            name = c.get("name", "")[:30]
            image = c.get("image", "")[:25]
            status = c.get("status", "")[:25]
            attr = curses.A_REVERSE if idx == self.selected_index else curses.A_NORMAL
            win.addstr(y, 2, f"{name:30}{image:25}{status:25}", attr)
            y += 1
            if y > h - 3:
                break
        # command log area below
        log_h = 6
        log_start = max( y+1, h - log_h - 1)
        win.addstr(log_start - 1, 1, "-" * (w-2))
        # show last 4 log lines
        with self.lock:
            tail = self.log_lines[-(log_h-1):]
        ly = log_start
        for ln in tail:
            try:
                win.addstr(ly, 2, ln[:w-4])
            except Exception:
                pass
            ly += 1
        win.noutrefresh()

    def draw_right(self, x, w):
        h = curses.LINES - 4
        win = curses.newwin(h, w, 1, x)
        win.box()
        win.addstr(0, 2, " LATEST SANDBOX RESULTS ")
        y = 2
        win.addstr(y, 2, f"{'File':30}{'Status':10}{'Time':20}")
        y += 1
        for r in self.results:
            file = r.get("file","")[:30]
            status = r.get("status","")[:10]
            ts = r.get("ts","")[:20]
            win.addstr(y, 2, f"{file:30}{status:10}{ts:20}")
            y += 1
            if y > h-2:
                break
        win.noutrefresh()

    def draw_bottom_input(self):
        h, w = self.stdscr.getmaxyx()
        y = h - 3
        self.stdscr.hline(y-1, 1, curses.ACS_HLINE, w-2)
        prompt = "axs> "
        try:
            self.stdscr.addstr(y, 2, prompt + self.command_input)
            # footer help
            footer = "[Enter] send  [Up/Down] select container  [F1-F4] actions  [q] quit"
            self.stdscr.addstr(h-2, 2, footer, curses.A_DIM)
        except Exception:
            pass

    def run_poc_prompt(self):
        # interactive prompt in terminal (blocking)
        curses.echo()
        curses.nocbreak()
        self.stdscr.keypad(False)
        self.stdscr.addstr(curses.LINES-4, 2, "Enter --target ... --strategy ... --extra ... : ")
        self.stdscr.clrtoeol()
        s = self.stdscr.getstr(curses.LINES-4, 45, 200).decode(errors="ignore").strip()
        curses.noecho()
        curses.cbreak()
        self.stdscr.keypad(True)
        if s:
            payload = {"cmd": "run_poc", "payload": s, "ts": datetime.datetime.utcnow().isoformat()}
            published = publish_command(payload)
            if published:
                self.log("Published run_poc to Redis stream")
            else:
                self.log(f"Wrote command file for run_poc: {write_command_file(payload)}")

    def action_restart_selected(self):
        if not self.containers:
            self.log("No containers to restart")
            return
        c = self.containers[self.selected_index]
        payload = {"cmd": "restart", "container": c.get("name"), "ts": datetime.datetime.utcnow().isoformat()}
        if DIRECT_EXEC:
            # execute immediately (risky)
            self.log(f"Direct exec: docker restart {c.get('name')}")
            ret, out = safe_shell(["docker", "restart", c.get("name")], timeout=15)
            self.log(out.strip().splitlines()[-1] if out else f"rc={ret}")
        else:
            published = publish_command(payload)
            if published:
                self.log("Published restart command to Redis")
            else:
                self.log(f"Wrote command file: {write_command_file(payload)}")

    def action_stop_selected(self):
        if not self.containers:
            self.log("No containers to stop")
            return
        c = self.containers[self.selected_index]
        payload = {"cmd": "stop", "container": c.get("name"), "ts": datetime.datetime.utcnow().isoformat()}
        if DIRECT_EXEC:
            self.log(f"Direct exec: docker stop {c.get('name')}")
            ret, out = safe_shell(["docker", "stop", c.get("name")], timeout=15)
            self.log(out.strip().splitlines()[-1] if out else f"rc={ret}")
        else:
            published = publish_command(payload)
            if published:
                self.log("Published stop command to Redis")
            else:
                self.log(f"Wrote command file: {write_command_file(payload)}")

    def action_logs_selected(self, lines: int = 200):
        if not self.containers:
            self.log("No containers to fetch logs for")
            return
        c = self.containers[self.selected_index]
        payload = {"cmd": "logs", "container": c.get("name"), "lines": lines, "ts": datetime.datetime.utcnow().isoformat()}
        published = publish_command(payload)
        if published:
            self.log("Published logs request to Redis")
        else:
            self.log(f"Wrote command file: {write_command_file(payload)}")

    def action_submit_command(self, raw: str):
        raw = raw.strip()
        if not raw:
            return
        # simple parsing: if starts with 'run_poc ' accept rest
        if raw.startswith("run_poc "):
            payload = {"cmd": "run_poc", "payload": raw[len("run_poc "):], "ts": datetime.datetime.utcnow().isoformat()}
            published = publish_command(payload)
            if published:
                self.log("Published run_poc")
            else:
                self.log(f"Wrote command file: {write_command_file(payload)}")
            return
        if raw.startswith("restart "):
            cont = raw.split(" ", 1)[1]
            payload = {"cmd": "restart", "container": cont, "ts": datetime.datetime.utcnow().isoformat()}
            published = publish_command(payload)
            if published:
                self.log("Published restart command")
            else:
                self.log(f"Wrote command file: {write_command_file(payload)}")
            return
        # fallback: generic shell? we will queue it for safety
        payload = {"cmd": "shell", "payload": raw, "ts": datetime.datetime.utcnow().isoformat()}
        published = publish_command(payload)
        if published:
            self.log("Published shell command to Redis")
        else:
            self.log(f"Wrote command file: {write_command_file(payload)}")

    def handle_key(self, ch):
        if ch in (ord('q'), 27):  # q or ESC
            self.running = False
            return
        if ch == curses.KEY_UP:
            if self.selected_index > 0:
                self.selected_index -= 1
        elif ch == curses.KEY_DOWN:
            if self.selected_index < max(0, len(self.containers)-1):
                self.selected_index += 1
        elif ch == curses.KEY_F1:
            self.run_poc_prompt()
        elif ch == curses.KEY_F2:
            self.action_restart_selected()
        elif ch == curses.KEY_F3:
            self.action_stop_selected()
        elif ch == curses.KEY_F4:
            self.action_logs_selected()
        elif ch == ord('r'):
            self.refresh_data()
        elif ch in (curses.KEY_BACKSPACE, 127):
            self.command_input = self.command_input[:-1]
        elif ch == curses.KEY_ENTER or ch == 10 or ch == 13:
            # submit
            s = self.command_input.strip()
            if s:
                self.action_submit_command(s)
            self.command_input = ""
        elif 0 <= ch < 256:
            self.command_input += chr(ch)

    def draw(self):
        self.stdscr.clear()
        left_w, center_w, right_w, x_left, x_center, x_right = self.draw_borders()
        # draw sections
        self.draw_left(x_left+1, left_w)
        self.draw_center(x_center+1, center_w)
        self.draw_right(x_right+1, right_w)
        self.draw_bottom_input()
        curses.doupdate()

    def run(self):
        # init colors
        curses.start_color()
        curses.use_default_colors()
        curses.init_pair(1, curses.COLOR_CYAN, -1)
        curses.init_pair(2, curses.COLOR_YELLOW, -1)
        # start background refresher
        t = threading.Thread(target=self.background_refresher, daemon=True)
        t.start()
        self.log("AXS TUI started")
        self.refresh_data()
        self.stdscr.nodelay(True)
        while self.running:
            try:
                self.draw()
                # input
                try:
                    ch = self.stdscr.getch()
                except Exception:
                    ch = -1
                if ch != -1:
                    self.handle_key(ch)
                time.sleep(0.05)
            except Exception:
                self.log("UI loop exception: " + traceback.format_exc())
                time.sleep(0.5)
        self.log("shutting down")
        time.sleep(0.2)


def main_curses(stdscr):
    # setup
    stdscr.clear()
    stdscr.refresh()
    panel = AXSPanel(stdscr)
    panel.run()


if __name__ == "__main__":
    curses.wrapper(main_curses)
