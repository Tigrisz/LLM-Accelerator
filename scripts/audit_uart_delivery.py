"""Recheck archived board UART data and groupwise dequantization, without hardware."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import zipfile

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.compare_results import golden_values, sha256
from scripts.decode_result_uart import decode
from model.golden_gemv import gemv_partial_sums
from model.pack_weights import unpack_weight_matrix


def dequantize(partials, scales, activation_scale):
    p, s, a = np.asarray(partials), np.asarray(scales), np.asarray(activation_scale)
    if p.ndim != 2 or not p.size or p.dtype.kind != 'i' or np.any(p < -(2**31)) or np.any(p > 2**31-1):
        raise ValueError('partials must be a nonempty signed INT32-range matrix')
    if s.shape != p.shape or s.dtype.kind != 'f' or a.shape != () or a.dtype.kind != 'f':
        raise ValueError('scales must be floating [rows,groups] and activation scale scalar')
    if not np.all(np.isfinite(s)) or np.any(s <= 0) or not np.isfinite(a) or a <= 0:
        raise ValueError('scales must be finite and positive')
    return np.sum(p.astype(np.float64) * s.astype(np.float64) * float(a), axis=1)


def unified_capture(frame, source, run_id):
    decoded = decode(frame, source=source)
    return dict(format_version=1, source=source, run_id=run_id, completed=True,
                completion_basis='complete framed UART payload; not a hardware done flag',
                raw_sha256=hashlib.sha256(frame).hexdigest(),
                results=[{key: r[key] for key in ('row_id', 'group_id', 'partial_sum')}
                         for r in decoded['records']])


def write(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n', encoding='utf-8')


def check(condition, message):
    if not condition:
        raise ValueError(message)


def verify_zip(path):
    expected = path.with_suffix(path.suffix + '.sha256').read_text().split()[0]
    check(sha256(path) == expected, 'delivery ZIP hash mismatch')
    with zipfile.ZipFile(path) as archive:
        prefix = path.stem + '/'
        count = 0
        for line in archive.read(prefix + 'SHA256SUMS.txt').decode().splitlines():
            digest, name = line.split('  ', 1)
            check(hashlib.sha256(archive.read(prefix + name)).hexdigest() == digest,
                  f'ZIP member hash mismatch: {name}')
            count += 1
    return dict(sha256=expected, members_checked=count)


def audit(output, simulation=None):
    evidence = ROOT / 'evidence/uart_board/2026-10-21'
    model = evidence / 'model_slice'
    output.mkdir(parents=True, exist_ok=True)
    write(output / 'summary.json', dict(status='running'))
    delivery = verify_zip(ROOT / 'deliveries/qwen_uart_board_handoff_2026-10-21.zip')
    hashes = {}
    for line in (evidence / 'SHA256SUMS.txt').read_text().splitlines():
        digest, name = line.split('  ', 1)
        check(sha256(evidence / name) == digest, f'evidence hash mismatch: {name}')
        hashes[name] = digest
    manifest = json.loads((evidence / 'verification_manifest.json').read_text())
    provenance_dir = ROOT / 'evidence/model_provenance/2026-10-21'
    for line in (provenance_dir / 'SHA256SUMS.txt').read_text().splitlines():
        digest, name = line.split('  ', 1)
        check(sha256(provenance_dir / name) == digest, f'provenance hash mismatch: {name}')
    provenance = json.loads((provenance_dir / 'provenance.json').read_text())
    for item in provenance['payload_comparison']:
        check(sha256(ROOT / item['file']) == item['sha256'], f'provenance payload mismatch: {item["file"]}')
    for entry in [manifest['bitstream'], *manifest['initialization_files']]:
        check(sha256(ROOT / entry['file']) == entry['sha256'], f'manifest mismatch: {entry["file"]}')
    cfg = json.loads((model / 'config.json').read_text())
    n, k, group = cfg['N'], cfg['padded_K'], cfg['group_size']
    check((n, k, group, cfg['source_cols']) == (16, 2048, 128, 1536), 'unexpected baseline dimensions')
    weights = (model / 'weight_packed.bin').read_bytes()
    activation = (model / 'activation_int8.bin').read_bytes()
    check(len(weights) == n*k//2 and len(activation) == k, 'packed size mismatch')
    w = np.asarray(unpack_weight_matrix(weights, n, k, group), dtype=np.int64)
    x = np.frombuffer(activation, dtype=np.int8).astype(np.int64)
    check(not np.any(w[:, 1536:]) and not np.any(x[1536:]), 'nonzero padded columns')
    calculated = np.asarray(gemv_partial_sums(w.tolist(), x.tolist()), dtype=np.int32)
    golden_path = model / 'expected_partial.npy'
    expected = np.asarray(golden_values(golden_path), dtype=np.int32)
    np.testing.assert_array_equal(calculated, expected)
    mem = ROOT / 'fpgatest/qwen_slice/prj/mem'
    np.testing.assert_array_equal(expected, golden_values(mem / 'expected.mem', n, k//group))
    for filename, packed, word_bytes in [('weights.mem', weights, 16), ('activation.mem', activation, 32)]:
        words = (mem / filename).read_text().split()
        check(all(len(word) == word_bytes*2 for word in words), f'{filename} width mismatch')
        check(b''.join(int(word, 16).to_bytes(word_bytes, 'little') for word in words) == packed,
              f'{filename} differs from model input')
    scales = np.load(model / 'scales.npy', allow_pickle=False)
    activation_scale = np.load(model / 'activation_scale.npy', allow_pickle=False)
    reference = dequantize(calculated, scales, activation_scale)
    reconstructed = (w.astype(np.float64) * np.repeat(scales.astype(np.float64), group, axis=1)) @ (x * float(activation_scale))
    np.testing.assert_allclose(reference, reconstructed, rtol=1e-12, atol=1e-12)
    runs = []
    inputs = [(evidence / f'run{i}.bin', 'board', f'board-run{i}') for i in (1, 2, 3)]
    if simulation:
        inputs.append((simulation, 'simulation', 'uart-rtl'))
    for raw, source, run_id in inputs:
        data = unified_capture(raw.read_bytes(), source, run_id)
        data['bitstream_sha256'] = manifest['bitstream']['sha256'] if source == 'board' else None
        data['provenance_note'] = ('B archived capture; bitstream association from manifest, not UART ID'
                                   if source == 'board' else 'RTL simulation, not board capture')
        if source == 'board':
            record = manifest['runs'][len(runs)]
            check(data['raw_sha256'] == record['sha256'], 'raw/manifest hash mismatch')
            supplied = json.loads(raw.with_suffix('.json').read_text())['records']
            check(data['results'] == [{key: r[key] for key in ('row_id', 'group_id', 'partial_sum')} for r in supplied],
                  'B JSON differs from raw UART')
        capture, report = output / f'{run_id}.json', output / f'{run_id}_comparison.json'
        write(capture, data)
        command = [sys.executable, str(ROOT / 'scripts/compare_results.py'), '--golden', str(golden_path),
                   '--capture', str(capture), '--report', str(report)]
        if source == 'board':
            command += ['--bitstream', str(ROOT / manifest['bitstream']['file'])]
        subprocess.run(command, check=True, timeout=60, capture_output=True, text=True)
        partials = np.asarray([r['partial_sum'] for r in data['results']], dtype=np.int32).reshape(n, -1)
        y = dequantize(partials, scales, activation_scale)
        np.testing.assert_allclose(y, reconstructed, rtol=1e-12, atol=1e-12)
        runs.append(dict(run_id=run_id, source=source, records=len(data['results']),
                         raw_sha256=data['raw_sha256'], comparison=report.name,
                         dequantized_output=y.tolist(), max_abs_reconstruction_error=float(np.max(np.abs(y-reconstructed)))))
    check(len({r['raw_sha256'] for r in runs[:3]}) == 1, 'board reset runs differ')
    summary = dict(status='pass', config=cfg, delivery=delivery, evidence_sha256=hashes,
                   bitstream_sha256=manifest['bitstream']['sha256'], runs=runs,
                   integer_reference='256 partial sums independently recomputed',
                   dequantization='float64 group scaling versus reconstructed quantized dot product; rtol=atol=1e-12',
                   original_float_accuracy='not evaluated: original floating weights/activation/reference absent',
                   checkpoint_revision=provenance['checkpoint_revision'],
                   checkpoint_evidence='B fixed-snapshot replay report; payload hashes checked by A, model replay not rerun by A',
                   provenance_sha256=sha256(provenance_dir / 'provenance.json'),
                   board_provenance='B capture records; A independently rechecked files without hardware')
    write(output / 'summary.json', summary)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'build/reports/uart_acceptance')
    parser.add_argument('--simulation', type=Path)
    args = parser.parse_args()
    # Generated reports must not overwrite tracked evidence or sources.
    check(args.output.resolve().is_relative_to((ROOT / 'build/reports').resolve()),
          'output must be under build/reports')
    try:
        summary = audit(args.output, args.simulation)
    except Exception as exc:
        args.output.mkdir(parents=True, exist_ok=True)
        write(args.output / 'summary.json', dict(status='fail', error=str(exc)))
        raise
    print(f"PASS UART_ACCEPTANCE runs={len(summary['runs'])} integer/dequantization=matched")


if __name__ == '__main__':
    main()
