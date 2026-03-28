# ✅ المسار: core/ui/dashboard_app.py

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical, Container
from textual.widgets import Static, Input, Header, Footer
from textual.reactive import reactive
from textual.screen import Screen
from textual import events
import docker
import redis
import time
import datetime

client = docker.from_env()

class RedisStatus(Static):
    def on_mount(self):
        self.update_status()

    def update_status(self):
        try:
            r = redis.Redis(host="redis", port=6379, db=0, socket_connect_timeout=2)
            r.ping()
            keys = r.dbsize()
            self.update(f"[b]Redis:[/b] ✅ متصل | عدد المفاتيح: {keys}")
        except redis.ConnectionError as e:
            self.update(f"[b]Redis:[/b] ❌ خطأ: {e}")
        except Exception as e:
            self.update(f"[b]Redis:[/b] ⚠️ غير متصل | التفاصيل: {e}")

class ContainerStatus(Static):
    def on_mount(self):
        self.update_status()

    def update_status(self):
        try:
            containers = client.containers.list(all=True)
            output = "[b][blue]📦 الحاويات[/blue][/b]\n\n"
            for c in containers:
                name = c.name
                status = c.status
                health = c.attrs.get("State", {}).get("Health", {}).get("Status", "unknown")

                symbol = "🟢" if health == "healthy" else ("🔴" if health == "unhealthy" else "🟡")
                output += f"{symbol} {name} - ({health})\n"
            self.update(output)
        except Exception as e:
            self.update(f"[red]خطأ في جلب حالة الحاويات: {e}[/red]")

class LogsPanel(Static):
    logs = reactive("")

    def append_log(self, msg):
        now = datetime.datetime.now().strftime("[%H:%M:%S]")
        self.logs += f"{now} {msg}\n"
        self.update(self.logs)

class SystemStatus(Static):
    def on_mount(self):
        self.update_status()

    def update_status(self):
        cpu = "1%"
        mem = "5%"
        uptime = "15087s"
        self.update(f"[b]🖥️ النظام[/b]\nCPU: {cpu}\nMEM: {mem}\nUptime: {uptime}")

class DashboardScreen(Screen):
    def compose(self) -> ComposeResult:
        self.containers = ContainerStatus()
        self.logs = LogsPanel()
        self.redis = RedisStatus()
        self.sysinfo = SystemStatus()
        self.command_input = Input(placeholder="اكتب الأمر هنا (مثال: restart api)")

        yield Header(show_clock=True)
        yield Horizontal(
            Vertical(self.containers, self.redis, self.sysinfo, id="left"),
            Vertical(Static("[b]السجل[/b]"), self.logs, id="right"),
        )
        yield self.command_input
        yield Footer()

    async def on_input_submitted(self, message: Input.Submitted) -> None:
        cmd = message.value.strip()
        if cmd:
            self.logs.append_log(f"🚀 تنفيذ الأمر: {cmd}")
            try:
                result = self.execute_command(cmd)
                self.logs.append_log(f"✅ النتيجة: {result}")
            except Exception as e:
                self.logs.append_log(f"❌ خطأ: {e}")

    def execute_command(self, cmd: str):
        if cmd == "restart api":
            container = client.containers.get("sky_axs_initial-api")
            container.restart()
            return "تم إعادة تشغيل API"
        elif cmd == "restart all":
            for container in client.containers.list():
                container.restart()
            return "تمت إعادة تشغيل جميع الحاويات"
        else:
            return "❓ أمر غير معروف"

    async def on_mount(self) -> None:
        self.set_interval(10, self.refresh_status)

    def refresh_status(self):
        self.containers.update_status()
        self.redis.update_status()
        self.sysinfo.update_status()

class DashboardApp(App):
    CSS = """
    Screen {
        align: center middle;
        padding: 1;
    }
    #left, #right {
        width: 1fr;
        height: auto;
        border: solid gray;
        padding: 1;
    }
    Input {
        dock: bottom;
        height: 3;
        border: heavy blue;
    }
    """

    def on_mount(self):
        self.push_screen(DashboardScreen())

if __name__ == "__main__":
    DashboardApp().run()
