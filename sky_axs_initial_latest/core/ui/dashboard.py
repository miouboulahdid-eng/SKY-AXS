# filename: dashboard.py

from textual.app import App, ComposeResult
from textual.widgets import Static, Input, Footer
from textual.containers import Container, Horizontal
from textual.reactive import reactive
from textual import events
import docker
import asyncio

client = docker.from_env()

class ContainerBox(Static):
    def __init__(self, name, status, health):
        color = "green" if health == "healthy" else ("yellow" if health == "starting" else "red")
        super().__init__(f"[b]{name}[/b]\n[bold {color}]{status.upper()}[/bold {color}] - {health}", expand=True)

class Dashboard(App):
    CSS_PATH = None
    BINDINGS = [("q", "quit", "Quit")]

    containers_data = reactive([])

    def compose(self) -> ComposeResult:
        yield Static("[b cyan]SKY AXS TOOL - TERMINAL DASHBOARD[/b cyan]", id="title", expand=True)
        yield Container(id="container-status")
        yield Static(id="system-info")
        yield Input(placeholder="> اكتب الأمر هنا لتشغيله", id="command-input")
        yield Footer()

    async def on_mount(self) -> None:
        self.set_interval(5, self.refresh_data)
        await self.refresh_data()

    async def refresh_data(self) -> None:
        try:
            containers = client.containers.list(all=True)
            container_widgets = []

            for c in containers:
                status = c.status
                name = c.name
                health = c.attrs.get("State", {}).get("Health", {}).get("Status", "unknown")
                widget = ContainerBox(name, status, health)
                container_widgets.append(widget)

            container_area = self.query_one("#container-status", Container)
            container_area.remove_children()
            for widget in container_widgets:
                container_area.mount(widget)

            # System info mock for now
            sys_info = self.query_one("#system-info", Static)
            sys_info.update("🔧 [b]CPU:[/b] 1% | [b]MEM:[/b] 5% | [b]Uptime:[/b] 15087s")

        except Exception as e:
            print("Error:", e)

    async def on_input_submitted(self, message: Input.Submitted) -> None:
        cmd = message.value.strip()
        if cmd:
            # Execute the command (simulate)
            self.query_one("#command-input", Input).value = ""
            container = self.query_one("#container-status", Container)
            container.mount(Static(f"[grey]نفذت الأمر:[/grey] {cmd}"))

if __name__ == "__main__":
    Dashboard().run()
