import unittest

from protocol import (
    encode_to_wave,
    decode_from_wave,
    encode_file_transfer_wave,
    decode_file_transfer_from_wave,
)


class FileTransferProtocolTests(unittest.TestCase):
    def test_single_payload_round_trip(self):
        payload = b"hello world"
        wave = encode_to_wave(payload, symbol_duration=0.002)
        self.assertEqual(decode_from_wave(wave, symbol_duration=0.002), payload)

    def test_chunked_file_transfer_round_trip(self):
        payload = (b"hello-audio-transfer-" * 80) + b"done"
        wave = encode_file_transfer_wave(
            "test.bin",
            payload,
            symbol_duration=0.002,
            chunk_size=120,
        )
        name, data = decode_file_transfer_from_wave(
            wave,
            symbol_duration=0.002,
        )
        self.assertEqual(name, "test.bin")
        self.assertEqual(data, payload)


if __name__ == "__main__":
    unittest.main()
