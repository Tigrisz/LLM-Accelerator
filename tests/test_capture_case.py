"""Task-A fixtures must survive ROM conversion without changing their meaning."""
import json
import shutil
import tempfile
import unittest
from pathlib import Path

import numpy as np

try:
    from scripts.prepare_capture_case import prepare_case
except ImportError:
    prepare_case = None


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests/fixtures/a_multigroup"
WANTED = {
    256: [-1284, -920, -3432, 724, -851, 2890],
    384: [-6908, 1686, -1175, -1560, -1043, -3218, -4489, 215, 1156],
}


class CaptureCaseTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(prepare_case, "prepare_case converter is not implemented")
        (ROOT / "tmp").mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=ROOT / "tmp")
        self.addCleanup(self.temp.cleanup)
        self.work = Path(self.temp.name)

    def source(self):
        path = self.work / "source"
        shutil.copytree(FIXTURES / "lanes16_n3_k256", path)
        return path

    def test_actual_cases_roundtrip_and_literal_partial_sums(self):
        for k, wanted in WANTED.items():
            with self.subTest(k=k):
                source = FIXTURES / f"lanes16_n3_k{k}"
                original = (source / "config.json").read_bytes()
                output = self.work / str(k)
                report = prepare_case(source, output)
                self.assertEqual(report["expected_records"], len(wanted))
                self.assertFalse(report["board_verified"])
                self.assertEqual(report["source_capture"], "simulation")
                config = json.loads((output / "config.json").read_text())
                self.assertEqual(config["lanes"], 32)
                self.assertEqual(config["source_lanes"], 16)
                self.assertEqual(config["compute_lanes"], 16)
                for name, width in (("weights.mem", 16), ("activation.mem", 32)):
                    words = (output / name).read_bytes()
                    self.assertNotIn(b"\r", words)
                    data = b"".join(int(x, 16).to_bytes(width, "little")
                                    for x in words.split())
                    binary = "weight_packed.bin" if width == 16 else "activation_int8.bin"
                    self.assertEqual(data, (source / binary).read_bytes())
                expected = [int(x, 16) for x in (output / "expected.mem").read_text().split()]
                self.assertEqual(expected, [x & 0xffffffff for x in wanted])
                self.assertEqual((source / "config.json").read_bytes(), original)
                self.assertEqual(prepare_case(source, output), report)

    def test_rejects_wrong_golden_before_writing(self):
        source = self.source()
        values = np.load(source / "expected_partial.npy", allow_pickle=False)
        values[0, 0] += 1
        np.save(source / "expected_partial.npy", values)
        with self.assertRaisesRegex(ValueError, "golden"):
            prepare_case(source, self.work / "out")
        self.assertFalse((self.work / "out").exists())

    def test_rejects_wrong_sixteen_lane_stream(self):
        source = self.source()
        stream = json.loads((source / "stream_reference.json").read_text())
        stream[0]["activation_data_hex"] = "00" * 16
        (source / "stream_reference.json").write_text(json.dumps(stream))
        with self.assertRaisesRegex(ValueError, "stream"):
            prepare_case(source, self.work / "out")

    def test_rejects_truncated_packed_input(self):
        source = self.source()
        file = source / "weight_packed.bin"
        file.write_bytes(file.read_bytes()[:-1])
        with self.assertRaisesRegex(ValueError, "length"):
            prepare_case(source, self.work / "out")

    def test_rejects_nonzero_tail_padding(self):
        source = self.source()
        config = json.loads((source / "config.json").read_text())
        config["K"] = 255
        (source / "config.json").write_text(json.dumps(config))
        file = source / "activation_int8.bin"
        data = bytearray(file.read_bytes()); data[-1] = 1
        file.write_bytes(data)
        with self.assertRaisesRegex(ValueError, "padding"):
            prepare_case(source, self.work / "out")

    def test_rejects_non_integer_golden(self):
        source = self.source()
        np.save(source / "expected_partial.npy", np.zeros((3, 2), dtype=np.float32))
        with self.assertRaisesRegex(ValueError, "INT32"):
            prepare_case(source, self.work / "out")

    def test_rejects_unsupported_lane_count(self):
        source = self.source()
        config = json.loads((source / "config.json").read_text()); config["lanes"] = 8
        (source / "config.json").write_text(json.dumps(config))
        with self.assertRaisesRegex(ValueError, "lanes"):
            prepare_case(source, self.work / "out")

    def test_refuses_to_replace_different_existing_output(self):
        source = self.source(); output = self.work / "out"; output.mkdir()
        marker = output / "expected.mem"; marker.write_bytes(b"do not overwrite\n")
        with self.assertRaisesRegex(ValueError, "overwrite"):
            prepare_case(source, output)
        self.assertEqual(marker.read_bytes(), b"do not overwrite\n")
        self.assertFalse((output / "weights.mem").exists())

    def test_rejects_incomplete_reference_capture(self):
        source = self.source()
        file = source / "capture.json"; capture = json.loads(file.read_text())
        capture["completed"] = False; file.write_text(json.dumps(capture))
        with self.assertRaisesRegex(ValueError, "capture"):
            prepare_case(source, self.work / "out")


if __name__ == "__main__":
    unittest.main()
