import asyncio
from textual.screen import Screen
from textual.app import ComposeResult
from textual.widgets import Header, Footer, Button, Label
from textual.containers import Vertical, Horizontal, Grid
from textual.message import Message


class CalibrateScreen(Screen):
    CSS_PATH = ["../styles/calibrate.tcss"]

    FREQS = [3000, 4000, 5000, 6000, 7000, 8000, 9000, 10000]

    class FreqStatus(Message):
        def __init__(self, freq: int, status: str):
            self.freq = freq
            self.status = status
            super().__init__()

    def compose(self):
        yield Header(show_clock=True)
        with Vertical(classes="calibrate-container"):
            yield Label("Calibration", classes="title")
            with Horizontal(classes="role-buttons"):
                yield Button("Transmitter", id="tx-role", variant="primary")
                yield Button("Receiver", id="rx-role", variant="primary")
            yield Label("Frequency Status:", classes="prompt")
            yield Grid(
                *[Label(f"{f} Hz", classes="freq-label") for f in self.FREQS],
                id="freq-grid", classes="freq-grid"
            )
            with Horizontal(classes="button-row"):
                yield Button("Start Calibration", id="start-cal", variant="success")
                yield Button("Back", id="back-btn", variant="default")
            yield Label("Select role and start calibration", id="status", classes="status-text")
        yield Footer()

    def on_mount(self):
        self.freq_labels = list(self.query("#freq-grid Label"))
        self.status = self.query_one("#status", Label)
        self.start_btn = self.query_one("#start-cal", Button)
        self.tx_btn = self.query_one("#tx-role", Button)
        self.rx_btn = self.query_one("#rx-role", Button)
        self.selected_role = None

    def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "tx-role":
            self.selected_role = "tx"
            self.tx_btn.variant = "success"
            self.rx_btn.variant = "primary"
        elif event.button.id == "rx-role":
            self.selected_role = "rx"
            self.rx_btn.variant = "success"
            self.tx_btn.variant = "primary"
        elif event.button.id == "start-cal":
            if not self.selected_role:
                self.status.update("Please select a role first!")
                return
            self.start_calibration()
        elif event.button.id == "back-btn":
            self.app.pop_screen()

    def start_calibration(self):
        self.start_btn.disabled = True
        self.status.update("Calibrating...")
        for label in self.freq_labels:
            label.update("")
        self.run_worker(self.calibration_worker(), exclusive=True)

    async def calibration_worker(self):
        for freq in self.FREQS:
            await asyncio.sleep(0.5)
            # Имитация результата
            if freq <= 5000:
                status = "good signal"
            elif freq <= 8000:
                status = "too weak"
            else:
                status = "good signal"
            self.post_message(self.FreqStatus(freq, status))
        self.post_message(self.FreqStatus(0, "done"))

    def on_freq_status(self, message: FreqStatus):
        if message.freq == 0 and message.status == "done":
            self.status.update("Calibration complete. Adjust volume if needed.")
            self.start_btn.disabled = False
            return
        idx = self.FREQS.index(message.freq)
        label = self.freq_labels[idx]
        label.update(f"{message.freq} Hz: {message.status}")
        label.remove_class("good", "weak", "noisy")
        if "good" in message.status:
            label.add_class("good")
        else:
            label.add_class("weak")
