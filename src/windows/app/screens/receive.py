import asyncio
import time
import numpy as np
import sounddevice as sd
from scipy.fft import fft

from textual.screen import Screen
from textual.app import ComposeResult
from textual.widgets import Header, Footer, Button, ProgressBar, Label, RichLog
from textual.containers import VerticalScroll, Horizontal, Container
from textual.message import Message

from src.windows.config import STYLES_DIR

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
    CSS_PATH = [STYLES_DIR / "receive.tcss"]

    def compose(self) -> ComposeResult:
        yield VerticalScroll(
            Container(
                Label(TITLE_TEXT, id="subtitle"),
                id="subtitle_container",
            ),
            Label(" Received data:", id="support_text"),
            RichLog(id="output", markup=False, auto_scroll=True),
            Horizontal(
                Button("Start Listening", id="listen-btn", variant="primary"),
                Button("Stop", id="stop-btn", variant="error"),
                Button("Back", id="back-btn", variant="default"),
                id="button_row",
            ),
            ProgressBar(total=100, show_eta=False, id="progress"),
            Label("Idle", id="status"),
            id="receive_container",
        )

    def on_mount(self) -> None:
        self.output: RichLog = self.query_one("#output", RichLog)
        self.status: Label = self.query_one("#status", Label)
        self.listen_btn: Button = self.query_one("#listen-btn", Button)
        self.stop_btn: Button = self.query_one("#stop-btn", Button)
        self.progress: ProgressBar = self.query_one("#progress", ProgressBar)

        self.progress.display = False
        self.stop_btn.disabled = True
        self._stop_flag = False
        self._task = None

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "listen-btn":
            self.start_listening()
        elif event.button.id == "stop-btn":
            self._stop_flag = True
            self.status.update("Stopping...")
        elif event.button.id == "back-btn":
            if self._task and not self._task.done():
                self._stop_flag = True
            self.app.pop_screen()

    def start_listening(self) -> None:
        self.listen_btn.disabled = True
        self.stop_btn.disabled = False
        self._stop_flag = False
        self.progress.display = True
        self.status.update("Listening for carrier...")
        self.output.clear()
        self._task = asyncio.create_task(self.listening_worker())

    async def listening_worker(self) -> None:
        """Run the synchronous listening in a thread."""
        try:
            await asyncio.to_thread(self._sync_listen)
        finally:
            self.listen_btn.disabled = False
            self.stop_btn.disabled = True
            self.progress.display = False
            self.status.update("Idle")

    def _sync_listen(self) -> None:
        """Blocking audio capture loop that sends recognized characters to the UI."""
        sample_rate = 48000
        duration = 0.1
        chunk_size = int(sample_rate * duration)
        freq_0 = 1800
        freq_1 = 2000
        tolerance = 80
        header = '10101010'

        bit_buffer = ''
        received_bits = ''
        receiving = False

        def detect_frequency(signal: np.ndarray) -> float:
            n = len(signal)
            fft_vals = fft(signal)
            freqs = np.fft.fftfreq(n, 1 / sample_rate)
            peak_freq = abs(freqs[np.argmax(np.abs(fft_vals))])
            return peak_freq

        def frequency_to_bit(freq: float) -> str | None:
            if abs(freq - freq_0) < tolerance:
                return '0'
            elif abs(freq - freq_1) < tolerance:
                return '1'
            return None

        def callback(indata, frames, time_info, status):
            nonlocal bit_buffer, receiving, received_bits
            if status:
                print(f"Stream status: {status}")
            chunk = indata[:, 0]
            freq = detect_frequency(chunk)
            bit = frequency_to_bit(freq)
            if bit:
                bit_buffer += bit
                if not receiving and bit_buffer.endswith(header):
                    receiving = True
                    received_bits = ''
                    # Send status update
                    self.app.call_from_thread(
                        self.post_message,
                        StatusMessage("Header detected – receiving data", 50)
                    )
                elif receiving:
                    received_bits += bit
                    if len(received_bits) % 8 == 0:
                        byte = received_bits[-8:]
                        try:
                            char = chr(int(byte, 2))
                            self.app.call_from_thread(
                                self.post_message,
                                DataMessage(char)
                            )
                        except (ValueError, OverflowError):
                            pass  # ignore malformed bytes

        stream = sd.InputStream(
            callback=callback,
            samplerate=sample_rate,
            channels=1,
            blocksize=chunk_size
        )
        stream.start()
        try:
            while not self._stop_flag:
                time.sleep(0.1)
        finally:
            stream.stop()
            stream.close()

    def on_data_message(self, message: DataMessage) -> None:
        """Append received character to the scrollable output."""
        self.output.write(message.text)

    def on_status_message(self, message: StatusMessage) -> None:
        """Update status label and progress bar."""
        self.status.update(message.text)
        self.progress.update(progress=message.progress)
