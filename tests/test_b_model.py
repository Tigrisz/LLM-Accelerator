from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from model.golden_gemv import gemv_partial_sums, stream_metadata
from model.gen_vectors import generate_case
from model.model_slice import write_model_slice
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

    def test_real_model_slice_quantization_fixture(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path("tmp")) as tmp:
            out = Path(tmp) / "qwen_slice_smoke"
            weights = np.linspace(-1.0, 1.0, 16 * 128, dtype=np.float32).reshape(16, 128)
            activation = np.linspace(-0.5, 0.5, 128, dtype=np.float32)
            config = write_model_slice(out, weights, activation, {"model": "synthetic-real-slice"})
            self.assertEqual(config["N"], 16)
            self.assertEqual(config["K"], 128)
            self.assertEqual(config["padded_K"], 128)
            self.assertEqual(np.load(out / "expected_partial.npy").shape, (16, 1))
            self.assertEqual((out / "weight_packed.bin").stat().st_size, 16 * 64)
            self.assertEqual((out / "activation_int8.bin").stat().st_size, 128)
            self.assertTrue((out / "activation_scale.npy").exists())


class ContractFileTests(unittest.TestCase):
    def test_contract_mentions_task_a_boundary(self) -> None:
        text = Path("docs/b_delivery/interface_v1.md").read_text(encoding="utf-8")
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

    def test_system_control_contract_is_present(self) -> None:
        regs = Path("rtl/control/control_regs.sv").read_text(encoding="utf-8")
        controller = Path("rtl/control/task_controller.sv").read_text(encoding="utf-8")
        top = Path("rtl/control/accelerator_control_top.sv").read_text(encoding="utf-8")
        self.assertIn("module control_regs", regs)
        self.assertIn("ADDR_STATUS       = 8'h04", regs)
        self.assertIn("ADDR_RESULT_COUNT = 8'h28", regs)
        self.assertIn("module task_controller", controller)
        self.assertIn("result_valid && result_ready", controller)
        self.assertIn("ERR_ACT_LENGTH", controller)
        self.assertIn("GROUP_SIZE_U64", controller)
        self.assertIn("CACHE_MAX_K_U64", controller)
        self.assertIn("64'(GROUP_SIZE)", controller)
        self.assertIn("64'(CACHE_MAX_K)", controller)
        self.assertIn("module accelerator_control_top", top)
        self.assertIn(".cache_loaded_k(host_loaded_k)", top)
        self.assertIn(".out_ready(result_ready)", top)
        self.assertNotIn(".busy(),", top)
        self.assertIn("reader_busy", top)
        self.assertIn("activation_base_cfg", top)
        self.assertIn("parameter integer LANES = 32", top)
        self.assertIn("if (LANES == 16)", top)
        self.assertIn("lane_adapter_32_to_16", top)

    def test_32_to_16_adapter_contract_is_present(self) -> None:
        adapter = Path("rtl/compute/lane_adapter_32_to_16.sv").read_text(encoding="utf-8")
        self.assertIn("module lane_adapter_32_to_16", adapter)
        self.assertIn("weight_hold[63:0]", adapter)
        self.assertIn("weight_hold[127:64]", adapter)
        self.assertIn("activation_hold[127:0]", adapter)
        self.assertIn("activation_hold[255:128]", adapter)
        self.assertIn("out_group_first", adapter)
        self.assertIn("out_group_last", adapter)
        self.assertIn("in_valid && in_ready", adapter)

    def test_board_slice_runner_contract_is_present(self) -> None:
        runner = Path("rtl/model/fixed_slice_runner.sv").read_text(encoding="utf-8")
        self.assertIn("module fixed_slice_runner", runner)
        self.assertIn("$readmemh", runner)
        self.assertIn("lane_adapter_32_to_16", runner)
        self.assertIn("output reg         pass", runner)
        self.assertIn("output reg         fail", runner)
        self.assertIn("expected_mem", runner)
        self.assertIn("weight_mem_index", runner)
        self.assertIn("activation_beat_index", runner)
        self.assertIn("expected_row_index", runner)
        self.assertNotIn("16'(N)", runner)
        self.assertNotIn("32'(N)", runner)
        self.assertNotIn("16'(WEIGHT_BEATS)", runner)
        self.assertNotIn("WEIGHT_INDEX_WIDTH'(", runner)
        demo = Path("rtl/model/fixed_slice_demo_top.sv").read_text(encoding="utf-8")
        self.assertIn("module fixed_slice_demo_top", demo)
        self.assertIn(".start(rst_n)", demo)
        qwen_demo = Path("rtl/model/fixed_slice_qwen_demo_top.sv").read_text(encoding="utf-8")
        self.assertIn("module fixed_slice_qwen_demo_top", qwen_demo)
        self.assertIn(".N(16)", qwen_demo)
        self.assertIn(".K(128)", qwen_demo)
        self.assertIn("build/fixed_slice_qwen/weights.mem", qwen_demo)
        qwen_tb = Path("tests/tb_fixed_slice_qwen.sv").read_text(encoding="utf-8")
        qwen_bfm = Path("tests/test_fixed_slice_qwen.cpp").read_text(encoding="utf-8")
        self.assertIn("module tb_fixed_slice_qwen", qwen_tb)
        self.assertIn(".N(16)", qwen_tb)
        self.assertIn("build/fixed_slice_qwen/weights.mem", qwen_tb)
        self.assertIn("result_count == 16", qwen_bfm)
        makefile = Path("Makefile").read_text(encoding="utf-8")
        self.assertIn("test-fixed-slice-qwen", makefile)
        self.assertIn("fixed-slice-qwen-inputs", makefile)

    def test_model_slice_tools_are_present(self) -> None:
        extractor = Path("scripts/extract_qwen_slice.py").read_text(encoding="utf-8")
        mem_packer = Path("scripts/prepare_fixed_slice_mem.py").read_text(encoding="utf-8")
        self.assertIn("Qwen2.5-1.5B-Instruct", extractor)
        self.assertIn("self_attn.o_proj", extractor)
        self.assertIn('.float().numpy()', extractor)
        self.assertIn("weight_packed.bin", mem_packer)
        self.assertIn("expected_partial.npy", mem_packer)


if __name__ == "__main__":
    unittest.main(verbosity=2)

