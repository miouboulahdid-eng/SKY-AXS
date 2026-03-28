from textual.screen import Screen
from textual.widgets import Static
import os, json, redis
from textual import events

class DecisionScreen(Screen):
    def compose(self):
        yield Static("🔐 Decision Engine\n", id="title")
        yield Static(self.render_decisions(), id="decisions")

    def render_decisions(self):
        try:
            r = redis.Redis(host=os.environ.get("REDIS_HOST","redis"), port=6379, decode_responses=True)
            items = r.xrevrange("stream:decisions", count=10)
            lines=[]
            for _id, msg in items:
                data = msg.get("data") or msg
                try:
                    if isinstance(data,str):
                        data=json.loads(data)
                except:
                    data={"raw": data}
                lines.append(f"{_id} | action={data.get('action','?')} | reason={data.get('reason','')}")
            return "\n".join(lines) if lines else "No decisions yet."
        except Exception:
            return "Decisions not available."

    async def on_message(self, event: events.Message) -> None:
        if event._text == "refresh":
            self.query_one("#decisions", Static).update(self.render_decisions())
