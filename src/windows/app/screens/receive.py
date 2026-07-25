import asyncio
from textual.screen import Screen
from textual.app import ComposeResult
from textual.widgets import Header, Footer, Button, Static, ProgressBar, Label, TextArea
from textual.containers import Container, Vertical, Horizontal, VerticalScroll
from textual.message import Message

from src.windows.config import STYLES_DIR
from src.windows.modem.receptor import listen


TITLE_TEXT = """                                                     
▄     █████▄  ▄▄▄▄▄  ▄▄▄▄ ▄▄▄▄▄ ▄▄ ▄▄ ▄▄ ▄▄▄▄▄     ▄ 
 ▀▄   ██▄▄██▄ ██▄▄  ██▀▀▀ ██▄▄  ██ ██▄██ ██▄▄    ▄▀  
▄▀    ██   ██ ██▄▄▄ ▀████ ██▄▄▄ ██  ▀█▀  ██▄▄▄    ▀▄ 
                                                    
"""


class StatusMessage(Message):
    def __init__(self, text: str, progress: float = 0):
        self.text = text
        self.progress = progress
        super().__init__()


class DataMessage(Message):
    def __init__(self, text: str):
        self.text = text
        super().__init__()


class ReceiveScreen(Screen):
    CSS_PATH = [STYLES_DIR / "receive.tcss",]

    def compose(self):
        yield VerticalScroll(
            Container(
                Label(TITLE_TEXT, id="subtitle"),
                id="subtitle_container",
            ),
            Label(" Received data:", id="support_text"),
            Static(id="output"),
            Horizontal(
                Button("Start Listening", id="listen-btn", variant="primary"),
                Button("Stop", id="stop-btn", variant="error"),
                Button("Back", id="back-btn", variant="default"),
                id="button_row",
            ),
            ProgressBar(total=100, show_eta=False, id="progress", classes="progress-bar"),
            Label("Idle", id="status", classes="status-text"),
            id="receive_container",
        )
        
    def on_mount(self):
        self.output = self.query_one("#output", Static)
        self.status = self.query_one("#status", Label)
        self.listen_btn = self.query_one("#listen-btn", Button)
        self.stop_btn = self.query_one("#stop-btn", Button)
        self.progress = self.query_one("#progress", ProgressBar)
        self.progress.display = False
        self.stop_btn.disabled = True
        self._stop_flag = False

    def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "listen-btn":
            self.start_listening()
        elif event.button.id == "stop-btn":
            self._stop_flag = True
        elif event.button.id == "back-btn":
            self.app.pop_screen()

    def start_listening(self):
        self.listen_btn.disabled = True
        self.stop_btn.disabled = False
        self._stop_flag = False
        self.progress.display = True
        self.status.update("Listening for carrier...")
        self.run_worker(self.listening_worker())

    async def listening_worker(self):
        listen()
        self.listen_btn.disabled = False
        self.stop_btn.disabled = True
        self.progress.display = False

    def on_data_message(self, message: DataMessage):
        self.output.update(message.text)

    def on_status_message(self, message: StatusMessage):
        self.status.update(message.text)
        self.progress.update(progress=message.progress)
