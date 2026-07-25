import asyncio
import numpy as np
import sounddevice as sd
import zlib                     # <-- добавлено

from textual.screen import Screen
from textual.app import ComposeResult
from textual.widgets import TextArea, Button, ProgressBar, Label
from textual.containers import VerticalScroll, Horizontal, Container
from textual.message import Message

from src.windows.config import STYLES_DIR

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
    CSS_PATH = [STYLES_DIR / "transmit.tcss"]

    # Константы для звука
    SAMPLE_RATE = 48000
    DURATION = 0.05
    FREQ_0 = 1800
    FREQ_1 = 2000
    HEADER = '10101010'

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

    # ----- вспомогательные генераторы сигнала -----
    @staticmethod
    def _generate_tone(bit: str) -> np.ndarray:
        t = np.linspace(0, TransmitScreen.DURATION,
                        int(TransmitScreen.SAMPLE_RATE * TransmitScreen.DURATION),
                        endpoint=False)
        freq = TransmitScreen.FREQ_1 if bit == '1' else TransmitScreen.FREQ_0
        return np.sin(freq * t * 2 * np.pi)

    @classmethod
    def _bytes_to_signal(cls, data: bytes) -> np.ndarray:
        """Преобразует байты в битовую строку и генерирует сигнал."""
        bits = ''.join(format(b, '08b') for b in data)
        tones = [cls._generate_tone(bit) for bit in bits]
        return np.concatenate(tones) if tones else np.array([])

    @classmethod
    def _build_full_signal(cls, text: str) -> np.ndarray:
        """
        Формирует полный сигнал с заголовком и сжатым содержимым.
        Структура payload: имя (utf-8) + b'\x00' + сжатые данные.
        """
        # Кодируем текст в UTF-8 и сжимаем
        text_bytes = text.encode('utf-8')
        compressed = zlib.compress(text_bytes)

        # Имя для пакета (можно изменить, например "message")
        name = b"message"
        payload = name + b'\x00' + compressed

        # Строим заголовок и данные
        header_signal = np.concatenate([cls._generate_tone(bit) for bit in cls.HEADER])
        data_signal = cls._bytes_to_signal(payload)
        return np.concatenate((header_signal, data_signal))

    # ----- асинхронная передача с прогрессом -----
    async def transmission_worker(self, data: str):
        # 1. Генерация сигнала (теперь со сжатием)
        self.post_message(StatusMessage(" Generating compressed signal...", 0))
        signal = self._build_full_signal(data).astype(np.float32)
        total_duration = len(signal) / self.SAMPLE_RATE

        # 2. Блокирующее воспроизведение в отдельном потоке
        def play_audio(sig, sr):
            stream = sd.OutputStream(samplerate=sr, channels=1, dtype='float32')
            stream.start()
            stream.write(sig)
            return stream

        try:
            stream = await asyncio.to_thread(play_audio, signal, self.SAMPLE_RATE)
        except Exception as e:
            self.post_message(StatusMessage(f" Audio error: {str(e)}", 0))
            self.send_btn.disabled = False
            return

        # 3. Цикл обновления прогресса
        while stream.active:
            current_time = stream.time
            if current_time and current_time > 0:
                progress = min(current_time / total_duration * 100, 100)
            else:
                progress = 0
            self.post_message(
                StatusMessage(f" Transmitting... {progress:.0f}%", progress)
            )
            await asyncio.sleep(0.1)

        # 4. Завершение
        stream.close()
        self.post_message(StatusMessage(" Transmission complete!", 100))
        self.send_btn.disabled = False

    def on_status_message(self, message: StatusMessage):
        self.progress.update(progress=message.progress)
        self.status.update(message.text)
        if message.progress >= 100:
            self.progress.display = False
