from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from model.model_slice import write_model_slice
from scripts.extract_qwen_slice import select_slice
from scripts.prepare_fixed_slice_mem import prepare
from scripts.verify_board_mem import verify_slice


class FixedSliceMultiGroupTests(unittest.TestCase):
    def test_extract_can_explicitly_zero_pad_short_model_width(self) -> None:
        weights = np.arange(2 * 3, dtype=np.float32).reshape(2, 3)
        activation = np.asarray([1.0, 2.0, 3.0], dtype=np.float32)

        selected, selected_activation, metadata = select_slice(
            weights,
            activation,
            rows_start=0,
            rows=2,
            cols_start=0,
            cols=5,
            allow_zero_pad_cols=True,
        )

        self.assertEqual(selected.shape, (2, 5))
        self.assertEqual(selected_activation.tolist(), [1.0, 2.0, 3.0, 0.0, 0.0])
        np.testing.assert_array_equal(selected[:, :3], weights)
        np.testing.assert_array_equal(selected[:, 3:], np.zeros((2, 2), dtype=np.float32))
        self.assertEqual(metadata["source_cols"], 3)
        self.assertEqual(metadata["zero_padded_cols"], 2)

    def test_prepare_emits_row_group_mem_layout_for_k256(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path("tmp")) as tmp:
            root = Path(tmp)
            source = root / "source"
            output = root / "fixed_slice"
            weights = np.arange(2 * 256, dtype=np.float32).reshape(2, 256) / 31.0
            activation = np.linspace(-1.0, 1.0, 256, dtype=np.float32)
            config = write_model_slice(
                source,
                weights,
                activation,
                {"model": "synthetic-multigroup"},
            )
            self.assertEqual(config["N"], 2)
            self.assertEqual(config["K"], 256)
            self.assertEqual(config["padded_K"], 256)

            prepared = prepare(source, output)

            self.assertEqual(prepared["N"], 2)
            self.assertEqual(prepared["K"], 256)
            self.assertEqual(len((output / "weights.mem").read_text().splitlines()), 16)
            self.assertEqual(len((output / "activation.mem").read_text().splitlines()), 8)
            expected = np.load(source / "expected_partial.npy", allow_pickle=False)
            expected_lines = [int(line, 16) for line in (output / "expected.mem").read_text().splitlines()]
            expected_signed = [value - (1 << 32) if value & (1 << 31) else value for value in expected_lines]
            self.assertEqual(expected_signed, expected.reshape(-1).tolist())
            self.assertEqual(json.loads((output / "config.json").read_text())["group_size"], 128)

    def test_prepare_emits_qwen_multigroup_image_dimensions(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path("tmp")) as tmp:
            root = Path(tmp)
            source = root / "qwen_slice"
            output = root / "fixed_slice_qwen"
            weights = np.zeros((16, 2048), dtype=np.float32)
            activation = np.zeros(2048, dtype=np.float32)
            write_model_slice(source, weights, activation, {"model": "Qwen2.5-1.5B-Instruct"})

            prepare(source, output)

            self.assertEqual(len((output / "weights.mem").read_text().splitlines()), 1024)
            self.assertEqual(len((output / "activation.mem").read_text().splitlines()), 64)
            self.assertEqual(len((output / "expected.mem").read_text().splitlines()), 256)

    def test_verify_accepts_multigroup_rom_images(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path("tmp")) as tmp:
            root = Path(tmp)
            source = root / "qwen_slice"
            output = root / "fixed_slice_qwen"
            checked = root / "checked"
            weights = np.zeros((16, 2048), dtype=np.float32)
            activation = np.zeros(2048, dtype=np.float32)
            write_model_slice(source, weights, activation, {"model": "Qwen2.5-1.5B-Instruct"})
            prepare(source, output)

            report = verify_slice(output, checked)

            self.assertEqual(report["config"]["N"], 16)
            self.assertEqual(report["config"]["K"], 2048)
            self.assertEqual(len(report["calculated"]), 256)


if __name__ == "__main__":
    unittest.main(verbosity=2)
