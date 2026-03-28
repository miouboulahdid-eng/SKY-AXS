from textual.screen import Screen
from textual.widgets import Static
import docker

class LogsScreen(Screen):
    def compose(self):
        yield Static("📋 شاشة عرض السجلات", classes="title")
        self.logs = Static()
        yield self.logs

    async def on_mount(self):
        try:
            client = docker.from_env()
            container = client.containers.get("sky_axs_initial-api")
            logs = container.logs(tail=20).decode()
            self.logs.update(logs)
        except Exception as e:
            self.logs.update(f"❌ خطأ: {e}")
