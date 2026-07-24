import numpy as np

FS = 44100              # частота дискретизации
FREQ0 = 2000.0           # тон для бита 0
FREQ1 = 3000.0           # тон для бита 1
SYMBOL_DURATION = 0.08   # длительность одного бита, сек (~12.5 бод — с запасом на шум динамика/микро)
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


def encode_to_wave(payload: bytes, fs=FS) -> np.ndarray:
    frame = build_frame(payload)
    bits = bytes_to_uart_bits(frame)

    sync = gen_tone(FREQ1, SYNC_TONE_DURATION, fs)
    gap = np.zeros(int(GAP_DURATION * fs), dtype=np.float32)

    chunks = [sync, gap]
    for bit in bits:
        f = FREQ1 if bit == 1 else FREQ0
        chunks.append(gen_tone(f, SYMBOL_DURATION, fs))

    # немного тишины в конце, чтобы декодер не обрезал последний символ
    chunks.append(np.zeros(int(0.1 * fs), dtype=np.float32))

    wave = np.concatenate(chunks)
    return (wave * 0.8).astype(np.float32)


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
        s_prev = x if False else s  # keep clarity
        s_prev = s
    power = s_prev2 ** 2 + s_prev ** 2 - coeff * s_prev * s_prev2
    return power


def _find_sync_end(samples: np.ndarray, fs=FS) -> int:
    """Ищем момент, где заканчивается калибровочный тон (после него — тишина)."""
    win = int(0.02 * fs)
    step = win // 2
    tone_started = False
    i = 0
    while i + win < len(samples):
        seg = samples[i:i + win]
        energy = np.sum(seg.astype(np.float64) ** 2) / win
        p1 = _goertzel_power(seg, FREQ1, fs) / win
        if not tone_started and p1 > 0.05:
            tone_started = True
        if tone_started and energy < 0.01:
            return i
        i += step
    return -1


def _decode_bit(seg: np.ndarray, fs=FS) -> int:
    p0 = _goertzel_power(seg, FREQ0, fs)
    p1 = _goertzel_power(seg, FREQ1, fs)
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
        if energy > 0.05:
            return i
        i += step
    return from_index + int(GAP_DURATION * fs * 0.5)  # fallback


def decode_from_wave(samples: np.ndarray, fs=FS, max_payload_len=255):
    """Возвращает payload (bytes) или None, если не удалось распознать/CRC не сошёлся."""
    samples = np.asarray(samples, dtype=np.float32)

    sync_end = _find_sync_end(samples, fs)
    if sync_end < 0:
        return None

    start = _find_data_start(samples, sync_end, fs)
    bit_len = int(SYMBOL_DURATION * fs)

    bits = []
    i = start
    # с запасом читаем достаточно бит на преамбулу+длину+payload+crc
    max_bits = 10 * (4 + 1 + max_payload_len + 1) + 20
    while i + bit_len <= len(samples) and len(bits) < max_bits:
        seg = samples[i:i + bit_len]
        bits.append(_decode_bit(seg, fs))
        i += bit_len

    frame_bytes = _bits_to_frame_bytes(bits)

    # ищем преамбулу 0xAA 0xAA 0xAA 0xAA в раскодированных байтах
    idx = frame_bytes.find(PREAMBLE)
    if idx < 0:
        return None

    rest = frame_bytes[idx + len(PREAMBLE):]
    if len(rest) < 1:
        return None
    length = rest[0]
    if len(rest) < 1 + length + 1:
        return None
    payload = rest[1:1 + length]
    crc_received = rest[1 + length]
    crc_calc = crc8(bytes([length]) + payload)
    if crc_calc != crc_received:
        return None
    return payload
