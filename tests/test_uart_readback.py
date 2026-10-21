"""Protocol checks independent of RTL: malformed frames and golden compare."""
import importlib.util
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "decode_result_uart", Path(__file__).resolve().parents[1] / "scripts/decode_result_uart.py")
uart = importlib.util.module_from_spec(spec)
spec.loader.exec_module(uart)

FRAME = bytes.fromhex("a5 5a 01 02 00 00 00 00 00 00 00 ff ff ff ff 00 00 01 00 11 00 00 00 5a a5")

class UartReadbackTests(unittest.TestCase):
    def test_decode_does_not_claim_board_provenance_without_input(self):
        self.assertEqual(uart.decode(FRAME)["source"], "unknown")

    def test_signed_values_and_explicit_simulation_source(self):
        result = uart.decode(FRAME, source="simulation")
        self.assertEqual(result["source"], "simulation")
        self.assertEqual([r["partial_sum"] for r in result["records"]], [-1, 17])
        uart.verify_records(result, [0xffffffff, 17], rows=1, groups=2)

    def test_rejects_partial_or_corrupted_frames(self):
        for data in (FRAME[:-1], b"wrong" + FRAME, FRAME[:-2] + b"\x00\x00"):
            with self.assertRaises(ValueError):
                uart.decode(data)

    def test_rejects_wrong_sum(self):
        result = uart.decode(FRAME)
        with self.assertRaises(ValueError):
            uart.verify_records(result, [123, 17], rows=1, groups=2)

    def test_rejects_duplicate_or_out_of_range_tags(self):
        for bad_group in (0, 2):
            result = uart.decode(FRAME)
            result["records"][1]["group_id"] = bad_group
            with self.assertRaises(ValueError):
                uart.verify_records(result, [0xffffffff, 17], rows=1, groups=2)

    def test_rejects_missing_results(self):
        with self.assertRaises(ValueError):
            uart.verify_records(uart.decode(FRAME), [0xffffffff, 17, 0], rows=1, groups=3)

    def test_receiver_recovers_after_reset_interrupts_a_frame(self):
        scanner = uart.FrameScanner(max_records=256)
        self.assertEqual(scanner.feed(FRAME[:12] + FRAME), FRAME)

    def test_receiver_accepts_fragmented_frame_and_discards_noise(self):
        scanner = uart.FrameScanner(max_records=2)
        self.assertIsNone(scanner.feed(b"noise\xa5"))
        self.assertIsNone(scanner.feed(FRAME[:6]))
        self.assertIsNone(scanner.feed(FRAME[6:20]))
        self.assertEqual(scanner.feed(FRAME[20:]), FRAME)

    def test_receiver_recovers_from_bad_count_and_footer(self):
        scanner = uart.FrameScanner(max_records=2)
        corrupt = FRAME[:-2] + b"\x00\x00"
        self.assertEqual(scanner.feed(b"\xa5\x5a\x01\xff\xff\xff\xff" + corrupt + FRAME), FRAME)

if __name__ == "__main__":
    unittest.main()
