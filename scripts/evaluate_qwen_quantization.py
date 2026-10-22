"""Audit original float replay against immutable quantized payload, MEM and UART."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from model.model_slice import write_model_slice
from model.pack_weights import unpack_weight_matrix
from scripts.decode_result_uart import decode, verify_records
from scripts.prepare_fixed_slice_mem import prepare


def error_metrics(reference, actual) -> dict:
    ref, got = np.asarray(reference, dtype=np.float64), np.asarray(actual, dtype=np.float64)
    if ref.shape != got.shape or not ref.size or not np.isfinite(ref).all() or not np.isfinite(got).all():
        raise ValueError('finite, nonempty matching metric arrays required')
    err = got-ref
    nonzero = np.abs(ref) > 1e-12
    rn, en, gn = float(np.linalg.norm(ref)), float(np.linalg.norm(err)), float(np.linalg.norm(got))
    return dict(max_abs_error=float(np.max(np.abs(err))), mae=float(np.mean(np.abs(err))),
                rmse=float(np.sqrt(np.mean(err**2))), relative_l2=en/rn if rn else None,
                max_relative_error_nonzero=float(np.max(np.abs(err[nonzero]/ref[nonzero]))) if nonzero.any() else None,
                relative_error_excluded_count=int(ref.size-nonzero.sum()), relative_error_abs_threshold=1e-12,
                cosine_similarity=float(np.dot(ref.ravel(), got.ravel())/(rn*gn)) if rn and gn else None)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def check(condition, message):
    if not condition:
        raise ValueError(message)


def evaluate(reference: Path, quantized: Path, board: Path, mem: Path, output: Path, provenance=None) -> dict:
    output = Path(output)
    if output.exists():
        raise FileExistsError(output)
    if any(output.resolve().is_relative_to(Path(p).resolve()) for p in (reference, quantized, board, mem)):
        raise ValueError('output must not be inside read-only input directories')
    output.mkdir(parents=True, exist_ok=False)
    try:
        result = _evaluate(Path(reference), Path(quantized), Path(board), Path(mem), output, provenance)
    except Exception as exc:
        (output/'summary.json').write_text(json.dumps(dict(status='failed', error=str(exc)), indent=2)+'\n', encoding='utf-8')
        raise
    (output/'summary.json').write_text(json.dumps(result, indent=2, allow_nan=False)+'\n', encoding='utf-8')
    return result


def _evaluate(reference, quantized, board, mem, output, provenance):
    manifest = json.loads((reference/'manifest.json').read_text())
    required = {'weights_fp32.npy', 'activation_fp32.npy', 'reference_fp64.npy',
                'reference_groups_fp64.npy', 'reference_fp32.npy'}
    check(required.issubset(manifest['files']), 'reference manifest is missing required arrays')
    for name, meta in manifest['files'].items():
        check(Path(name).name == name, 'reference file must be a basename')
        check(digest(reference/name) == meta['sha256'], f'float hash mismatch: {name}')
    w = np.load(reference/'weights_fp32.npy', allow_pickle=False)
    x = np.load(reference/'activation_fp32.npy', allow_pickle=False)
    n, k, group = manifest['N'], manifest['K'], manifest['group_size']
    check(w.dtype == np.float32 and x.dtype == np.float32 and w.shape == (n, k) and x.shape == (k,), 'float dtype/shape mismatch')
    check(group == 128 and k % group == 0 and np.isfinite(w).all() and np.isfinite(x).all(), 'invalid float inputs')
    meta = manifest['metadata']
    provenance_check = None
    if provenance is not None:
        accepted = json.loads(Path(provenance).read_text())
        check(meta['checkpoint_revision'] == accepted['checkpoint_revision'], 'checkpoint revision mismatch')
        for name, wanted in accepted['checkpoint_file_sha256'].items():
            check(meta['checkpoint_sha256'].get(name) == wanted, f'checkpoint file mismatch: {name}')
        provenance_check = dict(sha256=digest(provenance), checkpoint_revision=meta['checkpoint_revision'],
                                matched_files=len(accepted['checkpoint_file_sha256']))
    cfg = json.loads((quantized/'config.json').read_text())
    for key in ('layer', 'rows_start', 'cols_start', 'prompt', 'token_index', 'source_cols', 'zero_padded_cols'):
        check(cfg[key] == meta[key], f'capture metadata mismatch: {key}')
    check((cfg['N'], cfg['K'], cfg['padded_K'], cfg['group_size']) == (n, k, k, group), 'quantized dimensions mismatch')
    check(0 < meta['source_cols'] <= k and meta['zero_padded_cols'] == k-meta['source_cols'], 'padding metadata mismatch')
    check(not np.any(w[:, meta['source_cols']:]) and not np.any(x[meta['source_cols']:]), 'nonzero float padding')
    recomputed_groups = (w.astype(np.float64)*x.astype(np.float64)).reshape(n, -1, group).sum(axis=2)
    floating = np.load(reference/'reference_fp64.npy', allow_pickle=False)
    np.testing.assert_array_equal(recomputed_groups, np.load(reference/'reference_groups_fp64.npy', allow_pickle=False))
    np.testing.assert_array_equal(floating, recomputed_groups.sum(axis=1))
    requantized = output/'requantized'
    write_model_slice(requantized, w, x, cfg)
    payload_checks = []
    for name in ('weight_packed.bin', 'activation_int8.bin', 'scales.npy', 'activation_scale.npy', 'expected_partial.npy'):
        check((requantized/name).read_bytes() == (quantized/name).read_bytes(), f'requantization mismatch: {name}')
        payload_checks.append(dict(file=name, sha256=digest(quantized/name), byte_identical=True))
    generated_mem = output/'requantized_mem'
    prepare(requantized, generated_mem)
    mem_checks = []
    for name in ('weights.mem', 'activation.mem', 'expected.mem'):
        check((generated_mem/name).read_bytes() == (mem/name).read_bytes(), f'ROM mismatch: {name}')
        mem_checks.append(dict(file=name, sha256=digest(mem/name), byte_identical=True))
    expected = np.load(quantized/'expected_partial.npy', allow_pickle=False)
    scales = np.load(quantized/'scales.npy', allow_pickle=False).astype(np.float64)
    activation_scale = float(np.load(quantized/'activation_scale.npy', allow_pickle=False))
    check(expected.dtype == np.int32 and expected.shape == (n, k//group), 'expected partial shape/dtype mismatch')
    check(scales.shape == expected.shape and np.isfinite(scales).all() and (scales > 0).all()
          and np.isfinite(activation_scale) and activation_scale > 0, 'invalid quantization scales')
    dequantized = (expected.astype(np.float64)*scales*activation_scale).sum(axis=1)
    qw = np.asarray(unpack_weight_matrix((quantized/'weight_packed.bin').read_bytes(), n, k, group), dtype=np.float64)
    qx = np.frombuffer((quantized/'activation_int8.bin').read_bytes(), dtype=np.int8).astype(np.float64)
    reconstructed_w = qw*np.repeat(scales, group, axis=1)
    reconstructed_x = qx*activation_scale
    independent = reconstructed_w @ reconstructed_x
    np.testing.assert_allclose(dequantized, independent, rtol=1e-12, atol=1e-12)
    board_manifest = json.loads((board/'verification_manifest.json').read_text())
    check(len(board_manifest['runs']) == 3, 'three board runs required')
    runs = []
    for i in (1, 2, 3):
        raw = board/f'run{i}.bin'
        check(digest(raw) == board_manifest['runs'][i-1]['sha256'], 'board frame hash mismatch')
        decoded = decode(raw.read_bytes(), source='board')
        for index, record in enumerate(decoded['records']):
            check((record['row_id'], record['group_id']) == divmod(index, k//group), 'UART tag order mismatch')
        verify_records(decoded, expected.ravel().tolist(), n, k//group)
        partials = np.asarray([r['partial_sum'] for r in decoded['records']], dtype=np.int32).reshape(n, -1)
        y = (partials.astype(np.float64)*scales*activation_scale).sum(axis=1)
        np.testing.assert_array_equal(y, dequantized)
        runs.append(dict(run=i, source='archived_board_not_new_capture', records=decoded['count'],
                         raw_sha256=digest(raw), dequantized_output=y.tolist(), metrics=error_metrics(floating, y)))
    check(len({r['raw_sha256'] for r in runs}) == 1, 'reset frames differ')
    np.save(output/'dequantized_fp64.npy', dequantized, allow_pickle=False)
    return dict(status='pass', status_meaning='data linkage and evaluation completed; no model accuracy acceptance threshold specified',
                reference_manifest_sha256=digest(reference/'manifest.json'), metadata=meta,
                accepted_provenance_check=provenance_check,
                N=n, physical_K=k, effective_K=meta['source_cols'], group_size=group,
                payload_checks=payload_checks, mem_checks=mem_checks, board_runs=runs,
                reference_fp64=floating.tolist(), quantized_dequantized_fp64=dequantized.tolist(),
                per_row_absolute_error=np.abs(dequantized-floating).tolist(),
                metrics=error_metrics(floating, dequantized),
                weight_metrics=error_metrics(w, reconstructed_w), activation_metrics=error_metrics(x, reconstructed_x),
                independent_dequantization_max_abs_error=float(np.max(np.abs(dequantized-independent))),
                fp32_reference_vs_fp64=error_metrics(floating, np.load(reference/'reference_fp32.npy', allow_pickle=False)),
                limitations=['one layer0 o_proj tile, one prompt/token only', 'not end-to-end model accuracy, throughput or DDR validation',
                             'FP32 storage of loaded BF16 values, not native FP32 checkpoint execution',
                             'bias excluded from both reference and integer GEMV', 'archived UART captures, not new board acquisition'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference', type=Path, required=True)
    parser.add_argument('--quantized', type=Path, default=ROOT/'evidence/uart_board/2026-10-21/model_slice')
    parser.add_argument('--board-dir', type=Path, default=ROOT/'evidence/uart_board/2026-10-21')
    parser.add_argument('--mem-dir', type=Path, default=ROOT/'fpgatest/qwen_slice/prj/mem')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--provenance', type=Path, default=ROOT/'evidence/model_provenance/2026-10-21/provenance.json')
    args = parser.parse_args()
    report = evaluate(args.reference, args.quantized, args.board_dir, args.mem_dir, args.output, args.provenance)
    print(json.dumps(dict(status=report['status'], metrics=report['metrics']), indent=2, allow_nan=False))


if __name__ == '__main__':
    main()
