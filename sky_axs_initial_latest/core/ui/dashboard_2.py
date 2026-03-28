# core/ui/dashboard_v2.py

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical, Grid
from textual.widgets import Static, Input, Footer
from textual.reactive import reactive
from rich.text import Text
import docker
import asyncio

client = docker.from_env()

def get_container_color(health):
    if health == "healthy":
        return "green"
    elif health == "unhealthy":
        return "red"
    elif health == "starting":
        return "yellow"
    else:
        return "grey50"

def get_container_icon(health):
    if health == "healthy":
        return "🟢"
    elif health == "unhealthy":
        return "🔴"
    elif health == "starting":
        return "🟡"
    else:
        return "⚪"

class Dashboard(App):
    BINDINGS = [("q", "quit", "Quit")]

    def compose(self) -> ComposeResult:
        yield Static("🛡️ [b cyan]SKY AXS TOOL — TERMINAL DASHBOARD[/b cyan]", id="header")

        with Grid(id="main-grid"):
            yield Static("📦 [b]حالة الحاويات[/b]", id="containers-title")
            yield Vertical(id="containers-box")

            yield Static("🧠 [b]حالة النظام[/b]", id="system-title")
            yield Static(id="system-info")

        yield Static("⌨️ [b]سطر الأوامر[/b]", id="command-title")
        yield Input(placeholder="> اكتب الأمر هنا لتشغيله", id="command-input")

        yield Footer()

    async def on_mount(self) -> None:
        self.set_interval(5, self.update_data)
        await self.update_data()

    async def update_data(self):
        try:
            containers = client.containers.list(all=True)
            box = self.query_one("#containers-box", Vertical)
            box.remove_children()

            for c in containers:
                name = c.name
                status = c.status
                health = c.attrs.get("State", {}).get("Health", {}).get("Status", "unknown")
                color = get_container_color(health)
                icon = get_container_icon(health)

                text = Text(f"{icon} {name.ljust(30)} ({health})", style=color)
                box.mount(Static(text))

            # تحديث النظام (قيم وهمية الآن)
            sys_info = self.query_one("#system-info", Static)
            sys_info.update(Text("CPU: 1%  |  MEM: 5%  |  Uptime: 15087s", style="bold white"))

        except Exception as e:
            self.query_one("#containers-box", Vertical).mount(Static(f"[red]Error: {e}"))

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        cmd = event.value.strip()
        if cmd:
            self.query_one("#command-input", Input).value = ""
            self.query_one("#containers-box", Vertical).mount(Static(f"[grey62]✔ تم تنفيذ الأمر:[/grey62] {cmd}"))

if __name__ == "__main__":
    Dashboard().run()
