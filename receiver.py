"""
Приёмник. Слушает микрофон заданное время (или читает .wav) и декодирует данные.

Использование:
  python3 receiver.py --listen 15                # слушать 15 секунд с микрофона
  python3 receiver.py --listen 15 --out result.bin
  python3 receiver.py --wav received.wav          # декодировать готовый файл (отладка)
"""

import argparse
import sys
import numpy as np

from protocol import decode_from_wave, FS


def record_audio(seconds: float, fs: int = FS) -> np.ndarray:
    import sounddevice as sd
    print(f"[receiver] слушаю {seconds} сек...")
    audio = sd.rec(int(seconds * fs), samplerate=fs, channels=1, dtype="float32")
    sd.wait()
    print("[receiver] запись окончена, декодирую...")
    return audio.flatten()


def load_wav(path: str, target_fs: int = FS) -> np.ndarray:
    try:
        import soundfile as sf
        data, fs = sf.read(path, dtype="float32")
        if data.ndim > 1:
            data = data.mean(axis=1)
        if fs != target_fs:
            print(f"[receiver] ВНИМАНИЕ: частота файла {fs} != {target_fs}, "
                  f"декодер может ошибаться без ресемплинга", file=sys.stderr)
        return data
    except ImportError:
        import wave as wavemod
        with wavemod.open(path, "r") as wf:
            fs = wf.getframerate()
            n = wf.getnframes()
            raw = wf.readframes(n)
        data = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
        if fs != target_fs:
            print(f"[receiver] ВНИМАНИЕ: частота файла {fs} != {target_fs}", file=sys.stderr)
        return data


def main():
    ap = argparse.ArgumentParser()
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--listen", type=float, help="Слушать микрофон N секунд")
    src.add_argument("--wav", help="Декодировать готовый WAV-файл (для отладки)")
    ap.add_argument("--out", help="Сохранить декодированные байты в файл (иначе печать в консоль)")
    ap.add_argument("--retries", type=int, default=1,
                     help="Если из микрофона — сколько раз слушать заново при неудаче")
    args = ap.parse_args()

    if args.wav:
        audio = load_wav(args.wav)
        payload = decode_from_wave(audio)
    else:
        payload = None
        attempt = 0
        while payload is None and attempt < max(1, args.retries):
            attempt += 1
            audio = record_audio(args.listen)
            payload = decode_from_wave(audio)
            if payload is None and attempt < args.retries:
                print("[receiver] не удалось декодировать (нет сигнала/CRC не сошёлся), пробую снова...")

    if payload is None:
        print("[receiver] ОШИБКА: не удалось распознать сигнал (нет sync-тона или CRC не совпал)",
              file=sys.stderr)
        sys.exit(1)

    print(f"[receiver] получено {len(payload)} байт")

    if args.out:
        with open(args.out, "wb") as f:
            f.write(payload)
        print(f"[receiver] сохранено в {args.out}")
    else:
        try:
            print("[receiver] текст:", payload.decode("utf-8"))
        except UnicodeDecodeError:
            print("[receiver] бинарные данные (не UTF-8):", payload)


if __name__ == "__main__":
    main()
