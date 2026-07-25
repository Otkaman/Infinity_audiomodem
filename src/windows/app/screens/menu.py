from textual.screen import Screen
from textual.app import ComposeResult
from textual.widgets import Button, Label

from textual.containers import Container, Vertical, VerticalScroll

from src.windows.config import STYLES_DIR


# https://patorjk.com/software/taag/#p=display&f=ANSI+Compact&t=%3E+Infinity+Modem+%3C&x=none&v=4&h=4&w=80&we=false
TITLE_TEXT = r"""                                                                                           
                                                                                           
▄     ██ ▄▄  ▄▄ ▄▄▄▄▄ ▄▄ ▄▄  ▄▄ ▄▄ ▄▄▄▄▄▄ ▄▄ ▄▄   ██▄  ▄██  ▄▄▄  ▄▄▄▄  ▄▄▄▄▄ ▄▄   ▄▄     ▄ 
 ▀▄   ██ ███▄██ ██▄▄  ██ ███▄██ ██   ██   ▀███▀   ██ ▀▀ ██ ██▀██ ██▀██ ██▄▄  ██▀▄▀██   ▄▀  
▄▀    ██ ██ ▀██ ██    ██ ██ ▀██ ██   ██     █     ██    ██ ▀███▀ ████▀ ██▄▄▄ ██   ██    ▀▄ 
"""


class MenuScreen(Screen):
    CSS_PATH = [STYLES_DIR / "menu.tcss",]

    def compose(self) -> ComposeResult:
        yield VerticalScroll(
            Container(
                Label(TITLE_TEXT, id="title"),
                id="title_container",
            ),
            Vertical(
                Button("Send Data", id="send", variant="primary"),
                Button("Receive Data", id="receive", variant="primary"),
                Button("Calibrate", id="calibrate", variant="default"),
                id="button_container_vertical",
            )
        )

    def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "send":
            self.app.push_screen("transmit")
        elif event.button.id == "receive":
            self.app.push_screen("receive")
        elif event.button.id == "calibrate":
            self.app.push_screen("calibrate")
