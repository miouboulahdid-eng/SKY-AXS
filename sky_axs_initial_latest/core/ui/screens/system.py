from textual.screen import Screen
from textual.widgets import Static
import psutil, os, json
from textual import events

class SystemScreen(Screen):
    def compose(self):
        yield Static("⚙️ System Status\n", id="title")
        yield Static(self.render_info(), id="info")

    def render_info(self):
        try:
            cpu = psutil.cpu_percent(interval=0.2)
            mem = psutil.virtual_memory().percent
            return f"CPU: {cpu}%\nMEM: {mem}%\nDocker: see docker ps (must run on host instance)"
        except Exception:
            return "psutil not available — cannot show host metrics."

    async def on_message(self, event: events.Message) -> None:
        if event._text == "refresh":
            self.query_one("#info", Static).update(self.render_info())
