"""T2 evidence audit/probe. Never supplies budgets or declares target readiness."""
import argparse
import collections
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = 'Bytestring0/FPGA_RV32IM_VibeOS'
COMMIT = 'c1bc715b276db48cf6e6b640701d51b72e984d77'
REPO_PATHS = set('''Makefile README.md sw/link.ld sw/start.S sw/platform.h
sw/coremark/core_portme.c sw/coremark/core_portme.h rtl/qinglong_soc.sv rtl/rv32_core.sv
rtl/rv32_csr.sv rtl/rv32_decode.sv rtl/rv32_pkg.sv rtl/qinglong_fpga_top.sv
fpga/board/qinglong_board_clock.sv fpga/board/qinglong_board_system.sv fpga/generated/qinglong_all.sv
fpga/build.tcl RiscV.pds docs/CPU设计说明.md docs/性能与验证报告.md docs/青龙OS与即时应用设计.md
docs/上板调试记录.md docs/results/board-81mhz/manifest.json
docs/results/board-81mhz/board81-run1.uart.log docs/results/board-27mhz/coremark-manifest.json
scripts/run_coremark.py scripts/prepare_board.ps1'''.split())
SOURCE_PATHS = {'main:'+p:'docs/target_platform_sources/main/'+p for p in REPO_PATHS}
SOURCE_PATHS.update(dict(core_h='c/include/ir_core.h',core_c='c/src/ir_core.c',
    static_h='c/include/ir_static.h',static_c='c/src/ir_static.c',pc_h='c/include/ir_pc.h',pc_c='c/src/ir_pc.c',
    memory_py='inference_ref/memory.py',platform_py='inference_ref/platform.py',cbuild_py='inference_ref/c_backend.py'))
# T3 keeps the T2 facts auditable after the live runtime changes. These nine
# byte-identical source snapshots remain runtime 0.5.0 historical evidence.
for ident in ('core_h','core_c','static_h','static_c','pc_h','pc_c','memory_py','platform_py','cbuild_py'):
    SOURCE_PATHS[ident]='docs/target_platform_sources/framework_t2/'+SOURCE_PATHS[ident]
SOURCE_PATHS.update({ident:'docs/target_platform_sources/'+filename for ident,filename in (
    ('official','official_sources.json'),('repository_index','repository.json'),('pdf_index','local_pdfs.json'),
    ('contest','contest_pages.txt'),('manual','board_manual_pages.txt'),
    ('env_win','environment_20261025_windows.json'),('env_wsl','environment_20261025_wsl.json'))})
STATUSES = {'source_confirmed', 'normative', 'derived', 'historical_report', 'proposed', 'unknown'}
DOMAINS = {'toolchain', 'abi', 'endian', 'floating_point', 'memory', 'stack', 'reading', 'timing', 'synchronization'}
REQUIRED_IDS = set('''toolchain.contest toolchain.repository isa.baseline isa.optional toolchain.history
toolchain.current toolchain.link_mode toolchain.runtime_libraries toolchain.pds abi.selection abi.types
abi.native_layout abi.privilege endian.scalar endian.wire abi.unaligned floating_point.hardware
floating_point.reference_needs floating_point.softfloat floating_point.profile_clock memory.tcm
memory.linked_data_ceiling memory.ddr_physical memory.ddr_mapped memory.ddr_draft memory.cache
memory.free_bytes memory.heap_budget memory.arena_budget memory.trace_task_metadata_budgets
memory.context_arrays memory.no_runtime_malloc memory.null_address stack.reserve stack.alignment
stack.inspect_scratch stack.runtime_peak reading.current reading.reader_contract reading.target_adapter
reading.proposal timing.counters timing.consistent_read timing.default_clock timing.archived_profiles
timing.active_hz timing.callback timing.target_conversion synchronization.bus synchronization.fence
synchronization.target_hooks synchronization.dma synchronization.interrupt synchronization.atomics'''.split())
UNKNOWN_IDS = set('''toolchain.current toolchain.runtime_libraries abi.native_layout floating_point.softfloat
floating_point.profile_clock memory.free_bytes memory.heap_budget memory.arena_budget
memory.trace_task_metadata_budgets stack.runtime_peak reading.target_adapter timing.active_hz
synchronization.target_hooks'''.split())


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def within(root, relative):
    p = root / relative
    if Path(relative).is_absolute() or '..' in Path(relative).parts or p.is_symlink():
        raise ValueError('Unsafe evidence path: ' + relative)
    if not p.resolve().is_relative_to(root.resolve()) or not p.is_file():
        raise ValueError('Missing/outside evidence: ' + relative)
    return p


def audit(root=ROOT):
    root = Path(root)
    data = json.loads((root / 'docs/target_platform_constraints.json').read_text(encoding='utf-8'))
    manifest = json.loads((root / 'docs/target_platform_sources/manifest.json').read_text(encoding='utf-8'))
    if data['version'] != 1 or manifest['version'] != 1:
        raise ValueError('Unsupported T2 data version')
    if data.get('target_repository') != REPOSITORY or data.get('target_commit') != COMMIT:
        raise ValueError('Target repository/commit identity changed')
    sources = {}
    for source in manifest['sources']:
        if source['id'] in sources:
            raise ValueError('Duplicate source id')
        if SOURCE_PATHS.get(source['id']) != source['path']:
            raise ValueError('Unexpected source identity/path')
        p = within(root, source['path'])
        if digest(p) != source['sha256']:
            raise ValueError('Source SHA256 changed: ' + source['id'])
        if source['id'].startswith('main:'):
            path = source['id'][5:]
            url = f'https://github.com/{REPOSITORY}/blob/{COMMIT}/{quote(path,safe="/")}'
            if not source.get('git_blob_sha1') or source.get('ref') != COMMIT or source.get('url') != url:
                raise ValueError('Repository source requires pinned ref, URL and Git blob')
            b = p.read_bytes()
            actual = hashlib.sha1(b'blob ' + str(len(b)).encode() + b'\0' + b).hexdigest()
            if actual != source['git_blob_sha1']:
                raise ValueError('Remote blob changed: ' + source['id'])
        sources[source['id']] = source
    if set(sources) != set(SOURCE_PATHS):
        raise ValueError('T2 v1 requires all 43 source identities')
    repository = json.loads(within(root, SOURCE_PATHS['repository_index']).read_text(encoding='utf-8'))
    if repository.get('repository') != REPOSITORY or repository.get('ref') != COMMIT:
        raise ValueError('Repository index identity changed')
    entries = repository['entries']
    if len(entries) != len(REPO_PATHS) or {e['repository_path'] for e in entries} != REPO_PATHS:
        raise ValueError('Repository index must contain the same 27 paths')
    for e in entries:
        path = e['repository_path'];ident = 'main:'+path;s = sources[ident]
        if (e.get('id') != ident or e.get('path') != 'main/'+path or
                e.get('git_blob_sha1') != s['git_blob_sha1'] or e.get('url') != s['url']):
            raise ValueError('Repository index and manifest disagree')
    ids = set()
    for item in data['constraints']:
        if item['id'] in ids or item['status'] not in STATUSES or item['domain'] not in DOMAINS:
            raise ValueError('Invalid constraint identity/status/domain')
        ids.add(item['id'])
        if not item['evidence'] or not item['scope'] or not item['implication']:
            raise ValueError('Constraint needs evidence/scope/implication')
        if item['status'] == 'unknown' and (item['value'] is not None or not item.get('unblock')):
            raise ValueError('Unknown must remain null with an unblock task')
        for ref in item['evidence']:
            p = within(root, sources[ref['source']]['path'])
            lines = p.read_text(encoding='utf-8').splitlines()
            if not (1 <= ref['line'] <= len(lines)) or ref['needle'] not in lines[ref['line']-1]:
                raise ValueError('Source locator changed: ' + item['id'])
    if {c['domain'] for c in data['constraints']} != DOMAINS:
        raise ValueError('Missing required constraint domain')
    if ids != REQUIRED_IDS:
        raise ValueError('T2 v1 constraint set incomplete or changed')
    by_id = {c['id']: c for c in data['constraints']}
    if {c['id'] for c in data['constraints'] if c['status']=='unknown'} != UNKNOWN_IDS:
        raise ValueError('Unverified T2 fields cannot be promoted to confirmed')
    # These are evidence-derived snapshot invariants, not allocator settings.
    expected = {'memory.tcm': {'base':0,'end_exclusive':65536,'bytes':65536},
                'memory.linked_data_ceiling': {'bss_end_strictly_less_than':57344},
                'stack.reserve': {'top':65536,'reserved_min_bytes':8192,'guard_candidate_base':57344},
                'stack.inspect_scratch':32768,'memory.context_arrays':20480,
                'memory.ddr_physical': {'chip_count':2,'bits_per_chip':4294967296,'total_bytes':1073741824,'bus_bits':32},
                'memory.ddr_mapped':False,'memory.cache':False,'floating_point.hardware':False}
    for ident,value in expected.items():
        if by_id[ident]['value'] != value:
            raise ValueError('Source-derived snapshot value changed: '+ident)
    if set(data['target_budgets']) != {'arena_bytes','heap_bytes','trace_bytes','task_bytes','c_metadata_bytes','stack_peak_bytes'}:
        raise ValueError('Target budget categories incomplete')
    if any(v is not None for v in data['target_budgets'].values()):
        raise ValueError('T2 unmeasured budgets must remain null')
    if data['target_ready'] is not False or data['target_execution_verified'] is not False:
        raise ValueError('T2 is not target execution/readiness proof')
    if data['model'] is not None or data['quantization'] is not None:
        raise ValueError('T2 must remain model/quantization independent')
    return {'passed': True, 'evidence_scope':'historical_T2_runtime_0.5.0', 'constraint_count': len(ids), 'sources_checked': len(sources),
            'domains': sorted(DOMAINS), 'statuses': dict(collections.Counter(x['status'] for x in data['constraints'])),
            'target_ready': False, 'target_execution_verified': False,
            'target_budgets': data['target_budgets'], 'constraints_sha256': digest(root/'docs/target_platform_constraints.json'),
            'manifest_sha256': digest(root/'docs/target_platform_sources/manifest.json')}


def command(args):
    try:
        p = subprocess.run(args, capture_output=True, text=True, timeout=20, check=False)
        return {'command': args, 'exit_code': p.returncode, 'stdout': p.stdout, 'stderr': p.stderr}
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {'command': args, 'exit_code': None, 'error': str(exc)}


def probe_environment():
    names = ('riscv32-unknown-elf-gcc', 'riscv64-unknown-elf-gcc', 'riscv64-linux-gnu-gcc', 'clang', 'readelf', 'verilator')
    found = {name: shutil.which(name) for name in names}
    probes = []
    for name, path in found.items():
        if path:
            probes.append({'tool': name, 'path': path, 'sha256': digest(path), 'result': command([path, '--version'])})
    if sys.platform.startswith('linux'):
        probes.append({'result': command(['dpkg-query','-W','gcc-riscv64-unknown-elf','binutils-riscv64-unknown-elf','gcc-riscv64-linux-gnu'])})
    return {'platform': platform.platform(), 'python': sys.version, 'cwd': os.getcwd(),
            'scope': 'Current process PATH and named dpkg packages only; not a whole disk or all WSL distributions inventory.',
            'paths': found, 'probes': probes, 'cross_compile_performed': False, 'board_accessed': False,
            'target_toolchain_verified': False,
            'note': 'Presence/version alone cannot certify RV32 multilib, newlib/libgcc/fenv or runtime execution.'}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--probe-environment', action='store_true')
    args = p.parse_args()
    # An exclusive file leaves any previous evidence untouched.
    result = audit()
    if args.probe_environment:
        result['environment'] = probe_environment()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps({k: v for k, v in result.items() if k != 'environment'}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
