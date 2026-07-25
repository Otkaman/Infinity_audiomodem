import asyncio
from textual.screen import Screen
from textual.app import ComposeResult
from textual.widgets import TextArea, Button, ProgressBar, Label
from textual.containers import VerticalScroll, Horizontal, Container
from textual.message import Message

from src.windows.config import STYLES_DIR
from src.windows.modem.send import transmit


TITLE_TEXT = r"""
▄     ▄█████ ▄▄▄▄▄ ▄▄  ▄▄ ▄▄▄▄      ▄ 
 ▀▄   ▀▀▀▄▄▄ ██▄▄  ███▄██ ██▀██   ▄▀  
▄▀    █████▀ ██▄▄▄ ██ ▀██ ████▀    ▀▄ """


class StatusMessage(Message):
    def __init__(self, text: str, progress: float = 0):
        self.text = text
        self.progress = progress
        super().__init__()


class TransmitScreen(Screen):
    CSS_PATH = [STYLES_DIR / "transmit.tcss",]

    def compose(self) -> ComposeResult:
        yield VerticalScroll(
            Container(
                Label(TITLE_TEXT, id="subtitle"),
                id="subtitle_container",
            ),
            Label(" Enter data to transmit:", id="support_text"),
            TextArea(id="data_input"),
            Horizontal(
                ProgressBar(total=100, show_eta=False, id="progress_bar"),
                Label(" Ready", id="status_text"),
                Horizontal(
                    Button("Send", id="send_btn", variant="primary"),
                    Button("Back", id="back_btn", variant="default"),
                    id="button_row",
                ),
            ),
            id="transmit_container",
        )

    def on_mount(self):
        self.progress = self.query_one("#progress_bar", ProgressBar)
        self.status = self.query_one("#status_text", Label)
        self.send_btn = self.query_one("#send_btn", Button)
        self.progress.display = False

    def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "send_btn":
            self.start_transmission()
        elif event.button.id == "back_btn":
            self.query_one("#data_input", TextArea).clear()
            self.status.update(" Ready")
            self.app.pop_screen()

    def start_transmission(self):
        data = self.query_one("#data_input", TextArea).text.strip()
        if not data:
            self.status.update(" No data to send!")
            return
        self.send_btn.disabled = True
        self.progress.display = True
        self.progress.update(total=100, progress=0)
        
        self.run_worker(self.transmission_worker(data), exclusive=True)

    async def transmission_worker(self, data: str):
        self.post_message(StatusMessage(" Transmitting...", 0))

        transmit(data)

        self.post_message(StatusMessage(" Transmission complete!", 100))
        self.send_btn.disabled = False

    def on_status_message(self, message: StatusMessage):
        self.progress.update(progress=message.progress)
        self.status.update(message.text)
        if message.progress == 100:
            self.progress.display = False
