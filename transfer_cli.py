import argparse
import os
import numpy as np
import sounddevice as sd

from protocol import FS, encode_file_transfer_wave, decode_file_transfer_from_wave


def play_audio(wave: np.ndarray, fs: int = FS):
    sd.play(wave, fs)
    sd.wait()


def save_wav(path: str, wave: np.ndarray, fs: int = FS):
    import wave as wavemod
    pcm = np.clip(wave, -1.0, 1.0)
    pcm16 = (pcm * 32767).astype(np.int16)
    with wavemod.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(fs)
        wf.writeframes(pcm16.tobytes())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--send", help="Path to file to send")
    ap.add_argument("--receive", action="store_true", help="Receive a file from the microphone")
    ap.add_argument("--out", default="received.bin", help="Output filename for received file")
    ap.add_argument("--chunk-size", type=int, default=300)
    args = ap.parse_args()

    if args.send:
        with open(args.send, "rb") as f:
            payload = f.read()
        wave = encode_file_transfer_wave(os.path.basename(args.send), payload, chunk_size=args.chunk_size)
        print(f"Prepared {len(payload)} bytes for transmission")
        play_audio(wave)
    elif args.receive:
        print("Receiving via microphone is not implemented in this lightweight CLI yet.")
        print("Use the existing receiver.py workflow for now.")
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
