from textual.screen import Screen
from textual.widgets import Static
import os, json, redis
from textual import events

class SandboxScreen(Screen):
    def compose(self):
        yield Static("🧩 Sandbox Results\n", id="title")
        yield Static(self.render_list(), id="list")

    def render_list(self):
        try:
            r = redis.Redis(host=os.environ.get("REDIS_HOST","redis"), port=6379, decode_responses=True)
            items = r.xrevrange("stream:sandbox_results", count=10)
            lines = []
            for _id, msg in items:
                data = msg.get("data") or msg
                if isinstance(data, str):
                    try:
                        data = json.loads(data)
                    except:
                        data = {"raw": data}
                t = data.get("target","?")
                st = data.get("status","?")
                conf = data.get("confidence","?")
                ts = data.get("timestamp", _id)
                lines.append(f"{ts} | {t} | {st} | {conf}")
            return "\n".join(lines) if lines else "No sandbox results yet."
        except Exception:
            # fallback to file-based results
            try:
                p = "/app/data/results"
                files = sorted(os.listdir(p))[-10:]
                out=[]
                for f in files:
                    try:
                        j=json.load(open(os.path.join(p,f)))
                        out.append(f"{j.get('timestamp','?')} | {j.get('target','?')} | {j.get('status','?')} | {j.get('confidence','?')}")
                    except:
                        out.append(f)
                return "\n".join(out) if out else "No local results."
            except Exception:
                return "No results available."

    async def on_message(self, event: events.Message) -> None:
        if event._text == "refresh":
            self.query_one("#list", Static).update(self.render_list())
