import asyncio
import os
import sys
import time
import threading

import numpy as np

from textual.app import App, ComposeResult
from textual.screen import Screen
from textual.widgets import (
    Header, Footer, Button, Static, Label, Input, Select, ProgressBar,
    RichLog, TextArea, ContentSwitcher,
)
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.reactive import reactive
from textual import work

from protocol import (
    encode_with_preset, decode_with_preset,
    detect_end_marker, build_end_marker_wave,
    FS, PRESETS, PRESET_NAMES,
)

STYLES_DIR = os.path.join(os.path.dirname(__file__), "app", "styles")

LOGO = """
▄     █████▄  ▄▄▄▄▄  ▄▄▄▄ ▄▄▄▄▄ ▄▄ ▄▄ ▄▄ ▄▄▄▄▄     ▄ 
 ▀▄   ██▄▄██▄ ██▄▄  ██▀▀▀ ██▄▄  ██ ██▄██ ██▄▄    ▄▀  
▄▀    ██   ██ ██▄▄▄ ▀████ ██▄▄▄ ██  ▀█▀  ██▄▄▄    ▀▄ 
                                                      """


def format_size(n: int) -> str:
    for unit in ("Б", "КБ", "МБ"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} ГБ"


def format_time(sec: float) -> str:
    if sec < 60:
        return f"{sec:.0f} сек"
    if sec < 3600:
        return f"{sec/60:.0f} мин {sec%60:.0f} сек"
    return f"{sec/3600:.1f} ч"


# ---------------------------------------------------------------------------
# Menu
# ---------------------------------------------------------------------------

class MenuScreen(Screen):

    def compose(self) -> ComposeResult:
        with Vertical(id="menu-container"):
            yield Static(LOGO, id="title")
            with Vertical(id="menu-buttons"):
                yield Button("  📤  Отправить файл", variant="primary", id="send-btn", classes="-send-btn")
                yield Button("  📥  Принять файл", variant="success", id="receive-btn", classes="-receive-btn")
                yield Button("  ❌  Выход", variant="default", id="quit-btn", classes="-back-btn")
            yield Label("v0.2  |  FSK-модем через динамик и микрофон", id="footer-label")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "send-btn":
            self.app.push_screen("send")
        elif event.button.id == "receive-btn":
            self.app.push_screen("receive")
        elif event.button.id == "quit-btn":
            self.app.exit()


# ---------------------------------------------------------------------------
# Send Screen
# ---------------------------------------------------------------------------

class SendScreen(Screen):

    BINDINGS = [("escape", "go_back", "Назад")]

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static("📤 Отправка файла", id="title")
            with Container(id="input-area"):
                yield Input(placeholder="Путь к файлу (или текст ниже)", id="file-input")
                yield TextArea(id="text-input", text="", soft_wrap=False)
                yield Select(
                    [(p.capitalize(), p) for p in PRESET_NAMES],
                    prompt="Пресет",
                    id="preset-select",
                    value="normal",
                )
                yield Label(id="preset-desc", classes="-status-ok")
            yield ProgressBar(total=100, show_eta=False, id="progress")
            yield RichLog(id="log-widget", highlight=True, markup=True)
            with Horizontal():
                yield Button("  ▶  Отправить", variant="primary", id="send-start-btn", classes="-send-btn")
                yield Button("  ←  Назад", variant="default", id="back-btn", classes="-back-btn")
            yield Label("", id="status-bar")
        self._stop_flag = False
        self._playing = False

    def on_mount(self) -> None:
        self.log_widget = self.query_one("#log-widget", RichLog)
        self.progress = self.query_one("#progress", ProgressBar)
        self.status = self.query_one("#status-bar", Label)
        self.file_input = self.query_one("#file-input", Input)
        self.text_input = self.query_one("#text-input", TextArea)
        self.preset_select = self.query_one("#preset-select", Select)
        self.preset_desc = self.query_one("#preset-desc", Label)
        self.send_btn = self.query_one("#send-start-btn", Button)
        self.progress.display = False
        self._update_preset_desc()

    def _update_preset_desc(self) -> None:
        p = self.preset_select.value
        if p and p in PRESETS:
            info = PRESETS[p]
            speed = 1000 / info["symbol_ms"]
            if not info["uart"]:
                speed *= 1
            size = 20 * 1024
            bits = size * 8
            if info["uart"]:
                bits = size * 10
            est = bits / (speed * (1 if info["uart"] else 1))
            self.preset_desc.update(f"{info['desc']}  |  ~{format_time(est)} для 20 КБ")

    def on_select_changed(self, event: Select.Changed) -> None:
        self._update_preset_desc()

    def action_go_back(self) -> None:
        self._stop_flag = True
        self.app.pop_screen()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "back-btn":
            self.action_go_back()
        elif event.button.id == "send-start-btn":
            self._start_send()

    def _start_send(self) -> None:
        file_path = self.file_input.value.strip()
        text = self.text_input.text.strip()
        preset = self.preset_select.value or "normal"

        if not file_path and not text:
            self.log_widget.write("[red]Укажи файл или текст[/red]")
            return

        self.send_btn.disabled = True
        self.progress.display = True
        self.progress.update(progress=0)
        self.log_widget.clear()
        self.log_widget.write(f"[green]▶ Пресет: {preset}[/green]")

        if text:
            payload = text.encode("utf-8")
            filename = "text.txt"
            self.log_widget.write(f"Текст: {len(payload)} байт")
        else:
            if not os.path.exists(file_path):
                self.log_widget.write(f"[red]Файл не найден: {file_path}[/red]")
                self.send_btn.disabled = False
                return
            with open(file_path, "rb") as f:
                payload = f.read()
            filename = os.path.basename(file_path)
            self.log_widget.write(f"Файл: {filename} ({format_size(len(payload))})")

        self.log_widget.write(f"[yellow]Кодирование...[/yellow]")
        self.progress.update(progress=30)
        self.status.update("Кодирование...")

        def encode_and_play():
            try:
                wave = encode_with_preset(filename, payload, preset=preset)
                duration = len(wave) / FS
                self.app.call_from_thread(self.log_widget.write,
                    f"[green]Сигнал: {duration:.0f} сек ({format_time(duration)})[/green]")
                self.app.call_from_thread(self.progress.update, progress=60)
                self.app.call_from_thread(self.status.update, "Воспроизведение...")
                self.app.call_from_thread(self.log_widget.write, "[yellow]▶ Воспроизведение...[/yellow]")

                import sounddevice as sd
                sd.play(wave, FS)
                self._playing = True

                # прогресс во время проигрывания
                while True:
                    try:
                        stream = sd.get_stream()
                        if stream is None or not stream.active:
                            break
                    except Exception:
                        break
                    if self._stop_flag:
                        sd.stop()
                        break
                    time.sleep(0.5)
                    pct = min(90, 60 + int(sd.get_stream().time / duration * 30))
                    self.app.call_from_thread(self.progress.update, progress=pct)

                sd.wait()
                self._playing = False
                self.app.call_from_thread(self.progress.update, progress=100)
                self.app.call_from_thread(self.status.update, "Готово ✓")
                self.app.call_from_thread(self.log_widget.write, "[green]✓ Передача завершена[/green]")
            except Exception as e:
                self.app.call_from_thread(self.log_widget.write, f"[red]Ошибка: {e}[/red]")
            finally:
                self.app.call_from_thread(lambda: setattr(self.send_btn, "disabled", False))
                self.app.call_from_thread(lambda: self.status.update(""))

        thread = threading.Thread(target=encode_and_play, daemon=True)
        thread.start()


# ---------------------------------------------------------------------------
# Receive Screen
# ---------------------------------------------------------------------------

class ReceiveScreen(Screen):

    BINDINGS = [("escape", "go_back", "Назад")]

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static("📥 Приём файла", id="title")
            with Container(id="input-area"):
                yield Select(
                    [(p.capitalize(), p) for p in PRESET_NAMES],
                    prompt="Пресет",
                    id="preset-select-rx",
                    value="normal",
                )
                yield Input(placeholder="Папка для сохранения (по умолчанию .)", id="out-dir", value=".")
                yield Label(id="file-info-received", classes="-status-ok")
            yield ProgressBar(total=100, show_eta=False, id="progress-rx")
            yield RichLog(id="log-widget-rx", highlight=True, markup=True)
            with Horizontal():
                yield Button("  🎙  Слушать", variant="success", id="listen-btn", classes="-receive-btn")
                yield Button("  ⏹  Стоп", variant="error", id="stop-btn", classes="-back-btn")
                yield Button("  ←  Назад", variant="default", id="back-btn", classes="-back-btn")
            yield Label("", id="status-bar-rx")
        self._stop_flag = False
        self._listening = False

    def on_mount(self) -> None:
        self.log = self.query_one("#log-widget-rx", RichLog)
        self.progress = self.query_one("#progress-rx", ProgressBar)
        self.status = self.query_one("#status-bar-rx", Label)
        self.file_info = self.query_one("#file-info-received", Label)
        self.preset_select = self.query_one("#preset-select-rx", Select)
        self.out_dir = self.query_one("#out-dir", Input)
        self.listen_btn = self.query_one("#listen-btn", Button)
        self.stop_btn = self.query_one("#stop-btn", Button)
        self.progress.display = False
        self.stop_btn.disabled = True

    def action_go_back(self) -> None:
        self._stop_flag = True
        self.app.pop_screen()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "back-btn":
            self.action_go_back()
        elif event.button.id == "listen-btn":
            self._start_listen()
        elif event.button.id == "stop-btn":
            self._stop_flag = True

    def _start_listen(self) -> None:
        preset = self.preset_select.value or "normal"
        out = self.out_dir.value.strip() or "."

        self._stop_flag = False
        self.listen_btn.disabled = True
        self.stop_btn.disabled = False
        self.progress.display = True
        self.progress.update(progress=0)
        self.log.clear()
        self.file_info.update("")
        self.log.write(f"[green]▶ Пресет: {preset}[/green]")
        self.log.write(f"[yellow]Слушаю микрофон... (Ctrl+C / Стоп для остановки)[/yellow]")
        self.status.update("Слушаю...")

        def listen_thread():
            try:
                import sounddevice as sd
                fs = FS
                chunk_seconds = 3.0
                chunk_samples = max(int(chunk_seconds * fs), 1)
                marker = build_end_marker_wave(fs=fs)
                marker_len = len(marker)
                total = []

                self.app.call_from_thread(self.log.write, "[yellow]Запись... жду маркер завершения[/yellow]")

                while not self._stop_flag:
                    chunk = sd.rec(chunk_samples, samplerate=fs, channels=1, dtype="float32")
                    sd.wait()
                    audio = chunk.flatten()
                    total.append(audio)
                    combined = np.concatenate(total)

                    elapsed = len(combined) / fs
                    pct = min(95, int(elapsed / 60 * 5))
                    self.app.call_from_thread(self.progress.update, progress=pct)
                    self.app.call_from_thread(self.status.update, f"Запись... {elapsed:.0f} сек")

                    if len(combined) >= marker_len:
                        tail = combined[-marker_len:]
                        if detect_end_marker(tail, fs=fs):
                            self.app.call_from_thread(self.log.write, "[green]✓ Маркер завершения обнаружен[/green]")
                            audio_data = combined[:-marker_len]
                            break

                    if len(combined) > fs * 300:
                        self.app.call_from_thread(self.log.write, "[red]Таймаут 5 мин[/red]")
                        audio_data = combined
                        break
                else:
                    return

                self.app.call_from_thread(self.log.write, "[yellow]Декодирование...[/yellow]")
                self.app.call_from_thread(self.progress.update, progress=96)
                self.app.call_from_thread(self.status.update, "Декодирование...")

                result = decode_with_preset(audio_data, preset=preset)
                if result is None:
                    self.app.call_from_thread(self.log.write, "[red]✗ Не удалось декодировать[/red]")
                    self.app.call_from_thread(self.status.update, "Ошибка")
                    return

                filename, payload = result
                os.makedirs(out, exist_ok=True)
                out_path = os.path.join(out, filename)
                with open(out_path, "wb") as f:
                    f.write(payload)

                self.app.call_from_thread(self.progress.update, progress=100)
                self.app.call_from_thread(self.status.update, "Готово ✓")
                self.app.call_from_thread(self.log.write, f"[green]✓ Получен: {filename} ({format_size(len(payload))})[/green]")
                self.app.call_from_thread(self.file_info.update,
                    f"📁 {filename}  |  {format_size(len(payload))}  |  сохранён в {out_path}")
                self.app.call_from_thread(self.log.write, f"[green]Сохранён: {out_path}[/green]")

            except Exception as e:
                self.app.call_from_thread(self.log.write, f"[red]Ошибка: {e}[/red]")
            finally:
                self.app.call_from_thread(lambda: setattr(self.listen_btn, "disabled", False))
                self.app.call_from_thread(lambda: setattr(self.stop_btn, "disabled", True))
                self.app.call_from_thread(lambda: self.status.update(""))

        thread = threading.Thread(target=listen_thread, daemon=True)
        thread.start()


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

class InfinityModemApp(App):

    CSS_PATH = [os.path.join(STYLES_DIR, "main.tcss")]
    SCREENS = {
        "menu": MenuScreen,
        "send": SendScreen,
        "receive": ReceiveScreen,
    }
    BINDINGS = [("ctrl+q", "quit", "Выход")]

    def on_mount(self) -> None:
        self.push_screen("menu")


def main():
    app = InfinityModemApp()
    app.run()


if __name__ == "__main__":
    main()
