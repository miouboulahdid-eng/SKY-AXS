#!/usr/bin/env python3
from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, Static
from textual.containers import Container, Horizontal
from rich.panel import Panel

# استيراد الشاشات الفعلية من مشروعك
from core.ui.screens.dashboard import DashboardScreen
from core.ui.screens.sandbox import SandboxScreen
from core.ui.screens.ai_analyzer import AIAnalyzerScreen
from core.ui.screens.system import SystemScreen
from core.ui.screens.decision import DecisionScreen
from core.ui.screens.logs import LogsScreen

class MainApp(App):
    TITLE = "AXS Terminal Interface"
    SUB_TITLE = "AI-Powered Security Framework"
    CSS_PATH = None

    def compose(self) -> ComposeResult:
        yield Header()
        yield Footer()
        yield Container(
            Static("[bold cyan]Welcome to AXS Security Terminal[/bold cyan]\nUse ← → arrows or [1–6] to switch modules.", id="title"),
            Static("", id="content"),
            Static("", id="nav"),
        )

    def on_mount(self):
        # تعريف الشاشات بشكل ثابت
        self.screens = {
            "dashboard": DashboardScreen(),
            "sandbox": SandboxScreen(),
            "ai": AIAnalyzerScreen(),
            "system": SystemScreen(),
            "decision": DecisionScreen(),
            "logs": LogsScreen(),
        }
        self.screen_order = list(self.screens.keys())
        self.current_index = 0
        self.show_screen("dashboard")

    def show_screen(self, name: str):
        """عرض شاشة معينة"""
        screen = self.screens.get(name)
        content = self.query_one("#content", Static)
        content.update(Panel(f"[bold green]{name.upper()} SCREEN[/bold green]\n\n{screen.render() if hasattr(screen, 'render') else ''}"))
        self.query_one("#nav", Static).update(
            "[b]Navigation:[/b]  [1]Dashboard  [2]Sandbox  [3]AI  [4]System  [5]Decision  [6]Logs"
        )

    def on_key(self, event):
        key = event.key.lower()
        if key in ["left", "right"]:
            if key == "left":
                self.current_index = (self.current_index - 1) % len(self.screen_order)
            else:
                self.current_index = (self.current_index + 1) % len(self.screen_order)
            self.show_screen(self.screen_order[self.current_index])
        elif key in [str(i) for i in range(1, len(self.screen_order) + 1)]:
            idx = int(key) - 1
            self.current_index = idx
            self.show_screen(self.screen_order[idx])

if __name__ == "__main__":
    app = MainApp()
    app.run()
