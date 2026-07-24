#!/usr/bin/env python3
"""
audiotool — консольная утилита для записи звука с аудиоканала,
автоматической остановки записи по «стоп-частоте» и сохранения
полученных аудиофрагментов в отдельные файлы.

Команды:
    record   Считывать звук с микрофона/линейного входа до появления
             стоп-частоты. Во время записи показывается прогресс-бар.
    save     Сохранить последний (или указанный) записанный фрагмент
             в новый файл в целевой папке.
    list     Показать список сохранённых фрагментов в папке.

Запуск без аргументов (или с -h/--help) показывает эту справку.

Зависимости: numpy, sounddevice, soundfile
    pip install numpy sounddevice soundfile
Системная библиотека (для sounddevice/PortAudio):
    sudo apt-get install libportaudio2
"""

import argparse
import datetime
import json
import os
import shutil
import sys
import tempfile
import threading
import time

import numpy as np

try:
    import sounddevice as sd
except (ImportError, OSError):
    # ImportError — пакет не установлен (pip install sounddevice)
    # OSError — не найдена системная библиотека PortAudio
    #           (sudo apt-get install libportaudio2)
    sd = None

try:
    import soundfile as sf
except (ImportError, OSError):
    sf = None


STATE_FILE = os.path.join(tempfile.gettempdir(), "audiotool_last_fragment.json")
DEFAULT_FOLDER = os.path.join(os.path.expanduser("~"), "audio_fragments")


# --------------------------------------------------------------------------- #
# Разбор аргументов командной строки
# --------------------------------------------------------------------------- #

def build_parser():
    parser = argparse.ArgumentParser(
        prog="audiotool",
        description=(
            "Консольная утилита для записи звука с аудиоканала.\n"
            "Запись автоматически останавливается, когда во входном сигнале\n"
            "обнаруживается тон известной 'стоп-частоты'."
        ),
        epilog=(
            "Примеры использования:\n"
            "  audiotool record\n"
            "      Начать запись со стоп-частотой по умолчанию (1000 Гц).\n"
            "  audiotool record --stop-freq 2000 --tolerance 15 --min-duration 0.5\n"
            "      Запись остановится, встретив тон ~2000 Гц длительностью от 0.5с.\n"
            "  audiotool record --list-devices\n"
            "      Показать список доступных аудио-устройств.\n"
            "  audiotool save --name my_clip\n"
            "      Сохранить последний записанный фрагмент как 'my_clip.wav'.\n"
            "  audiotool list\n"
            "      Показать список сохранённых фрагментов.\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    sub = parser.add_subparsers(dest="command", metavar="{record,save,list}")

    # ------------------------------------------------------------------- #
    # record
    # ------------------------------------------------------------------- #
    p_record = sub.add_parser(
        "record",
        help="Начать считывание звука с аудио-канала до стоп-частоты",
        description=(
            "Начинает считывание аудио с выбранного входного устройства.\n"
            "Во время записи отображается прогресс-бар (прошедшее время,\n"
            "уровень сигнала и текущая пиковая частота). Запись автоматически\n"
            "завершается, как только во входном сигнале в течение\n"
            "--min-duration секунд подряд обнаруживается тон на частоте\n"
            "--stop-freq (± --tolerance Гц)."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_record.add_argument(
        "-d", "--device", type=str, default=None,
        help="Индекс или имя аудио-устройства ввода "
             "(по умолчанию — системное устройство по умолчанию)",
    )
    p_record.add_argument(
        "--list-devices", action="store_true",
        help="Показать список доступных аудио-устройств и выйти",
    )
    p_record.add_argument(
        "-r", "--samplerate", type=int, default=44100,
        help="Частота дискретизации, Гц (по умолчанию 44100)",
    )
    p_record.add_argument(
        "-c", "--channels", type=int, default=1,
        help="Количество каналов записи (по умолчанию 1 — моно)",
    )
    p_record.add_argument(
        "-f", "--stop-freq", type=float, default=1000.0,
        help="Стоп-частота в Гц: тон на этой частоте останавливает запись "
             "(по умолчанию 1000)",
    )
    p_record.add_argument(
        "--tolerance", type=float, default=20.0,
        help="Допустимое отклонение от стоп-частоты, Гц (по умолчанию 20)",
    )
    p_record.add_argument(
        "--min-duration", type=float, default=0.3,
        help="Минимальная длительность непрерывного тона стоп-частоты, "
             "после которой запись останавливается, сек (по умолчанию 0.3)",
    )
    p_record.add_argument(
        "--threshold", type=float, default=0.02,
        help="Порог амплитуды для распознавания тона стоп-частоты, "
             "значение от 0 до 1 (по умолчанию 0.02); увеличьте, если "
             "запись останавливается на фоновом шуме",
    )
    p_record.add_argument(
        "--max-duration", type=float, default=3600.0,
        help="Максимальная длительность записи, сек — защита от "
             "бесконечной записи, если стоп-частота не встретится "
             "(по умолчанию 3600)",
    )
    p_record.add_argument(
        "-o", "--output", type=str, default=None,
        help="Путь для файла записи (по умолчанию — временный файл "
             "во временной папке системы)",
    )

    # ------------------------------------------------------------------- #
    # save
    # ------------------------------------------------------------------- #
    p_save = sub.add_parser(
        "save",
        help="Сохранить записанный аудио-фрагмент в новый файл в папке",
        description=(
            "Копирует последний записанный командой 'record' аудио-фрагмент\n"
            "(либо файл, указанный через --input) в целевую папку под новым\n"
            "именем."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_save.add_argument(
        "-i", "--input", type=str, default=None,
        help="Путь к аудио-фрагменту для сохранения "
             "(по умолчанию — последний записанный фрагмент)",
    )
    p_save.add_argument(
        "-o", "--folder", type=str, default=DEFAULT_FOLDER,
        help=f"Папка назначения (по умолчанию {DEFAULT_FOLDER})",
    )
    p_save.add_argument(
        "-n", "--name", type=str, default=None,
        help="Имя файла без расширения (по умолчанию — метка времени)",
    )
    p_save.add_argument(
        "--keep", action="store_true",
        help="Не удалять исходный временный файл после копирования",
    )

    # ------------------------------------------------------------------- #
    # list
    # ------------------------------------------------------------------- #
    p_list = sub.add_parser(
        "list",
        help="Показать список сохранённых аудио-фрагментов",
        description="Показывает список аудиофайлов, сохранённых в указанной папке.",
    )
    p_list.add_argument(
        "-o", "--folder", type=str, default=DEFAULT_FOLDER,
        help=f"Папка с фрагментами (по умолчанию {DEFAULT_FOLDER})",
    )

    return parser


# --------------------------------------------------------------------------- #
# Анализ звука
# --------------------------------------------------------------------------- #

def rms(chunk):
    """Среднеквадратичный уровень сигнала (0..~1 для нормализованного аудио)."""
    if chunk.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(np.square(chunk))))


def dominant_frequency(chunk, samplerate):
    """
    Возвращает (пиковая_частота_Гц, нормированная_амплитуда_пика) для
    одноканального блока сэмплов chunk.
    """
    if chunk.size == 0:
        return 0.0, 0.0
    window = np.hanning(len(chunk))
    spec = np.fft.rfft(chunk * window)
    mag = np.abs(spec)
    if mag.size == 0:
        return 0.0, 0.0
    freqs = np.fft.rfftfreq(len(chunk), d=1.0 / samplerate)
    peak_idx = int(np.argmax(mag))
    peak_freq = float(freqs[peak_idx])
    norm_mag = float(mag[peak_idx] / (len(chunk) / 2.0 + 1e-9))
    return peak_freq, norm_mag


# --------------------------------------------------------------------------- #
# Прогресс-бар
# --------------------------------------------------------------------------- #

def draw_progress(state, args):
    elapsed = time.monotonic() - state["start_time"]
    level = min(state["current_level"] * 20.0, 1.0)
    bar_len = 30
    filled = int(level * bar_len)
    bar = "#" * filled + "-" * (bar_len - filled)
    freq = state["current_freq"]
    line = (
        f"\r[{bar}] t={elapsed:6.1f}с  уровень={level * 100:5.1f}%  "
        f"пик.частота={freq:7.1f} Гц (стоп: {args.stop_freq:.0f} Гц)   "
    )
    sys.stdout.write(line)
    sys.stdout.flush()


def print_devices():
    if sd is None:
        sys.exit(
            "Пакет sounddevice не установлен. Установите:\n"
            "  pip install sounddevice"
        )
    print(sd.query_devices())


# --------------------------------------------------------------------------- #
# Команда: record
# --------------------------------------------------------------------------- #

def cmd_record(args):
    if args.list_devices:
        print_devices()
        return

    if sd is None or sf is None:
        sys.exit(
            "Ошибка: не установлены необходимые пакеты.\n"
            "Установите: pip install sounddevice soundfile numpy\n"
            "И системную библиотеку PortAudio: sudo apt-get install libportaudio2"
        )

    samplerate = args.samplerate
    channels = args.channels
    chunk_size = 2048

    frames = []
    stop_event = threading.Event()
    state = {
        "match_start": None,
        "current_freq": 0.0,
        "current_level": 0.0,
        "start_time": time.monotonic(),
    }

    def callback(indata, frame_count, time_info, status):
        mono = indata[:, 0] if indata.ndim > 1 else indata
        frames.append(indata.copy())

        state["current_level"] = rms(mono)
        peak_freq, norm_mag = dominant_frequency(mono, samplerate)
        state["current_freq"] = peak_freq

        is_stop_tone = (
            abs(peak_freq - args.stop_freq) <= args.tolerance
            and norm_mag >= args.threshold
        )

        now = time.monotonic()
        if is_stop_tone:
            if state["match_start"] is None:
                state["match_start"] = now
            elif now - state["match_start"] >= args.min_duration:
                stop_event.set()
        else:
            state["match_start"] = None

        if now - state["start_time"] >= args.max_duration:
            stop_event.set()

    print(
        f"Слушаю входной канал (устройство: {args.device or 'по умолчанию'}, "
        f"{samplerate} Гц, {channels} канал(ов))."
    )
    print(
        f"Стоп-частота: {args.stop_freq:.1f} Гц ± {args.tolerance:.1f} Гц, "
        f"мин. длительность тона: {args.min_duration:.2f} с."
    )
    print("Нажмите Ctrl+C для принудительной остановки.\n")

    try:
        with sd.InputStream(
            device=args.device,
            samplerate=samplerate,
            channels=channels,
            blocksize=chunk_size,
            callback=callback,
        ):
            while not stop_event.is_set():
                draw_progress(state, args)
                time.sleep(0.1)
            draw_progress(state, args)
    except KeyboardInterrupt:
        sys.stdout.write("\n")
        print("Запись остановлена пользователем.")
    sys.stdout.write("\n")

    if not frames:
        print("Аудиоданные не были получены.")
        return

    audio = np.concatenate(frames, axis=0)

    out_path = args.output or os.path.join(
        tempfile.gettempdir(), f"audiotool_fragment_{int(time.time())}.wav"
    )
    sf.write(out_path, audio, samplerate)

    with open(STATE_FILE, "w") as f:
        json.dump({"last_fragment": out_path, "samplerate": samplerate}, f)

    duration = len(audio) / samplerate
    print(f"Запись завершена. Длительность: {duration:.2f} с.")
    print(f"Фрагмент сохранён во временный файл: {out_path}")
    print("Используйте команду 'save', чтобы перенести его в постоянную папку:")
    print("  audiotool save --name имя_фрагмента")


# --------------------------------------------------------------------------- #
# Команда: save
# --------------------------------------------------------------------------- #

def cmd_save(args):
    input_path = args.input
    if input_path is None:
        if not os.path.exists(STATE_FILE):
            sys.exit(
                "Нет данных о последнем записанном фрагменте.\n"
                "Укажите файл через --input, либо сначала выполните "
                "'audiotool record'."
            )
        with open(STATE_FILE) as f:
            saved_state = json.load(f)
        input_path = saved_state.get("last_fragment")

    if not input_path or not os.path.exists(input_path):
        sys.exit(f"Файл фрагмента не найден: {input_path}")

    os.makedirs(args.folder, exist_ok=True)

    ext = os.path.splitext(input_path)[1] or ".wav"
    name = args.name or datetime.datetime.now().strftime("fragment_%Y%m%d_%H%M%S")
    dest_path = os.path.join(args.folder, name + ext)

    counter = 1
    while os.path.exists(dest_path):
        dest_path = os.path.join(args.folder, f"{name}_{counter}{ext}")
        counter += 1

    shutil.copy2(input_path, dest_path)

    if not args.keep:
        try:
            os.remove(input_path)
        except OSError:
            pass

    print(f"Фрагмент сохранён: {dest_path}")


# --------------------------------------------------------------------------- #
# Команда: list
# --------------------------------------------------------------------------- #

def cmd_list(args):
    if not os.path.isdir(args.folder):
        print(f"Папка не найдена: {args.folder}")
        return

    audio_ext = {".wav", ".flac", ".ogg", ".mp3", ".aiff"}
    entries = sorted(
        e for e in os.listdir(args.folder)
        if os.path.splitext(e)[1].lower() in audio_ext
    )

    if not entries:
        print(f"В папке {args.folder} нет сохранённых аудио-фрагментов.")
        return

    print(f"Сохранённые фрагменты в {args.folder}:")
    for e in entries:
        full = os.path.join(args.folder, e)
        size_kb = os.path.getsize(full) / 1024
        mtime = datetime.datetime.fromtimestamp(os.path.getmtime(full))
        print(f"  {e:40s} {size_kb:8.1f} КБ   {mtime:%Y-%m-%d %H:%M:%S}")


# --------------------------------------------------------------------------- #
# Точка входа
# --------------------------------------------------------------------------- #

def main():
    parser = build_parser()
    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        return

    if args.command == "record":
        cmd_record(args)
    elif args.command == "save":
        cmd_save(args)
    elif args.command == "list":
        cmd_list(args)


if __name__ == "__main__":
    main()
