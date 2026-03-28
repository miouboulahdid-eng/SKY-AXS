from textual.screen import Screen
from textual.widgets import Static
import psutil

class PerformanceScreen(Screen):
    def compose(self):
        yield Static("🧠 مراقبة الأداء", classes="title")
        self.output = Static()
        yield self.output

    async def on_mount(self):
        cpu = psutil.cpu_percent()
        mem = psutil.virtual_memory().percent
        output = f"CPU Usage: {cpu}%\nMemory Usage: {mem}%"
        self.output.update(output)
