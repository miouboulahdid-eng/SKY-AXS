#!/usr/bin/env python3
# core/ui/term_panel_curses.py
# واجهة TRMINAL ثابتة بدون وميض + axs command prompt + F1-F4 controls
# Dependencies: python3, docker CLI (optional), curses (builtin)
import curses
import datetime
import json
import os
import shutil
import subprocess
import time

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DATA_CMDS = os.path.join(ROOT, "data", "commands")
RESULTS_DIR = os.path.join(ROOT, "data", "results")
os.makedirs(DATA_CMDS, exist_ok=True)
os.makedirs(RESULTS_DIR, exist_ok=True)

def now_ts():
    return int(time.time())

def write_fallback_command(cmd_type, payload):
    fname = f"{now_ts()}_{cmd_type}.json"
    path = os.path.join(DATA_CMDS, fname)
    try:
        with open(path, "w") as f:
            json.dump({"type": cmd_type, "payload": payload, "ts": datetime.datetime.utcnow().isoformat()}, f, indent=2)
        return path
    except Exception as e:
        return None

def try_docker_ps():
    # return list of tuples: (name, image, status)
    try:
        out = subprocess.check_output(["docker", "ps", "--format", "{{.Names}}\t{{.Image}}\t{{.Status}}"], stderr=subprocess.STDOUT, text=True)
        lines = [l for l in out.splitlines() if l.strip()]
        rows = []
        for l in lines:
            parts = l.split("\t")
            if len(parts) >= 3:
                rows.append((parts[0], parts[1], parts[2]))
            else:
                rows.append((parts[0], parts[1] if len(parts)>1 else "", ""))
        return rows
    except Exception:
        # if docker not available, return empty
        return []

def get_system_status():
    # minimal info: cpu% (approx), mem, uptime
    try:
        # cpu via top/awk (approx)
        cpu = 0.0
        mem_total = 0
        mem_used = 0
        try:
            with open("/proc/uptime") as f:
                uptime_s = int(float(f.readline().split()[0]))
        except Exception:
            uptime_s = 0
        try:
            with open("/proc/meminfo") as f:
                lines = f.readlines()
            info = {}
            for r in lines:
                k,v = r.split(":",1)
                info[k.strip()] = int(v.strip().split()[0])
            mem_total = int(info.get("MemTotal",0) / 1024)
            mem_free = int(info.get("MemAvailable",0) / 1024)
            mem_used = mem_total - mem_free
        except Exception:
            pass
        return {"cpu_pct": cpu, "mem_total_mb": mem_total, "mem_used_mb": mem_used, "uptime_s": uptime_s}
    except Exception:
        return {"cpu_pct": 0.0, "mem_total_mb": 0, "mem_used_mb": 0, "uptime_s": 0}

def read_latest_results(limit=8):
    # scan RESULTS_DIR for json files sorted by mtime descending
    try:
        files = []
        for fn in os.listdir(RESULTS_DIR):
            if fn.endswith(".json"):
                path = os.path.join(RESULTS_DIR, fn)
                st = os.stat(path)
                files.append((fn, datetime.datetime.utcfromtimestamp(st.st_mtime).isoformat(), "ok"))
        files.sort(key=lambda x: x[1], reverse=True)
        return files[:limit]
    except Exception:
        return []

# helper draw boxes without flicker
def show_text_box(win, title, lines, color_pair=1):
    win.box()
    try:
        win.addstr(0, 2, f" {title} ", curses.color_pair(color_pair) | curses.A_BOLD)
    except Exception:
        pass
    maxy, maxx = win.getmaxyx()
    y = 1
    for ln in lines:
        if y >= maxy-1:
            break
        # ensure we don't write out of bounds
        try:
            trimmed = ln[:maxx-4]
            win.addstr(y, 1, trimmed)
        except Exception:
            pass
        y += 1

def draw_all(left_win, center_win, right_win, bottom_win, sysinfo, containers, results, selected_idx, status_msg):
    # erase only the small windows
    left_win.erase(); center_win.erase(); right_win.erase(); bottom_win.erase()
    # left
    left_lines = [
        f"CPU Usage: {sysinfo.get('cpu_pct',0.0):.1f}%",
        f"Memory: {sysinfo.get('mem_used_mb',0)} / {sysinfo.get('mem_total_mb',0)} MB",
        f"Uptime: {sysinfo.get('uptime_s',0)}s",
        "",
        "[r] Refresh manually",
        "[q] Quit",
        "",
    ]
    show_text_box(left_win, "SYSTEM STATUS", left_lines, color_pair=2)

    # center
    center_lines = [
        "[F1] Run PoC   [F2] Restart   [F3] Stop   [F4] Logs   [r] Refresh   [q] Quit",
        "",
        "ACTIVE CONTAINERS:"
    ]
    for idx, (name, image, status) in enumerate(containers):
        prefix = "->" if idx == selected_idx else "  "
        line = f"{prefix} {name:28.28} {image:16.16} {status}"
        center_lines.append(line)
    show_text_box(center_win, "CONTROLS / ACTIVE CONTAINERS", center_lines, color_pair=1)

    # right
    right_lines = ["File                          Modified                Status", "-"*40]
    for (fn, mtime, st) in results:
        right_lines.append(f"{fn[:28]:28} {mtime.split('T')[0]:20} {st}")
    show_text_box(right_win, "LATEST SANDBOX RESULTS", right_lines, color_pair=4)

    bottom_win.box()
    maxy, maxx = bottom_win.getmaxyx()
    try:
        bottom_win.addstr(0, 2, " axs> ", curses.color_pair(3) | curses.A_REVERSE)
        bottom_win.addstr(1, 2, f"Status: {status_msg[:maxx-12]}")
    except Exception:
        pass

    # noutrefresh + doupdate for atomic update
    left_win.noutrefresh(); center_win.noutrefresh(); right_win.noutrefresh(); bottom_win.noutrefresh()
    curses.doupdate()

def show_logs(center_win, container_name):
    # fetch last 200 lines of docker logs
    try:
        out = subprocess.check_output(["docker","logs","--tail","200", container_name], text=True, stderr=subprocess.STDOUT)
        lines = out.splitlines()
    except Exception as e:
        lines = [f"Failed to fetch logs: {e}"]
    # draw into center_win replacing content area
    center_win.erase()
    show_text_box(center_win, f"LOGS: {container_name}", lines[:center_win.getmaxyx()[0]-3], color_pair=5)
    center_win.noutrefresh()
    curses.doupdate()

def run_poc_prompt(stdscr, bottom_win):
    # prompt user for target and strategy
    curses.echo()
    bottom_win.erase(); bottom_win.box()
    bottom_win.addstr(1,2, "Enter target: ")
    bottom_win.refresh()
    try:
        target = bottom_win.getstr(1, 16, 100).decode().strip()
    except Exception:
        target = ""
    bottom_win.erase(); bottom_win.box()
    bottom_win.addstr(1,2, "Enter strategy (comma): ")
    bottom_win.refresh()
    try:
        strategy = bottom_win.getstr(1, 26, 200).decode().strip()
    except Exception:
        strategy = ""
    curses.noecho()
    return target, strategy

def main(stdscr):
    curses.curs_set(0)
    curses.start_color()
    curses.use_default_colors()
    # color pairs: choose vibrant cyber-ish
    curses.init_pair(1, curses.COLOR_GREEN, -1)
    curses.init_pair(2, curses.COLOR_CYAN, -1)
    curses.init_pair(3, curses.COLOR_YELLOW, -1)
    curses.init_pair(4, curses.COLOR_MAGENTA, -1)
    curses.init_pair(5, curses.COLOR_RED, -1)

    # compute layout (once)
    maxy, maxx = stdscr.getmaxyx()
    left_w = max(24, maxx//6)
    right_w = max(24, maxx//6)
    center_w = maxx - left_w - right_w - 4
    # create windows once (no flicker)
    left_win = curses.newwin(maxy-4, left_w, 0, 0)
    center_win = curses.newwin(maxy-4, center_w, 0, left_w+2)
    right_win = curses.newwin(maxy-4, right_w, 0, left_w+2+center_w+2)
    bottom_win = curses.newwin(4, maxx, maxy-4, 0)

    selected_idx = 0
    status_msg = "Ready."
    stdscr.timeout(200)  # small timeout so getch non-blocking

    # initial draw
    sysinfo = get_system_status()
    containers = try_docker_ps()
    results = read_latest_results(10)
    draw_all(left_win, center_win, right_win, bottom_win, sysinfo, containers, results, selected_idx, status_msg)

    # keep a simple command buffer for axs>
    cmd_buffer = ""

    while True:
        try:
            key = stdscr.getch()
        except KeyboardInterrupt:
            break

        if key == -1:
            # no key pressed; continue loop without redrawing everything (no flicker)
            continue

        # navigation keys
        if key in (ord('q'), ord('Q')):
            break
        elif key in (ord('r'), ord('R')):
            sysinfo = get_system_status()
            containers = try_docker_ps()
            results = read_latest_results(10)
            status_msg = "Refreshed manually."
            draw_all(left_win, center_win, right_win, bottom_win, sysinfo, containers, results, selected_idx, status_msg)
        elif key == curses.KEY_DOWN:
            if containers:
                selected_idx = (selected_idx + 1) % len(containers)
                draw_all(left_win, center_win, right_win, bottom_win, sysinfo, containers, results, selected_idx, status_msg)
        elif key == curses.KEY_UP:
            if containers:
                selected_idx = (selected_idx - 1) % len(containers)
                draw_all(left_win, center_win, right_win, bottom_win, sysinfo, containers, results, selected_idx, status_msg)

        # Function key handlers
        elif key == curses.KEY_F1:
            # Run PoC flow: prompt for target/strategy
            tgt, strat = run_poc_prompt(stdscr, bottom_win)
            if not tgt or not strat:
                status_msg = "Run PoC canceled."
            else:
                payload = {"target": tgt, "strategy": strat}
                path = write_fallback_command("run_poc", payload)
                status_msg = f"Queued PoC for {tgt} -> {path or 'err'}"
            draw_all(left_win, center_win, right_win, bottom_win, sysinfo, containers, results, selected_idx, status_msg)
        elif key == curses.KEY_F2:
            # Restart selected container
            if containers:
                name = containers[selected_idx][0]
                # attempt docker restart
                try:
                    subprocess.check_output(["docker","restart", name], stderr=subprocess.STDOUT, text=True, timeout=10)
                    status_msg = f"Restarted {name}"
                except Exception:
                    # fallback write command
                    write_fallback_command("restart", {"name": name})
                    status_msg = f"Restart queued for {name}"
            else:
                status_msg = "No container selected."
            draw_all(left_win, center_win, right_win, bottom_win, sysinfo, containers, results, selected_idx, status_msg)
        elif key == curses.KEY_F3:
            # Stop selected container
            if containers:
                name = containers[selected_idx][0]
                try:
                    subprocess.check_output(["docker","stop", name], stderr=subprocess.STDOUT, text=True, timeout=10)
                    status_msg = f"Stopped {name}"
                except Exception:
                    write_fallback_command("stop", {"name": name})
                    status_msg = f"Stop queued for {name}"
            else:
                status_msg = "No container selected."
            draw_all(left_win, center_win, right_win, bottom_win, sysinfo, containers, results, selected_idx, status_msg)
        elif key == curses.KEY_F4:
            # Show logs for selected container
            if containers:
                name = containers[selected_idx][0]
                show_logs(center_win, name)
                status_msg = f"Showing logs for {name}"
            else:
                status_msg = "No container selected."
            draw_all(left_win, center_win, right_win, bottom_win, sysinfo, containers, results, selected_idx, status_msg)

        # handle direct input in bottom command line (axs>), Enter = execute
        elif key in (10, 13):  # Enter
            line = cmd_buffer.strip()
            if line:
                parts = line.split()
                cmd = parts[0].lower()
                args = parts[1:]
                if cmd == "run_poc":
                    # expect: run_poc <target> <comma-list-strategy>
                    if len(args) >= 2:
                        tgt = args[0]
                        strat = args[1]
                        p = write_fallback_command("run_poc", {"target": tgt, "strategy": strat})
                        status_msg = f"Queued run_poc {tgt}"
                    else:
                        status_msg = "Usage: run_poc <target> <strategy>"
                elif cmd == "restart":
                    if len(args) >= 1:
                        name = args[0]
                        try:
                            subprocess.check_output(["docker","restart", name], stderr=subprocess.STDOUT, text=True, timeout=10)
                            status_msg = f"Restarted {name}"
                        except Exception:
                            write_fallback_command("restart", {"name": name})
                            status_msg = f"Restart queued for {name}"
                    else:
                        status_msg = "Usage: restart <container>"
                elif cmd == "stop":
                    if len(args) >= 1:
                        name = args[0]
                        try:
                            subprocess.check_output(["docker","stop", name], stderr=subprocess.STDOUT, text=True, timeout=10)
                            status_msg = f"Stopped {name}"
                        except Exception:
                            write_fallback_command("stop", {"name": name})
                            status_msg = f"Stop queued for {name}"
                    else:
                        status_msg = "Usage: stop <container>"
                elif cmd == "logs":
                    if len(args) >= 1:
                        name = args[0]
                        show_logs(center_win, name)
                        status_msg = f"Showing logs for {name}"
                        # skip full redraw here as show_logs already updated center
                        cmd_buffer = ""
                        bottom_win.erase(); bottom_win.box()
                        bottom_win.addstr(1,2, "axs> ")
                        bottom_win.noutrefresh()
                        curses.doupdate()
                        continue
                    else:
                        status_msg = "Usage: logs <container>"
                else:
                    status_msg = f"Unknown command: {cmd}"
            else:
                status_msg = "Empty command."
            cmd_buffer = ""
            draw_all(left_win, center_win, right_win, bottom_win, sysinfo, containers, results, selected_idx, status_msg)

        # handle Backspace
        elif key in (curses.KEY_BACKSPACE, 127, 8):
            cmd_buffer = cmd_buffer[:-1]
            bottom_win.erase(); bottom_win.box()
            try:
                bottom_win.addstr(1,2, f"axs> {cmd_buffer}")
            except Exception:
                pass
            bottom_win.noutrefresh(); curses.doupdate()
        # handle printable characters
        elif 32 <= key <= 126:
            cmd_buffer += chr(key)
            bottom_win.erase(); bottom_win.box()
            try:
                bottom_win.addstr(1,2, f"axs> {cmd_buffer}")
            except Exception:
                pass
            bottom_win.noutrefresh(); curses.doupdate()
        else:
            # unknown key — ignore
            pass

if __name__ == "__main__":
    curses.wrapper(main)
