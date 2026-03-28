from textual.screen import Screen
from textual.widgets import Static
import redis, json, os
from textual import events

class DashboardScreen(Screen):
    BINDINGS = [("enter", "noop", "noop")]

    def compose(self):
        yield Static("🔷 AXS Dashboard (Home)\n", id="title")
        yield Static(self.render_stats(), id="stats")

    def render_stats(self):
        # try to read simple values from Redis stream or fallback to files
        try:
            r = redis.Redis(host=os.environ.get("REDIS_HOST","redis"), port=6379, decode_responses=True)
            # example: read last sandbox result id
            items = r.xrevrange("stream:sandbox_results", count=1)
            last = None
            if items:
                _, msg = items[0]
                last = msg.get("data") or msg
                if isinstance(last, str):
                    try:
                        last = json.loads(last)
                    except:
                        last = {"raw": last}
            stats = {
                "active_scans": r.llen("rq:queue:sky") if r.exists("rq:queue:sky") else 0,
                "last_result": last
            }
            return json.dumps(stats, indent=2)
        except Exception:
            return "Redis not available — showing local summary\n- Active scans: ?\n- Last result: N/A"

    async def on_message(self, event: events.Message) -> None:
        if event._text == "refresh":
            self.query_one("#stats", Static).update(self.render_stats())
