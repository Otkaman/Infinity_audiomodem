"""
Протокол передачи данных через звук (FSK, UART-подобное кадрирование).

Формат кадра:
  PREAMBLE (4 байта 0xAA) | LEN (1 байт) | PAYLOAD (LEN байт) | CRC8 (1 байт)

Каждый байт кадра кодируется как в UART:
  старт-бит(0) + 8 бит данных (LSB first) + стоп-бит(1)

Биты кодируются двумя тонами:
  0 -> FREQ0
  1 -> FREQ1

Перед данными идёт калибровочный тон (SYNC), чтобы приёмник понял,
где начинается передача, и пауза тишины перед битовым потоком.
"""

import math
import numpy as np

FS = 44100              # частота дискретизации
FREQ0 = 2000.0           # тон для бита 0
FREQ1 = 3000.0           # тон для бита 1
SYMBOL_DURATION = 0.08   # более длинный и устойчивый символ
SYNC_TONE_DURATION = 1.0 # длительность калибровочного тона
GAP_DURATION = 0.15      # тишина между sync-тоном и данными
PREAMBLE = bytes([0xAA, 0xAA, 0xAA, 0xAA])


def crc8(data: bytes) -> int:
    crc = 0x00
    poly = 0x07
    for b in data:
        crc ^= b
        for _ in range(8):
            if crc & 0x80:
                crc = ((crc << 1) ^ poly) & 0xFF
            else:
                crc = (crc << 1) & 0xFF
    return crc


def crc32(data: bytes) -> int:
    import zlib
    return zlib.crc32(data) & 0xFFFFFFFF


def build_frame(payload: bytes) -> bytes:
    if len(payload) > 255:
        raise ValueError("payload слишком длинный для этого простого протокола (макс 255 байт)")
    length = len(payload)
    crc = crc8(bytes([length]) + payload)
    return PREAMBLE + bytes([length]) + payload + bytes([crc])


def bytes_to_uart_bits(data: bytes):
    bits = []
    for byte in data:
        bits.append(0)  # старт-бит
        for i in range(8):
            bits.append((byte >> i) & 1)  # LSB first
        bits.append(1)  # стоп-бит
    return bits


def gen_tone(freq, duration, fs=FS, fade=0.003):
    n = int(duration * fs)
    t = np.arange(n) / fs
    wave = np.sin(2 * np.pi * freq * t)
    fade_n = int(fade * fs)
    if 0 < fade_n * 2 < n:
        ramp = np.linspace(0, 1, fade_n)
        wave[:fade_n] *= ramp
        wave[-fade_n:] *= ramp[::-1]
    return wave.astype(np.float32)


def encode_frame_to_wave(
    frame: bytes,
    fs=FS,
    symbol_duration=SYMBOL_DURATION,
    sync_tone_duration=SYNC_TONE_DURATION,
    gap_duration=GAP_DURATION,
) -> np.ndarray:
    bits = bytes_to_uart_bits(frame)

    sync = gen_tone(FREQ1, sync_tone_duration, fs)
    gap = np.zeros(int(gap_duration * fs), dtype=np.float32)

    chunks = [sync, gap]
    for bit in bits:
        f = FREQ1 if bit == 1 else FREQ0
        chunks.append(gen_tone(f, symbol_duration, fs))
        chunks.append(gap)

    chunks.append(np.zeros(int(0.05 * fs), dtype=np.float32))
    wave = np.concatenate(chunks)
    return (wave * 0.8).astype(np.float32)


def encode_to_wave(
    payload: bytes,
    fs=FS,
    symbol_duration=SYMBOL_DURATION,
    sync_tone_duration=SYNC_TONE_DURATION,
    gap_duration=GAP_DURATION,
) -> np.ndarray:
    frame = build_frame(payload)
    return encode_frame_to_wave(
        frame,
        fs=fs,
        symbol_duration=symbol_duration,
        sync_tone_duration=sync_tone_duration,
        gap_duration=gap_duration,
    )


def build_file_transfer_frames(filename: str, payload: bytes, chunk_size: int = 120) -> list[bytes]:
    if chunk_size <= 0:
        raise ValueError("chunk_size must be > 0")
    if chunk_size > 120:
        chunk_size = 120
    name_bytes = filename.encode("utf-8")
    if len(name_bytes) > 255:
        raise ValueError("filename too long")

    total_size = len(payload)
    chunk_count = 0 if total_size == 0 else math.ceil(total_size / chunk_size)
    checksum = crc32(payload).to_bytes(4, "big")
    metadata_payload = (
        b"\x00"
        + bytes([len(name_bytes)])
        + name_bytes
        + total_size.to_bytes(4, "big")
        + chunk_count.to_bytes(4, "big")
        + chunk_size.to_bytes(2, "big")
        + checksum
    )
    frames = [build_frame(metadata_payload)]
    for offset in range(0, len(payload), chunk_size):
        chunk = payload[offset:offset + chunk_size]
        data_payload = b"\x01" + offset.to_bytes(4, "big") + chunk
        frames.append(build_frame(data_payload))
    return frames


def build_end_marker_wave(
    fs=FS,
    duration=2.0,
    marker_freq=1200.0,
) -> np.ndarray:
    tone = gen_tone(marker_freq, duration, fs)
    silence = np.zeros(int(0.3 * fs), dtype=np.float32)
    return np.concatenate([tone, silence, tone]).astype(np.float32)


def encode_file_transfer_wave(
    filename: str,
    payload: bytes,
    fs=FS,
    symbol_duration=SYMBOL_DURATION,
    sync_tone_duration=SYNC_TONE_DURATION,
    gap_duration=GAP_DURATION,
    chunk_size: int = 200,
) -> np.ndarray:
    frames = build_file_transfer_frames(filename, payload, chunk_size=chunk_size)
    chunks = []
    for frame in frames:
        chunks.append(
            encode_frame_to_wave(
                frame,
                fs=fs,
                symbol_duration=symbol_duration,
                sync_tone_duration=sync_tone_duration,
                gap_duration=gap_duration,
            )
        )
        chunks.append(np.zeros(int(gap_duration * fs), dtype=np.float32))
    if not chunks:
        return np.zeros(0, dtype=np.float32)
    wave = np.concatenate(chunks)
    wave = (wave * 0.8).astype(np.float32)
    marker = build_end_marker_wave(fs=fs)
    return np.concatenate([wave, marker]).astype(np.float32)


# ---------------------- ДЕКОДЕР ----------------------

def _goertzel_power(samples: np.ndarray, freq: float, fs: int) -> float:
    n = len(samples)
    if n == 0:
        return 0.0
    k = int(0.5 + n * freq / fs)
    w = 2 * np.pi * k / n
    coeff = 2 * np.cos(w)
    s_prev = 0.0
    s_prev2 = 0.0
    for x in samples:
        s = x + coeff * s_prev - s_prev2
        s_prev2 = s_prev
        s_prev = s
    power = s_prev2 ** 2 + s_prev ** 2 - coeff * s_prev * s_prev2
    return power


def _bandpower(samples: np.ndarray, fs: int, low: float, high: float) -> float:
    if len(samples) == 0:
        return 0.0
    samples = np.asarray(samples, dtype=np.float32)
    n = len(samples)
    freqs = np.fft.rfftfreq(n, 1.0 / fs)
    spectrum = np.abs(np.fft.rfft(samples))
    mask = (freqs >= low) & (freqs <= high)
    if not np.any(mask):
        return 0.0
    return float(np.mean(spectrum[mask]))


def _filter_noise(samples: np.ndarray) -> np.ndarray:
    if len(samples) < 4:
        return samples
    samples = np.asarray(samples, dtype=np.float32)
    window = np.hanning(len(samples))
    return samples * window


def detect_end_marker(samples: np.ndarray, fs=FS, threshold: float = 0.12) -> bool:
    if len(samples) < int(0.8 * fs):
        return False

    energy = float(np.mean(np.square(samples.astype(np.float64))))
    if energy < 1e-4:
        return False

    marker = build_end_marker_wave(fs=fs)
    if len(marker) > len(samples):
        marker = marker[:len(samples)]

    signal = samples[:len(marker)].astype(np.float64)
    corr = np.correlate(signal, marker.astype(np.float64), mode="full")
    peak = float(np.max(corr))
    if peak <= threshold:
        return False

    marker_energy = float(np.mean(np.square(marker)))
    if marker_energy <= 0:
        return False

    return peak / max(marker_energy, 1e-8) > 0.8


def _find_sync_end(samples: np.ndarray, fs=FS, start_index: int = 0) -> int:
    """Ищем момент, где заканчивается калибровочный тон (после него — тишина)."""
    if start_index < 0:
        start_index = 0
    if start_index >= len(samples):
        return -1
    win = int(0.04 * fs)
    step = win // 2
    tone_started = False
    i = start_index
    while i + win < len(samples):
        seg = samples[i:i + win]
        energy = np.sum(seg.astype(np.float64) ** 2) / win
        p1 = _goertzel_power(seg, FREQ1, fs) / win
        if not tone_started and p1 > 0.02:
            tone_started = True
        if tone_started and energy < 0.005:
            return i
        i += step
    return -1


def _decode_bit(seg: np.ndarray, fs=FS) -> int:
    seg = _filter_noise(seg)
    p0 = _goertzel_power(seg, FREQ0, fs)
    p1 = _goertzel_power(seg, FREQ1, fs)
    p0_band = _bandpower(seg, fs, FREQ0 - 120.0, FREQ0 + 120.0)
    p1_band = _bandpower(seg, fs, FREQ1 - 120.0, FREQ1 + 120.0)
    if p1_band > p0_band * 1.1 and p1 > p0 * 1.1:
        return 1
    if p0_band > p1_band * 1.1 and p0 > p1 * 1.1:
        return 0
    return 1 if p1 > p0 else 0


def _bits_to_frame_bytes(bits):
    """UART-фреймер: ищем старт-бит(0), читаем 8 бит данных, проверяем стоп-бит(1)."""
    out = []
    i = 0
    n = len(bits)
    while i + 10 <= n:
        if bits[i] == 0:  # похоже на старт-бит
            data_bits = bits[i + 1:i + 9]
            stop_bit = bits[i + 9]
            if stop_bit == 1:
                byte = 0
                for idx, b in enumerate(data_bits):
                    byte |= (b << idx)
                out.append(byte)
                i += 10
                continue
        i += 1
    return bytes(out)


def _find_data_start(samples: np.ndarray, from_index: int, fs=FS) -> int:
    """После конца sync-тона ищем момент, где тишина заканчивается и начинается первый бит."""
    win = int(0.01 * fs)
    step = win // 2
    i = from_index
    while i + win < len(samples):
        seg = samples[i:i + win]
        energy = np.sum(seg.astype(np.float64) ** 2) / win
        if energy > 0.01:
            return i
        i += step
    return from_index + int(GAP_DURATION * fs * 0.5)  # fallback


def _decode_frame_from_wave(
    samples: np.ndarray,
    fs=FS,
    max_payload_len=255,
    symbol_duration=SYMBOL_DURATION,
    gap_duration=GAP_DURATION,
    start_index: int = 0,
):
    samples = np.asarray(samples, dtype=np.float32)
    sync_end = _find_sync_end(samples, fs, start_index=start_index)
    if sync_end < 0:
        return None, None

    start = _find_data_start(samples, sync_end, fs)
    tone_len = max(int(symbol_duration * fs), 1)
    step_len = tone_len + max(int(gap_duration * fs), 1)

    bits = []
    i = start
    max_bits = 10 * (4 + 1 + max_payload_len + 1) + 20
    while i + tone_len <= len(samples) and len(bits) < max_bits:
        seg = samples[i:i + tone_len]
        bits.append(_decode_bit(seg, fs))
        i += step_len

        frame_bytes = _bits_to_frame_bytes(bits)
        idx = frame_bytes.find(PREAMBLE)
        if idx < 0:
            continue

        rest = frame_bytes[idx + len(PREAMBLE):]
        if len(rest) < 1:
            continue
        length = rest[0]
        if len(rest) < 1 + length + 1:
            continue
        payload = rest[1:1 + length]
        crc_received = rest[1 + length]
        crc_calc = crc8(bytes([length]) + payload)
        if crc_calc != crc_received:
            continue

        next_index = max(i + int(0.05 * fs), start + len(bits) * step_len)
        return payload, next_index

    return None, None


def decode_frame_from_wave(
    samples: np.ndarray,
    fs=FS,
    max_payload_len=255,
    symbol_duration=SYMBOL_DURATION,
    gap_duration=GAP_DURATION,
):
    """Возвращает (payload, next_index) для одного кадра или (None, None)."""
    return _decode_frame_from_wave(
        samples,
        fs=fs,
        max_payload_len=max_payload_len,
        symbol_duration=symbol_duration,
        gap_duration=gap_duration,
    )


def decode_from_wave(
    samples: np.ndarray,
    fs=FS,
    max_payload_len=255,
    symbol_duration=SYMBOL_DURATION,
    gap_duration=GAP_DURATION,
):
    """Возвращает payload (bytes) или None, если не удалось распознать/CRC не сошёлся."""
    payload, _ = decode_frame_from_wave(
        samples,
        fs=fs,
        max_payload_len=max_payload_len,
        symbol_duration=symbol_duration,
        gap_duration=gap_duration,
    )
    return payload


def decode_file_transfer_from_wave(
    samples: np.ndarray,
    fs=FS,
    symbol_duration=SYMBOL_DURATION,
    gap_duration=GAP_DURATION,
):
    """Возвращает (filename, payload) после завершения передачи файла или None."""
    samples = np.asarray(samples, dtype=np.float32)
    metadata = None
    chunks = {}
    offset = 0
    step = max(int(0.05 * fs), 1)

    while offset < len(samples):
        decoded, next_index = decode_frame_from_wave(
            samples[offset:],
            fs=fs,
            max_payload_len=255,
            symbol_duration=symbol_duration,
            gap_duration=gap_duration,
        )
        if decoded is None:
            offset += step
            continue

        frame_type = decoded[0] if decoded else None
        if frame_type == 0x00:
            payload = decoded[1:]
            name_len = payload[0]
            name_bytes = payload[1:1 + name_len]
            total_size = int.from_bytes(payload[1 + name_len:5 + name_len], "big")
            chunk_count = int.from_bytes(payload[5 + name_len:9 + name_len], "big")
            checksum = int.from_bytes(payload[11 + name_len:15 + name_len], "big")
            metadata = {
                "filename": name_bytes.decode("utf-8"),
                "total_size": total_size,
                "chunk_count": chunk_count,
                "checksum": checksum,
            }
            chunks = {}
        elif frame_type == 0x01 and metadata is not None:
            payload = decoded[1:]
            offset_value = int.from_bytes(payload[0:4], "big")
            chunk = payload[4:]
            chunks[offset_value] = chunk
        else:
            break

        if metadata is not None and metadata["chunk_count"] > 0:
            if len(chunks) == metadata["chunk_count"]:
                reconstructed = b"".join(
                    chunk for _, chunk in sorted(chunks.items())
                )
                if len(reconstructed) >= metadata["total_size"]:
                    data = reconstructed[:metadata["total_size"]]
                    if crc32(data) == metadata["checksum"]:
                        return metadata["filename"], data
                    return None

        offset += max(next_index or step, step)

    return None
