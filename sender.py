"""
Отправитель. Кодирует текст или файл в аудиосигнал (FSK) и:
  - проигрывает через динамик, и/или
  - сохраняет в .wav (полезно для отладки без второго устройства)

Использование:
  python3 sender.py --text "привет" --play
  python3 sender.py --file secret.bin --play --save out.wav
  python3 sender.py --text "test" --save out.wav      # без реального звука, только файл
"""

import argparse
import os
import sys
import numpy as np

from protocol import encode_file_transfer_wave, FS


def save_wav(path: str, wave: np.ndarray, fs: int = FS):
    try:
        import soundfile as sf
        sf.write(path, wave, fs)
    except ImportError:
        # fallback без внешней либы: пишем 16-bit PCM WAV вручную через wave-модуль
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
    ap.add_argument("--chunk-size", type=int, default=120, help="Размер чанка для передачи файла (рекомендуется 120 или меньше)")
    args = ap.parse_args()

    if args.text is not None:
        payload = args.text.encode("utf-8")
        filename = "text.txt"
    else:
        with open(args.file, "rb") as f:
            payload = f.read()
        filename = os.path.basename(args.file)

    wave = encode_file_transfer_wave(filename, payload, chunk_size=args.chunk_size)
    print(f"[sender] payload: {len(payload)} байт, длительность сигнала: {len(wave)/FS:.1f} сек")

    if args.save:
        save_wav(args.save, wave)

    if args.play:
        play_audio(wave)

    if not args.play and not args.save:
        print("[sender] укажи --play и/или --save, иначе сигнал никуда не пойдёт")


if __name__ == "__main__":
    main()