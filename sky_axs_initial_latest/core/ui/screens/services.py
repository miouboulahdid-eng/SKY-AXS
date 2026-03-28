from textual.screen import Screen
from textual.widgets import Static, ListView, ListItem
import docker

class ServicesScreen(Screen):
    def compose(self):
        yield Static("🧰 إدارة الحاويات", classes="title")
        self.list_view = ListView()
        yield self.list_view

    async def on_mount(self):
        self.list_view.clear()
        client = docker.from_env()
        containers = client.containers.list(all=True)
        for c in containers:
            name = c.name
            status = c.status
            self.list_view.append(ListItem(Static(f"📦 {name} [{status}]")))
