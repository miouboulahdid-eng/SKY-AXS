from textual.screen import Screen
from textual.widgets import Static
import redis

class RedisScreen(Screen):
    def compose(self):
        yield Static("📡 شاشة مراقبة Redis", classes="title")
        self.output = Static()
        yield self.output

    async def on_mount(self):
        try:
            r = redis.Redis(host="host", port=6379)
            info = r.info()
            keys = r.dbsize()
            output = f"✅ Redis متصل\nعدد المفاتيح: {keys}\nالحالة: {info['role']} | connected_clients: {info['connected_clients']}"
        except Exception as e:
            output = f"❌ فشل الاتصال بـ Redis: {e}"

        self.output.update(output)
