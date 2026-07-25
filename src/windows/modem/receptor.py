import numpy as np
import sounddevice as sd
from scipy.fft import fft
import os
import time
import numpy as np
import sounddevice as sd
from scipy.fft import fft
import zlib


sample_rate = 48000
duration = 0.05
chunk_size = int(sample_rate * duration)
freq_0 = 1800
freq_1 = 2000
tolerance = 80
header = '10101010'

bit_buffer = ''
received_bits = ''
receiving = False


class Decompressor:
    def __init__(self, stream):
        self.obj = zlib.decompressobj()
        self.stream = stream

    def write(self, data):
        self.stream.write(self.obj.decompress(bytes(data)))

    def flush(self):
        self.stream.write(self.obj.flush())


def detect_frequency(signal):
    n = len(signal)
    fft_vals = fft(signal)
    freqs = np.fft.fftfreq(n, 1 / sample_rate)
    peak_freq = abs(freqs[np.argmax(np.abs(fft_vals))])
    return peak_freq

def frequency_to_bit(freq):
    if abs(freq - freq_0) < tolerance:
        return '0'
    elif abs(freq - freq_1) < tolerance:
        return '1'
    return None

def callback(indata, frames, time, status):
    global bit_buffer, receiving, received_bits

    chunk = indata[:, 0]
    freq = detect_frequency(chunk)
    bit = frequency_to_bit(freq)

    if bit:
        bit_buffer += bit

        if not receiving and bit_buffer.endswith(header):
            print("[+] Header detected")
            receiving = True
            received_bits = ''
        elif receiving:
            received_bits += bit

            if len(received_bits) % 8 == 0:
                byte = received_bits[-8:]
                try:
                    char = chr(int(byte, 2))
                    print(char, end='', flush=True)
                except:
                    pass

def listen():
    print("Listening...")
    with sd.InputStream(callback=callback, samplerate=sample_rate, channels=1, blocksize=chunk_size):
        input()


def receive_file_from_mic(
        output_dir=".",
        tolerance=80,
        silence_timeout=2.0
):
    chunk_size = int(sample_rate * duration)
    header_len = len(header)

    state = 'searching'
    bit_buffer = ''
    data_bits = []
    last_activity = time.time()
    flag = False

    def detect_frequency(signal):
        n = len(signal)
        fft_vals = fft(signal)
        freqs = np.fft.fftfreq(n, 1 / sample_rate)
        peak_freq = abs(freqs[np.argmax(np.abs(fft_vals))])
        return peak_freq

    def frequency_to_bit(freq):
        if abs(freq - freq_0) < tolerance:
            return '0'
        elif abs(freq - freq_1) < tolerance:
            return '1'
        return None

    def callback(indata, frames, time_info, status):
        nonlocal state, bit_buffer, data_bits, last_activity, flag

        if status:
            print(f"[!] Stream status: {status}")

        chunk = indata[:, 0]
        freq = detect_frequency(chunk)
        bit = frequency_to_bit(freq)

        if bit is not None:
            last_activity = time.time()
            if state == 'searching':
                bit_buffer += bit
                if len(bit_buffer) > header_len:
                    bit_buffer = bit_buffer[-header_len:]
                if bit_buffer == header:
                    print("[+] Header detected – receiving data...")
                    state = 'receiving'
                    data_bits = []
            elif state == 'receiving':
                data_bits.append(bit)

        if state == 'receiving' and (time.time() - last_activity) > silence_timeout:
            print("[*] Silence timeout – transmission ended.")
            sd.stop()
            flag = True

    print("Waiting for transmission... (auto-stop after silence)")
    stream = sd.InputStream(callback=callback,
                            samplerate=sample_rate,
                            channels=1,
                            blocksize=chunk_size)
    stream.start()

    while stream.active and not flag:
        time.sleep(0.1)

    stream.stop()
    stream.close()

    if not data_bits:
        print("No data received.")
        return None

    byte_vals = []
    for i in range(0, len(data_bits) - 7, 8):
        byte_bits = data_bits[i:i+8]
        byte_vals.append(int(''.join(byte_bits), 2))
    payload = bytes(byte_vals)

    print(payload)

    null_pos = payload.find(b'\x00')
    if null_pos == -1:
        print("Warning: filename terminator not found. Saving as received_file.bin")
        filename = "received_file.bin"
        raw_data  = payload
    else:
        filename_bytes = payload[:null_pos]
        raw_data  = payload[null_pos + 1:]
        try:
            filename = filename_bytes.decode('utf-8')
        except UnicodeDecodeError:
            filename = "received_file.bin"
    print(raw_data)

    os.makedirs(output_dir, exist_ok=True)
    out_path = os.path.join(output_dir, filename)
    try:
        with open(out_path, 'wb') as f:
            decompressor = Decompressor(f)
            decompressor.write(raw_data)
        print("Data decompressed and saved successfully.")
    except Exception as e:
        print(f"Decompression failed ({e}), saving raw data as is.")
        with open(out_path, 'wb') as f:
            f.write(raw_data)

    print(f"File saved: {out_path}")
    return out_path
