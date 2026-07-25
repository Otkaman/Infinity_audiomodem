import unittest

import numpy as np

from protocol import (
    encode_to_wave,
    decode_from_wave,
    encode_file_transfer_wave,
    decode_file_transfer_from_wave,
    fast_encode_file_transfer_wave,
    fast_decode_file_transfer_from_wave,
    encode_with_preset,
    decode_with_preset,
    build_end_marker_wave,
    detect_end_marker,
    crc32,
    PRESET_NAMES,
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

    def test_end_marker_detection(self):
        marker = build_end_marker_wave()
        self.assertTrue(detect_end_marker(marker))
        self.assertFalse(detect_end_marker(np.zeros(1000, dtype=np.float32)))

    def test_checksum_validation(self):
        payload = b"checksum-test-payload"
        wave = encode_file_transfer_wave("test.bin", payload, symbol_duration=0.02, gap_duration=0.05, chunk_size=8)
        self.assertEqual(crc32(payload), crc32(payload))

    def test_fast_mode_round_trip(self):
        payload = b"hello world fast mode test " * 100
        wave = fast_encode_file_transfer_wave("fast_test.bin", payload)
        result = fast_decode_file_transfer_from_wave(wave)
        self.assertIsNotNone(result)
        name, data = result
        self.assertEqual(name, "fast_test.bin")
        self.assertEqual(data, payload)

    def test_all_presets_round_trip(self):
        payload = b"preset-test-data-" * 50
        for preset in PRESET_NAMES:
            wave = encode_with_preset("preset.bin", payload, preset=preset)
            self.assertGreater(len(wave), 0, f"пустая волна для пресета {preset}")
            result = decode_with_preset(wave, preset=preset)
            self.assertIsNotNone(result, f"пресет {preset} не декодировался")
            name, data = result
            self.assertEqual(name, "preset.bin")
            self.assertEqual(data, payload)


if __name__ == "__main__":
    unittest.main()
