"""Task A: independent archived-board acceptance and float metric cross-check."""
import json
import math
from pathlib import Path
import struct
import subprocess
import sys
import uuid
import zipfile

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.audit_uart_delivery import verify_zip, check
from scripts.compare_results import compare, sha256
from scripts.evaluate_qwen_quantization import evaluate


def write(path, data):
    path.write_text(json.dumps(data, indent=2, allow_nan=False) + '\n', encoding='utf-8')


def raw_records(raw, count):
    check(len(raw) == 9 + 8*count and raw[:3] == b'\xa5\x5a\x01'
          and raw[-2:] == b'\x5a\xa5' and struct.unpack_from('<I', raw, 3)[0] == count,
          'invalid UART header/count/length/footer')
    return [dict(zip(('row_id', 'group_id', 'partial_sum'), struct.unpack_from('<HHi', raw, 7+8*i)))
            for i in range(count)]


def board_case(k, output):
    folder = ROOT / f'evidence/a_multigroup_pds/2026-10-21/k{k}'
    fixture = ROOT / f'tests/fixtures/a_multigroup/lanes16_n3_k{k}'
    output.mkdir()
    manifest = json.loads((folder / 'verification_manifest.json').read_text())
    for name, info in manifest['files'].items():
        check(sha256(folder / name) == info['sha256'], f'frozen evidence mismatch: {name}')
    source = json.loads((ROOT / 'tests/fixtures/a_multigroup/source_manifest.json').read_text())
    archive = ROOT / source['archive']
    check(sha256(archive) == source['archive_sha256'], 'original A archive mismatch')
    with zipfile.ZipFile(archive) as z:
        for name, info in source['cases'][f'lanes16_n3_k{k}']['files'].items():
            check((fixture/name).read_bytes() == z.read(info['archive_member']), f'original A input changed: {name}')
    cfg = json.loads((fixture/'config.json').read_text())
    check((cfg['N'], cfg['K'], cfg['padded_K'], cfg['group_size'], cfg['lanes']) == (3,k,k,128,16), 'wrong case')
    packed = (fixture/'weight_packed.bin').read_bytes()
    activation = (fixture/'activation_int8.bin').read_bytes()
    check(len(packed) == 3*k//2 and len(activation) == k, 'input length mismatch')
    w = [v-16 if v >= 8 else v for byte in packed for v in (byte & 15, byte >> 4)]
    x = [v-256 if v >= 128 else v for v in activation]
    groups = k//128
    expected = [[sum(w[r*k+i]*x[i] for i in range(g*128,(g+1)*128)) for g in range(groups)] for r in range(3)]
    np.testing.assert_array_equal(expected, np.load(fixture/'expected_partial.npy', allow_pickle=False))
    for filename, data, width in [('weights.mem',packed,16), ('activation.mem',activation,32)]:
        words = (folder/'rom'/filename).read_text().split()
        check(all(len(word)==width*2 for word in words), 'ROM word width mismatch')
        check(b''.join(int(word,16).to_bytes(width,'little') for word in words)==data, 'ROM input mismatch')
    check([int(v,16) for v in (folder/'rom/expected.mem').read_text().split()]
          == [v & 0xffffffff for row in expected for v in row], 'ROM golden mismatch')
    bitstreams = list((folder/'bitstream').glob('*.sbit'))
    check(len(bitstreams)==1 and sha256(bitstreams[0])==manifest['bitstream_sha256'], 'bitstream mismatch')
    program_log = (folder/'pds/program.log').read_text()
    check('0x081ffca0' in program_log and '0x00602899' in program_log.lower(), 'program status/device evidence missing')
    runs = []
    for i in (1,2,3):
        path = folder/f'board/run{i}.bin'
        check(sha256(path)==manifest['runs'][i-1]['sha256'], 'raw hash mismatch')
        records = raw_records(path.read_bytes(),3*groups)
        capture = dict(format_version=1,source='board',run_id=f'a-recheck-k{k}-run{i}',completed=True,
                       completion_basis='complete UART frame, not hardware done flag',results=records,
                       bitstream_sha256=manifest['bitstream_sha256'],raw_sha256=sha256(path))
        supplied = json.loads((folder/f'board/run{i}_a_format.json').read_text())
        check(supplied['source']=='board' and supplied['results']==records, 'B JSON/raw disagreement')
        report = compare(expected,capture)
        check(report['status']=='pass', f'capture mismatch: {report}')
        write(output/f'run{i}.json',capture)
        subprocess.run([sys.executable,str(ROOT/'scripts/compare_results.py'),
                        '--golden',str(fixture/'expected_partial.npy'),'--capture',str(output/f'run{i}.json'),
                        '--bitstream',str(bitstreams[0]),'--report',str(output/f'run{i}_comparison.json')],
                       check=True,capture_output=True,text=True,timeout=60)
        runs.append(dict(run=i,records=3*groups,bytes=path.stat().st_size,sha256=sha256(path),status='pass'))
    check(len({r['sha256'] for r in runs})==1,'reset runs differ')
    return dict(K=k,N=3,source='B archived physical captures; A independent offline audit',
                input_kind='A synthetic integer',bitstream_sha256=manifest['bitstream_sha256'],runs=runs,
                provenance_limit='UART has no LED/bitstream ID; key/LED observations are B records')


def float_check(output):
    evidence = ROOT/'evidence/qwen_float/2026-10-22'
    report = evaluate(evidence/'reference',ROOT/'evidence/uart_board/2026-10-21/model_slice',
                      ROOT/'evidence/uart_board/2026-10-21',ROOT/'fpgatest/qwen_slice/prj/mem',output,
                      ROOT/'evidence/model_provenance/2026-10-21/provenance.json')
    w = np.load(evidence/'reference/weights_fp32.npy',allow_pickle=False).astype(np.float64)
    x = np.load(evidence/'reference/activation_fp32.npy',allow_pickle=False).astype(np.float64)
    # Scalar fsum uses a different reduction from the producer's grouped NumPy sum.
    reference = [math.fsum(float(a)*float(b) for a,b in zip(row,x)) for row in w]
    np.testing.assert_allclose(reference,report['reference_fp64'],rtol=1e-13,atol=1e-13)
    actual = report['quantized_dequantized_fp64']
    errors = [a-b for a,b in zip(actual,reference)]
    norm = lambda values: math.sqrt(math.fsum(v*v for v in values))
    metrics = dict(max_abs_error=max(map(abs,errors)),mae=math.fsum(map(abs,errors))/len(errors),
                   rmse=norm(errors)/math.sqrt(len(errors)),relative_l2=norm(errors)/norm(reference),
                   max_relative_error_nonzero=max(abs(e/r) for e,r in zip(errors,reference) if abs(r)>1e-12),
                   cosine_similarity=math.fsum(a*b for a,b in zip(actual,reference))/(norm(actual)*norm(reference)))
    frozen = json.loads((evidence/'evaluation/summary.json').read_text())
    for key,value in metrics.items():
        check(math.isclose(value,report['metrics'][key],rel_tol=1e-12,abs_tol=1e-12),f'independent metric mismatch: {key}')
        check(math.isclose(value,frozen['metrics'][key],rel_tol=1e-12,abs_tol=1e-12),f'B metric mismatch: {key}')
    rows = [dict(row_id=i,reference=ref,actual=got,absolute_error=abs(got-ref),
                 relative_error=abs((got-ref)/ref) if abs(ref)>1e-12 else None)
            for i,(ref,got) in enumerate(zip(reference,actual))]
    write(output/'a_independent_metrics.json',dict(metrics=metrics,rows=rows,accuracy_accepted=False,
          acceptance_reason='No accuracy threshold or representative evaluation set agreed',
          model_replay_by_A=False,reference_basis='B BF16-loaded values stored FP32; scalar FP64 dot rechecked by A'))
    return dict(metrics=metrics,max_absolute_row=max(rows,key=lambda r:r['absolute_error']),
                max_relative_row=max(rows,key=lambda r:r['relative_error'] or 0),accuracy_accepted=False)


def main():
    root = ROOT/'build/reports/a_board_float_acceptance'
    output = root/uuid.uuid4().hex
    output.mkdir(parents=True)
    summary = dict(status='running',attempt=output.name)
    write(root/'summary.json',summary)
    try:
        summary['packages'] = {name:verify_zip(ROOT/'deliveries'/f'{name}.zip') for name in
                               ('a_multigroup_board_handoff_2026-10-22','qwen_float_handoff_2026-10-22')}
        summary['board_cases'] = [board_case(k,output/f'k{k}') for k in (256,384)]
        summary['qwen_float'] = float_check(output/'float')
        summary['status'] = 'pass'
    except Exception as exc:
        summary.update(status='fail',error=str(exc))
        raise
    finally:
        write(output/'summary.json',summary)
        write(root/'summary.json',summary)
    print(f'PASS A_BOARD_FLOAT_ACCEPTANCE board_runs=6 records=45 float_rows=16 report={output}')


if __name__=='__main__':
    main()
