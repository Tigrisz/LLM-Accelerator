"""Protect pre-quantization values, grouped scaling, and immutable evidence."""
import hashlib
import json
from pathlib import Path
import struct
import tempfile
import unittest

import numpy as np

from model.model_slice import write_model_slice
from scripts.prepare_fixed_slice_mem import prepare

try:
    from model.float_reference import write_float_reference
    from scripts.evaluate_qwen_quantization import evaluate, error_metrics
except ImportError:
    write_float_reference = evaluate = error_metrics = None


class FloatReferenceTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(write_float_reference, "float reference export is missing")
        work = Path(__file__).resolve().parents[1] / 'tmp'
        work.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=work)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.w = np.zeros((2, 256), dtype=np.float32)
        self.w[0, :2] = [1, .5]
        self.w[0, 128] = 2
        self.x = np.zeros(256, dtype=np.float32)
        self.x[:2] = [1, 2]
        self.x[128] = -1
        self.meta = dict(model="synthetic-test", layer=0, rows_start=0,
                         cols_start=0, prompt="test", token_index=-1,
                         source_cols=256, zero_padded_cols=0,
                         checkpoint_revision="test-only", source_weight_dtype="torch.bfloat16",
                         source_activation_dtype="torch.bfloat16", target_has_bias=False)

    def reference(self):
        out = self.root / "float"
        write_float_reference(out, self.w, self.x, self.meta)
        return out

    def fixture(self):
        ref = self.reference()
        q = self.root / "quantized"
        write_model_slice(q, self.w, self.x, self.meta)
        mem = self.root / "mem"
        prepare(q, mem)
        expected = np.load(q / "expected_partial.npy")
        board = self.root / "board"
        board.mkdir()
        frame = b'\xa5\x5a\x01' + struct.pack('<I', 4)
        for r in range(2):
            for g in range(2):
                frame += struct.pack('<HHi', r, g, int(expected[r, g]))
        frame += b'\x5a\xa5'
        runs = []
        for n in (1, 2, 3):
            (board / f'run{n}.bin').write_bytes(frame)
            runs.append(dict(sha256=hashlib.sha256(frame).hexdigest()))
        (board / 'verification_manifest.json').write_text(json.dumps(dict(runs=runs)))
        return ref, q, board, mem

    def test_exports_unquantized_values_and_fp64_group_reference(self):
        ref = self.reference()
        np.testing.assert_array_equal(np.load(ref / 'weights_fp32.npy'), self.w)
        np.testing.assert_array_equal(np.load(ref / 'activation_fp32.npy'), self.x)
        np.testing.assert_array_equal(np.load(ref / 'reference_groups_fp64.npy'), [[2, -2], [0, 0]])
        np.testing.assert_array_equal(np.load(ref / 'reference_fp64.npy'), [0, 0])
        self.assertEqual(np.load(ref / 'reference_fp64.npy').dtype, np.dtype('float64'))
        with self.assertRaises(FileExistsError):
            write_float_reference(ref, self.w, self.x, self.meta)

    def test_rejects_nonfinite_or_false_zero_padding(self):
        for bad in (float('nan'), float('inf')):
            w = self.w.copy()
            w[0, 0] = bad
            with self.assertRaises(ValueError):
                write_float_reference(self.root / 'bad', w, self.x, self.meta)
        with self.assertRaises(ValueError):
            write_float_reference(self.root / 'pad', self.w, self.x,
                                  {**self.meta, 'source_cols': 128, 'zero_padded_cols': 128})

    def test_metrics_define_zero_reference_without_nan(self):
        self.assertIsNotNone(error_metrics)
        m = error_metrics(np.array([0., 2.]), np.array([1., 1.]))
        self.assertEqual(m['max_abs_error'], 1.)
        self.assertEqual(m['mae'], 1.)
        self.assertEqual(m['rmse'], 1.)
        self.assertAlmostEqual(m['relative_l2'], 2**-.5)
        self.assertEqual(m['relative_error_excluded_count'], 1)
        self.assertEqual(m['max_relative_error_nonzero'], .5)
        self.assertIsNone(error_metrics(np.zeros(2), np.ones(2))['relative_l2'])

    def test_evaluates_requantization_mem_and_three_board_frames(self):
        ref, q, board, mem = self.fixture()
        before = {p: p.read_bytes() for directory in (q, board, mem) for p in directory.iterdir()}
        result = evaluate(ref, q, board, mem, self.root / 'evaluation')
        self.assertEqual(result['status'], 'pass')
        self.assertEqual(len(result['payload_checks']), 5)
        self.assertEqual(len(result['mem_checks']), 3)
        self.assertEqual(len(result['board_runs']), 3)
        self.assertGreater(result['metrics']['max_abs_error'], 0.)
        for p, content in before.items():
            self.assertEqual(p.read_bytes(), content)

    def test_rejects_quantized_payload_mismatch(self):
        ref, q, board, mem = self.fixture()
        data = bytearray((q / 'weight_packed.bin').read_bytes())
        data[0] ^= 1
        (q / 'weight_packed.bin').write_bytes(data)
        with self.assertRaisesRegex(ValueError, 'weight_packed'):
            evaluate(ref, q, board, mem, self.root / 'evaluation')

    def test_rejects_mismatched_prompt_even_if_quantized_values_match(self):
        ref, q, board, mem = self.fixture()
        cfg = json.loads((q / 'config.json').read_text())
        cfg['prompt'] = 'other token input'
        (q / 'config.json').write_text(json.dumps(cfg))
        with self.assertRaisesRegex(ValueError, 'prompt'):
            evaluate(ref, q, board, mem, self.root / 'evaluation')

    def test_rejects_tampered_float_file_and_mem(self):
        ref, q, board, mem = self.fixture()
        (mem / 'expected.mem').write_text('00000000\n' * 4)
        with self.assertRaisesRegex(ValueError, 'expected.mem'):
            evaluate(ref, q, board, mem, self.root / 'badmem')
        (ref / 'weights_fp32.npy').write_bytes(b'corrupt')
        with self.assertRaisesRegex(ValueError, 'weights_fp32'):
            evaluate(ref, q, board, mem, self.root / 'badfloat')

    def test_rejects_wrong_uart_tag_and_output_reuse(self):
        ref, q, board, mem = self.fixture()
        data = bytearray((board / 'run1.bin').read_bytes())
        data[7] = 1
        (board / 'run1.bin').write_bytes(data)
        m = json.loads((board / 'verification_manifest.json').read_text())
        m['runs'][0]['sha256'] = hashlib.sha256(data).hexdigest()
        (board / 'verification_manifest.json').write_text(json.dumps(m))
        with self.assertRaisesRegex(ValueError, 'tag|order'):
            evaluate(ref, q, board, mem, self.root / 'badtag')
        with self.assertRaises(FileExistsError):
            evaluate(ref, q, board, mem, ref)

    def test_rejects_output_inside_readonly_inputs(self):
        ref, q, board, mem = self.fixture()
        with self.assertRaisesRegex(ValueError, 'output'):
            evaluate(ref, q, board, mem, q / 'new-output')
        self.assertFalse((q / 'new-output').exists())

    def test_rejects_changed_checkpoint_revision(self):
        ref, q, board, mem = self.fixture()
        provenance = self.root / 'provenance.json'
        provenance.write_text(json.dumps(dict(checkpoint_revision='other-checkpoint',
                                               checkpoint_file_sha256={})))
        with self.assertRaisesRegex(ValueError, 'checkpoint'):
            evaluate(ref, q, board, mem, self.root/'wrong-revision', provenance=provenance)

    def test_rejects_incomplete_reference_hash_manifest(self):
        ref, q, board, mem = self.fixture()
        manifest = json.loads((ref/'manifest.json').read_text())
        del manifest['files']['reference_fp32.npy']
        (ref/'manifest.json').write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValueError, 'manifest'):
            evaluate(ref, q, board, mem, self.root/'incomplete')


if __name__ == '__main__':
    unittest.main()
