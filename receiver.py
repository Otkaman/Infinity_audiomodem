"""
Приёмник. Слушает микрофон и декодирует данные.

Использование:
  python3 receiver.py --out result.bin           # слушать до маркера завершения
  python3 receiver.py --wav received.wav         # декодировать готовый WAV-файл (отладка)
"""

import argparse
import sys
import numpy as np

from protocol import decode_from_wave, detect_end_marker, FS


def record_until_end_marker(seconds: float, fs: int = FS) -> np.ndarray:
    import sounddevice as sd
    seconds = max(float(seconds), 0.1)
    print(f"[receiver] слушаю до маркера завершения, блок {seconds:.1f} сек...")
    total = []
    chunk_samples = max(int(seconds * fs), 1)
    while True:
        chunk = sd.rec(chunk_samples, samplerate=fs, channels=1, dtype="float32")
        sd.wait()
        total.append(chunk.flatten())
        if detect_end_marker(np.concatenate(total)):
            print("[receiver] обнаружен маркер завершения")
            break
    return np.concatenate(total)


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
    src.add_argument("--wav", help="Декодировать готовый WAV-файл (для отладки)")
    ap.add_argument("--out", help="Сохранить декодированные байты в файл (иначе печать в консоль)")
    ap.add_argument("--chunk-seconds", type=float, default=5.0,
                     help="Длина блока записи до следующей проверки маркера завершения")
    args = ap.parse_args()

    if args.wav:
        audio = load_wav(args.wav)
        payload = decode_from_wave(audio)
    else:
        payload = None
        audio = record_until_end_marker(max(args.chunk_seconds, 0.1))
        payload = decode_from_wave(audio)

    if payload is None:
        print("[receiver] ОШИБКА: не удалось распознать сигнал", file=sys.stderr)
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
