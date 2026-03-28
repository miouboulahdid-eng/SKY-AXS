from textual.screen import Screen
from textual.widgets import Static
import os, json, redis
from textual import events

class AIAnalyzerScreen(Screen):
    def compose(self):
        yield Static("🧠 AI Analyzer\n", id="title")
        yield Static(self.render_summary(), id="summary")

    def render_summary(self):
        try:
            r = redis.Redis(host=os.environ.get("REDIS_HOST","redis"), port=6379, decode_responses=True)
            items = r.xrevrange("stream:ai_insights", count=5)
            out=[]
            for _id, msg in items:
                data = msg.get("data") or msg
                if isinstance(data,str):
                    try:
                        data=json.loads(data)
                    except:
                        data={"raw": data}
                out.append(f"{data.get('ts',_id)} | risk={data.get('risk_score', '?')} | note={data.get('note','')}")
            return "\n".join(out) if out else "No AI insights yet."
        except Exception:
            return "AI insights not available (Redis down)."

    async def on_message(self, event: events.Message) -> None:
        if event._text == "refresh":
            self.query_one("#summary", Static).update(self.render_summary())
