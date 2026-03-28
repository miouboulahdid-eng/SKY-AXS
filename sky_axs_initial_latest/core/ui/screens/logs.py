from textual.screen import Screen
from textual.widgets import Static
import os, tailer
from textual import events

class LogsScreen(Screen):
    def compose(self):
        yield Static("📜 Logs (latest)\n", id="title")
        yield Static(self.render_logs(), id="logs")

    def render_logs(self, lines=50):
        try:
            p="/app/data/logs/axs.log"
            if os.path.exists(p):
                # tailer may not be installed; fallback
                try:
                    return "".join(tailer.tail(open(p), lines))
                except Exception:
                    with open(p) as f:
                        return "".join(f.readlines()[-lines:])
            else:
                return "Log file not found (/app/data/logs/axs.log)"
        except Exception as e:
            return f"Cannot read logs: {e}"

    async def on_message(self, event: events.Message) -> None:
        if event._text == "refresh":
            self.query_one("#logs", Static).update(self.render_logs())
