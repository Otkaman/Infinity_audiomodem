"""
Отправитель. Кодирует файл или текст в аудиосигнал (FSK) и проигрывает через динамик
или сохраняет в WAV.

Пресеты (--preset):
  turbo    — макс. скорость (тишина, ноутбуки рядом)
  fast     — быстро (тихая комната)
  medium   — сбалансированно
  normal   — надёжно (по умолчанию)
  robust   — макс. надёжность (шум, большое расстояние)

Использование:
  python sender.py --file data.bin --play --preset fast
  python sender.py --text "test" --save out.wav
"""

import argparse
import os
import sys
import numpy as np

from protocol import encode_with_preset, encode_file_transfer_wave, FS, PRESET_NAMES


def save_wav(path: str, wave: np.ndarray, fs: int = FS):
    try:
        import soundfile as sf
        sf.write(path, wave, fs)
    except ImportError:
        import wave as wavemod
        pcm = np.clip(wave, -1.0, 1.0)
        pcm16 = (pcm * 32767).astype(np.int16)
        with wavemod.open(path, "w") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(fs)
            wf.writeframes(pcm16.tobytes())
    print(f"[sender] сохранено в {path}")


def play_audio(wave: np.ndarray, fs: int = FS):
    import sounddevice as sd
    import signal

    def _handle_sigint(signum, frame):
        sd.stop()
        raise KeyboardInterrupt

    signal.signal(signal.SIGINT, _handle_sigint)
    signal.signal(signal.SIGTERM, _handle_sigint)

    print("[sender] воспроизведение...")
    try:
        sd.play(wave, fs)
        sd.wait()
    except KeyboardInterrupt:
        sd.stop()
        print("[sender] остановлено")
        raise
    except Exception:
        sd.stop()
        raise
    else:
        print("[sender] готово")


def main():
    ap = argparse.ArgumentParser()
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--text", help="Текст для отправки (UTF-8)")
    src.add_argument("--file", help="Путь к файлу для отправки")
    ap.add_argument("--play", action="store_true", help="Проиграть через динамик")
    ap.add_argument("--save", help="Сохранить сигнал в WAV-файл")
    ap.add_argument("--preset", default="normal", choices=PRESET_NAMES,
                     help="Пресет скорости/надёжности (по умолчанию normal)")
    ap.add_argument("--fast", action="store_true",
                     help="= --preset fast")
    ap.add_argument("--chunk-size", type=int, default=120,
                     help="Размер чанка (только для UART-пресетов)")
    args = ap.parse_args()

    if args.fast:
        args.preset = "fast"

    if args.text is not None:
        payload = args.text.encode("utf-8")
        filename = "text.txt"
    else:
        with open(args.file, "rb") as f:
            payload = f.read()
        filename = os.path.basename(args.file)

    print(f"[sender] файл: {filename}, {len(payload)} байт, пресет: {args.preset}")

    wave = encode_with_preset(filename, payload, preset=args.preset)

    duration = len(wave) / FS
    print(f"[sender] длительность сигнала: {duration:.1f} сек ({duration/60:.1f} мин)")

    if args.save:
        save_wav(args.save, wave)

    if args.play:
        play_audio(wave)

    if not args.play and not args.save:
        print("[sender] укажи --play и/или --save")


if __name__ == "__main__":
    main()