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
        wave = encode_to_wave(payload, symbol_duration=0.02, gap_duration=0.05)
        self.assertEqual(decode_from_wave(wave, symbol_duration=0.02, gap_duration=0.05), payload)

    def test_chunked_file_transfer_round_trip(self):
        payload = b"small-payload-data"
        wave = encode_file_transfer_wave(
            "test.bin",
            payload,
            symbol_duration=0.02,
            gap_duration=0.05,
            chunk_size=8,
        )
        name, data = decode_file_transfer_from_wave(
            wave,
            symbol_duration=0.02,
            gap_duration=0.05,
        )
        self.assertEqual(name, "test.bin")
        self.assertEqual(data, payload)

    def test_multi_frame_progression(self):
        payload = b"small-payload"
        wave = encode_to_wave(payload, symbol_duration=0.02, gap_duration=0.05)
        self.assertEqual(decode_from_wave(wave, symbol_duration=0.02, gap_duration=0.05), payload)


if __name__ == "__main__":
    unittest.main()
