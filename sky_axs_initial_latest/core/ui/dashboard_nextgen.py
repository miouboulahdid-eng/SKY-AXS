# core/ui/dashboard_nextgen.py

from textual.app import App, ComposeResult
from textual.containers import Grid
from textual.widgets import Static, Input, Footer, ListView, ListItem
from textual.reactive import reactive
from rich.text import Text
import docker
import redis
import datetime

# إعداد الاتصال بـ Redis
redis_client = redis.Redis(host='localhost', port=6379, decode_responses=True)

# إعداد Docker
docker_client = docker.from_env()

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
    }.get(health, "grey50")

class DashboardNextgen(App):
    CSS = """
    Screen {
        layout: vertical;
        padding: 1;
    }

    #title {
        content-align: center middle;
        color: cyan;
        height: 3;
    }

    #grid {
        grid-size: 2;
        grid-columns: 1fr 1fr;
    }

    #containers, #system, #log {
        border: round #666666;
        height: auto;
        padding: 1;
    }

    #command {
        border: round #444444;
        height: 3;
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
        yield Static("🛡️ SKY AXS TOOL — NEXTGEN DASHBOARD", id="title")
        with Grid(id="grid"):
            self.container_list = ListView(id="containers")
            self.log_list = ListView(id="log")
            yield self.container_list
            yield self.log_list
            yield Static(id="system")
            yield Static(id="command")
        yield Input(placeholder="> اكتب الأمر هنا (مثل restart api)", id="input")
        yield Footer()

    async def on_mount(self):
        self.set_interval(5, self.update_dashboard)
        await self.update_dashboard()

    async def update_dashboard(self):
        try:
            # عرض الحاويات
            self.container_list.clear()
            containers = docker_client.containers.list(all=True)
            self.container_list.append(ListItem(Static(Text("📦 [b]الحاويات[/b]", style="bold cyan"))))
            for c in containers:
                name = c.name
                health = c.attrs.get("State", {}).get("Health", {}).get("Status", "unknown")
                line = f"{status_icon(health)} {name.ljust(25)} ({health})"
                self.container_list.append(ListItem(Static(Text(line, style=status_color(health)))))

            # معلومات النظام + Redis
            sys_info = self.query_one("#system", Static)
            redis_status = "❌ غير متصل"
            redis_keys = "؟"

            try:
                if redis_client.ping():
                    redis_status = "✅ متصل"
                    redis_keys = redis_client.dbsize()
            except Exception as e:
                redis_status = f"❌ خطأ: {e}"

            sys_text = (
                "🧠 [b]النظام[/b]\n"
                "CPU: 1%\n"
                "MEM: 5%\n"
                "Uptime: 15087s\n\n"
                f"📡 [b]Redis:[/b] {redis_status} | المفاتيح: {redis_keys}"
            )
            sys_info.update(Text(sys_text, style="white"))

            # سجل الأوامر
            self.log_list.clear()
            self.log_list.append(ListItem(Static(Text("📋 [b]السجل[/b]", style="bold green"))))
            for log in self.logs[-5:]:
                self.log_list.append(ListItem(Static(log)))

            # عنوان سطر الأوامر
            self.query_one("#command", Static).update(Text("⌨️ [b]سطر الأوامر[/b]", style="magenta"))

        except Exception as e:
            self.container_list.clear()
            self.container_list.append(ListItem(Static(f"[red]خطأ: {e}[/red]")))

    async def on_input_submitted(self, message: Input.Submitted) -> None:
        cmd = message.value.strip()
        self.query_one("#input", Input).value = ""
        response = ""

        if cmd.startswith("restart "):
            name = cmd.split(" ", 1)[1]
            try:
                container = docker_client.containers.get(name)
                container.restart()
                response = f"✔ تم إعادة تشغيل {name}"
            except Exception as e:
                response = f"✖ خطأ: {e}"

        elif cmd.startswith("logs "):
            name = cmd.split(" ", 1)[1]
            try:
                container = docker_client.containers.get(name)
                logs = container.logs(tail=5).decode()
                response = f"📄 آخر Logs:\n{logs}"
            except Exception as e:
                response = f"✖ خطأ في جلب السجلات: {e}"

        elif cmd.startswith("screen "):
            screen = cmd.split(" ", 1)[1]
            response = f"🚧 شاشة {screen} غير متوفرة بعد"

        else:
            response = f"⚠️ أمر غير معروف: {cmd}"

        now = datetime.datetime.now().strftime("%H:%M:%S")
        self.logs.append(f"[{now}] {response}")

if __name__ == "__main__":
    DashboardNextgen().run()
