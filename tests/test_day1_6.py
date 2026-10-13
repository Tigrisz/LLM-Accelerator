from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from model.golden_gemv import gemv_partial_sums, stream_metadata
from model.gen_vectors import generate_case
from model.pack_weights import (
    decode_int4,
    pack_int4,
    pack_weight_matrix,
    unpack_int4,
    unpack_weight_matrix,
)
from model.stream_reference import iter_gemv_beats


class ModelToolTests(unittest.TestCase):
    def test_signed_nibble_boundaries(self) -> None:
        self.assertEqual([decode_int4(x) for x in (0x0, 0x7, 0x8, 0xF)], [0, 7, -8, -1])
        values = [-8, -1, 0, 1, 7, -7, 6, -2]
        self.assertEqual(unpack_int4(pack_int4(values), len(values)), values)

    def test_pack_matrix_pads_each_row(self) -> None:
        matrix = [[-8, -1, 0], [1, 2, 7]]
        packed = pack_weight_matrix(matrix, group_size=4)
        self.assertEqual(unpack_weight_matrix(packed, 2, 3, group_size=4), matrix)
        # Two rows * four padded values * four bits = four bytes.
        self.assertEqual(len(packed), 4)

    def test_golden_partial_sums_and_tail_group(self) -> None:
        weights = [[1, -2, 3, -4, 5], [-1, 0, 2, 4, -3]]
        activation = [2, -3, 4, 5, -6]
        result = gemv_partial_sums(weights, activation, group_size=4)
        self.assertEqual(result, [[0, -30], [26, 18]])

    def test_stream_metadata_marks_group_edges(self) -> None:
        metadata = stream_metadata(rows=1, cols=129, lanes=32, group_size=128)
        self.assertEqual(len(metadata), 8)
        self.assertTrue(metadata[0]["group_first"])
        self.assertTrue(metadata[3]["group_last"])
        self.assertTrue(metadata[4]["group_first"])
        self.assertTrue(metadata[7]["group_last"])
        self.assertEqual(metadata[4]["valid_elements"], 1)
        self.assertEqual(metadata[7]["valid_elements"], 0)

    def test_stream_reference_repeats_activation_per_row(self) -> None:
        weights = [[1, 2, 3, 4], [5, 6, 7, 7]]
        activation = [1, -2, 3, -4]
        beats = list(iter_gemv_beats(weights, activation, lanes=2, group_size=4))
        self.assertEqual(len(beats), 4)
        self.assertEqual(beats[0]["weight_data_hex"], "21")
        self.assertEqual(beats[1]["weight_data_hex"], "43")
        self.assertEqual(beats[0]["activation_data_hex"], "01fe")
        self.assertEqual(beats[2]["activation_data_hex"], "01fe")

    def test_generated_case_is_reproducible_and_rtl_ready(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path("tmp")) as tmp:
            out = Path(tmp) / "case_001"
            config = generate_case(out, rows=3, cols=129, lanes=32, group_size=128, seed=42)
            self.assertEqual(config["format_version"], 1)
            self.assertEqual(json.loads((out / "config.json").read_text())["K"], 129)
            self.assertEqual(config["padded_K"], 256)
            self.assertTrue((out / "weight_packed.bin").exists())
            self.assertTrue((out / "activation_int8.bin").exists())
            self.assertEqual((out / "activation_int8.bin").stat().st_size, 256)
            self.assertTrue((out / "stream_reference.json").exists())
            expected = np.load(out / "expected_partial.npy")
            self.assertEqual(expected.shape, (3, 2))
            # Re-running with the same seed must produce byte-identical inputs.
            out2 = Path(tmp) / "case_002"
            generate_case(out2, rows=3, cols=129, lanes=32, group_size=128, seed=42)
            for name in (
                "config.json",
                "weight_packed.bin",
                "activation_int8.bin",
                "expected_partial.npy",
                "stream_reference.json",
            ):
                self.assertEqual((out / name).read_bytes(), (out2 / name).read_bytes(), name)


class ContractFileTests(unittest.TestCase):
    def test_contract_mentions_task_a_boundary(self) -> None:
        text = Path("docs/interface_v1.md").read_text(encoding="utf-8")
        for token in (
            "group_first",
            "group_last",
            "rd_req_valid",
            "rd_data_ready",
            "partial_sum",
            "paired_input_stream",
            "in_valid = weight_valid && activation_valid",
            "low-active asynchronous",
        ):
            self.assertIn(token, text)

    def test_b_side_rtl_modules_exist(self) -> None:
        for relative in (
            "rtl/memory/memory_model.sv",
            "rtl/memory/weight_reader.sv",
            "rtl/memory/activation_cache.sv",
            "rtl/memory/paired_input_stream.sv",
        ):
            text = Path(relative).read_text(encoding="utf-8")
            self.assertIn("module ", text)
            if relative != "rtl/memory/paired_input_stream.sv":
                self.assertIn("always_ff", text)

    def test_paired_stream_requires_both_sources(self) -> None:
        text = Path("rtl/memory/paired_input_stream.sv").read_text(encoding="utf-8")
        self.assertIn("assign in_valid = weight_valid && activation_valid;", text)
        self.assertIn("assign weight_ready = in_ready && activation_valid;", text)
        self.assertIn("assign activation_ready = in_ready && weight_valid;", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)

