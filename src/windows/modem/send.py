import numpy as np
from regex import S
import sounddevice as sd
import os
import zlib


sample_rate = 48000
duration = 0.05
freq_0 = 1800
freq_1 = 2000
header = '10101010'

v = np.linspace(0, duration, int(sample_rate * duration), endpoint=False) * 2 * np.pi
def generate_tone(bit):
    t = np.linspace(0, duration, int(sample_rate * duration), endpoint=False)
    if bit == '1':
        return np.sin(freq_1 * v)
    else:
        return np.sin(freq_0 * v)


def string_to_bits(s):
    return ''.join(format(ord(c), '08b') for c in s)


def string_to_signal(data):
    signal = np.concatenate([generate_tone(bit) for byte in data for bit in format(ord(byte), '08b')])
    return signal


def transmit(data):
    header_signal = np.concatenate([generate_tone(bit) for bit in header])
    data_signal = string_to_signal(data)
    signal = np.concatenate((header_signal, data_signal))

    sd.play(signal, samplerate=sample_rate)
    sd.wait()


class Compressor:
    def __init__(self, stream):
        self.obj = zlib.compressobj()
        self.stream = stream

    def read(self):
        data = self.stream.read()
        if data:
            result = self.obj.compress(data)
        elif self.obj:
            result = self.obj.flush()
            self.obj = None
        else:
            result = b''  # EOF marker
        return result

def transmit_file(filepath, sample_rate=48000, header_bits='10101010', include_path=False):
    def bytes_to_bits(data: bytes) -> str:
        return ''.join(format(b, '08b') for b in data)
    
    with open(filepath, 'rb') as file:
        comp = Compressor(file)
        file_data = b''
        while True:
            chunk = comp.read()
            if chunk == b'':
                break
            file_data += chunk
    
    print(file_data)
    name = filepath if include_path else os.path.basename(filepath)
    name_bytes = name.encode('utf-8')

    payload = name_bytes + b'\x00' + file_data
    payload_bits = bytes_to_bits(payload)
    header_signal = np.concatenate([generate_tone(bit) for bit in header_bits])
    data_signal = np.concatenate([generate_tone(bit) for bit in payload_bits])
    signal = np.concatenate((header_signal, data_signal))

    sd.play(signal, samplerate=sample_rate)
    sd.wait()
