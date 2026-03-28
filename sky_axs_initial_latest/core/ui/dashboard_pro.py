# core/ui/dashboard_pro.py (نسخة معدّلة بدون gap)

from textual.app import App, ComposeResult
from textual.containers import Grid, VerticalScroll
from textual.widgets import Static, Input, Footer
from textual.reactive import reactive
from rich.text import Text
import docker
import asyncio
import datetime

client = docker.from_env()

def status_icon(health):
    return {
        "healthy": "🟢",
        "unhealthy": "🔴",
        "starting": "🟡"
    }.get(health, "⚪")

def status_color(health):
    return {
        "healthy": "green",
        "unhealthy": "red",
        "starting": "yellow"
    }.get(health, "grey66")

class DashboardPro(App):
    CSS = """
    #header {
        content-align: center middle;
        padding: 1 0;
        background: #1e1e2e;
        color: cyan;
    }

    #main-grid {
        grid-size: 2;
        grid-columns: 65% 35%;
        grid-rows: auto auto auto;
        padding: 1;
    }

    #containers-box, #system-box, #log-box {
        border: round #888888;
        padding: 1;
    }

    #command-box {
        border: round #555555;
        padding: 1;
    }

    Input {
        width: 100%;
    }

    Footer {
        background: #1e1e2e;
    }
    """

    logs = reactive([])

    def compose(self) -> ComposeResult:
        yield Static("🛡️ SKY AXS TOOL — CYBEROPS DASHBOARD", id="header")
        with Grid(id="main-grid"):
            yield VerticalScroll(id="containers-box")
            yield VerticalScroll(id="log-box")
            yield Static(id="system-box")
            yield Static(id="command-box")
        yield Input(placeholder="> اكتب الأمر هنا (مثال: restart api)", id="input")
        yield Footer()

    async def on_mount(self) -> None:
        self.set_interval(5, self.update_dashboard)
        await self.update_dashboard()

    async def update_dashboard(self):

        try:

            containers = client.containers.list(all=True)

            container_box = self.query_one("#containers-box", VerticalScroll)

            container_box.clear()

            container_box.mount(Static(Text("📦 [b]حالة الحاويات[/b]\n", style="bold cyan")))



            for c in containers:

                name = c.name

                status = c.status

                health = c.attrs.get("State", {}).get("Health", {}).get("Status", "unknown")

                line = f"{status_icon(health)} {name.ljust(30)} ({health})"

                container_box.mount(Static(Text(line, style=status_color(health))))



            sys_text = f"🧠 [b]حالة النظام[/b]\n\nCPU: 1%\nMEM: 5%\nUptime: 15087s\n"

            self.query_one("#system-box", Static).update(Text(sys_text, style="bold white"))



            log_box = self.query_one("#log-box", VerticalScroll)

            log_box.clear()

            log_box.mount(Static(Text("📋 [b]سجل تنفيذ الأوامر[/b]\n", style="bold green")))

            for log in self.logs[-6:]:

                log_box.mount(Static(log))



            self.query_one("#command-box", Static).update(Text("⌨️ [b]سطر الأوامر[/b]\n", style="bold magenta"))



        except Exception as e:

            container_box = self.query_one("#containers-box", VerticalScroll)

            container_box.clear()

            container_box.mount(Static(f"[red]خطأ: {e}[/red]"))
        cmd = message.value.strip()
        if not cmd:
            return

        self.query_one("#input", Input).value = ""

        parts = cmd.split()
        result = ""
        if parts[0] == "restart" and len(parts) == 2:
            name = parts[1]
            try:
                container = client.containers.get(name)
                container.restart()
                result = f"✔ تم إعادة تشغيل {name}"
            except Exception as e:
                result = f"✖ خطأ أثناء إعادة تشغيل {name}: {e}"
        else:
            result = f"⚠️ أمر غير معروف: {cmd}"

        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        self.logs.append(f"[{timestamp}] {result}")

if __name__ == "__main__":
    DashboardPro().run()
