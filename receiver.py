"""
Приёмник. Слушает микрофон и декодирует данные.

Пресеты (--preset):
  turbo    — макс. скорость
  fast     — быстро
  medium   — сбалансированно
  normal   — надёжно (по умолчанию)
  robust   — макс. надёжность

Использование:
  python receiver.py --out . --preset fast
  python receiver.py --wav received.wav
"""

import argparse
import sys
import numpy as np

from protocol import decode_with_preset, decode_file_transfer_from_wave, detect_end_marker, build_end_marker_wave, FS, PRESET_NAMES


def record_until_end_marker(chunk_seconds: float, fs: int = FS) -> np.ndarray:
    import sounddevice as sd
    chunk_seconds = max(float(chunk_seconds), 0.1)
    print(f"[receiver] слушаю до маркера завершения, блок {chunk_seconds:.1f} сек...")
    total = []
    chunk_samples = max(int(chunk_seconds * fs), 1)
    marker = build_end_marker_wave(fs=fs)
    marker_len = len(marker)

    while True:
        chunk = sd.rec(chunk_samples, samplerate=fs, channels=1, dtype="float32")
        sd.wait()
        audio = chunk.flatten()
        total.append(audio)
        combined = np.concatenate(total)

        if len(combined) >= marker_len:
            tail = combined[-marker_len:]
            if detect_end_marker(tail, fs=fs):
                print("[receiver] обнаружен маркер завершения")
                return combined[:-marker_len]

        if len(combined) > fs * 300:
            print("[receiver] таймаут: маркер не обнаружен")
            return combined


def load_wav(path: str, target_fs: int = FS) -> np.ndarray:
    try:
        import soundfile as sf
        data, fs = sf.read(path, dtype="float32")
        if data.ndim > 1:
            data = data.mean(axis=1)
        if fs != target_fs:
            print(f"[receiver] ВНИМАНИЕ: частота файла {fs} != {target_fs}", file=sys.stderr)
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
    src = ap.add_mutually_exclusive_group()
    src.add_argument("--wav", help="Декодировать готовый WAV-файл (для отладки)")
    ap.add_argument("--out", help="Папка для сохранения файла (по умолчанию текущая)")
    ap.add_argument("--chunk-seconds", type=float, default=5.0,
                     help="Длина блока записи (сек)")
    ap.add_argument("--preset", default="normal", choices=PRESET_NAMES,
                     help="Пресет скорости/надёжности (по умолчанию normal)")
    ap.add_argument("--fast", action="store_true",
                     help="= --preset fast")
    args = ap.parse_args()

    if args.fast:
        args.preset = "fast"

    if args.wav:
        audio = load_wav(args.wav)
    else:
        audio = record_until_end_marker(max(args.chunk_seconds, 0.1))

    result = decode_with_preset(audio, preset=args.preset)

    if result is None:
        print("[receiver] ОШИБКА: не удалось распознать передачу файла", file=sys.stderr)
        sys.exit(1)

    filename, payload = result
    print(f"[receiver] получен файл: {filename} ({len(payload)} байт), пресет: {args.preset}")

    import os
    out_dir = args.out or "."
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, filename)
    with open(out_path, "wb") as f:
        f.write(payload)
    print(f"[receiver] сохранено в {out_path}")


if __name__ == "__main__":
    main()
