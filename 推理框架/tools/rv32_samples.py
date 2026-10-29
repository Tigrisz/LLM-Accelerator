"""T5 inventory, capacity classification and observed-output gates."""
import hashlib
from pathlib import Path
import re
import sys
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from inference_ref.fixtures import read_fixture
from inference_ref.suite import verify_suite

FROZEN_SUITE_SHA256='f8420082c5b9680f942fbf7e3aba8292c114cc44fef10a4af3e0eb64b52fcb98'


def verify_fixture_mapping(fixture,package,feeds):
    source={('y' if t['name']=='expected' else t['name']):t for t in fixture.metadata['tensors']}
    if set(source)!={t.id for t in package.tensors}:raise ValueError('Migration changed tensor identities')
    for tensor in package.tensors:
        original=source[tensor.id];spec=tensor.spec
        if list(spec.shape)!=original['shape'] or list(spec.storage_shape)!=original['storage_shape'] or spec.dtype!=original['dtype'] or spec.layout!=original['layout']:
            raise ValueError('Migration changed original dtype/layout/shape/storage_shape')
        if tensor.role=='input':
            value=feeds[tensor.id]
            if tuple(value.shape)!=spec.shape or value.dtype.name!=spec.dtype:raise ValueError('Migration changed input shape/dtype')
            storage=np.zeros(spec.storage_shape,dtype='<f4' if spec.dtype=='float32' else '<i4');storage[tuple(slice(0,d) for d in spec.shape)]=value;data=storage.tobytes()
        elif tensor.role=='constant':data=package.constant_array(tensor.id).astype('<f4' if spec.dtype=='float32' else '<i4',copy=False).tobytes()
        else:continue
        if hashlib.sha256(data).hexdigest()!=original['sha256']:raise ValueError('Migration changed original physical input/weight bytes')
    return True


def inventory(root,dtype='int32'):
    if dtype not in ('int32','float32'):raise ValueError('Only frozen INT32/FP32 migration is supported')
    root=Path(root)
    if not root.is_dir() or root.is_symlink():raise ValueError('Missing/nonregular frozen fixture root')
    index=root/'suite.json'
    if not index.is_file() or index.is_symlink() or hashlib.sha256(index.read_bytes()).hexdigest()!=FROZEN_SUITE_SHA256:
        raise ValueError('Frozen suite index identity mismatch')
    checked=verify_suite(root)
    if not checked['passed'] or checked['case_count']!=54 or checked['passed_count']!=54:raise ValueError('Frozen suite contains missing/changed/invalid samples')
    names={r['case_id'] for r in checked['cases']}
    expected={'suite.json'}|{f'{name}/{file}' for name in names for file in ('manifest.json','data.bin')}
    paths=list(root.rglob('*'))
    if any(p.is_symlink() for p in paths) or {p.relative_to(root).as_posix() for p in paths if p.is_file()}!=expected:
        raise ValueError('Frozen fixture file set differs from complete suite')
    rows=[]
    for path in sorted(root.glob('*/manifest.json')):
        fixture=read_fixture(path.parent);meta=fixture.metadata
        case_dtype=fixture.expected.dtype.name;selected=case_dtype==dtype
        rows.append({'case_id':meta['case_id'],'dtype':case_dtype,'operation':meta['operation']['name'],
            'selected':selected,'target_status':'pending' if selected else 'not_in_scope',
            'shapes':{t['name']:t['shape'] for t in meta['tensors']},
            'storage_shapes':{t['name']:t['storage_shape'] for t in meta['tensors']},
            'payload_bytes':meta['payload']['byte_length'],'manifest_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
            'payload_sha256':meta['payload']['sha256']})
    if len(rows)!=54 or sum(r['selected'] for r in rows)!=27 or sum(r['dtype']=='float32' for r in rows)!=27:
        raise ValueError('Expected frozen 27 INT32/27 FP32 samples')
    return rows


def link_state(code,stderr):
    if code==0:return 'linked'
    if code!=1:return 'tool_error'
    patterns=[r'TCM image/static buffers overlap reserved stack',r"region [`']RAM['`] overflowed by [0-9]+ bytes",
        r".*section [`'][^`']+['`] will not fit in region [`']RAM['`]",
        r'section \.stack VMA \[[0-9a-fA-FxX, ]+\] overlaps section \.[\w.]+ VMA \[[0-9a-fA-FxX, ]+\]',
        r'.*: section \.stack lma 0x[0-9a-fA-F]+ adjusted to 0x[0-9a-fA-F]+']
    capacity=False
    for line in stderr.splitlines():
        if not line.strip():continue
        if line.strip()=='collect2: error: ld returned 1 exit status':continue
        message=line.split('ld: ',1)[-1].strip()
        if not any(re.fullmatch(pattern,message) for pattern in patterns):return 'tool_error'
        capacity=True
    if capacity:return 'blocked_tcm'
    return 'tool_error'


def parse_stream(stdout):
    fields={};outputs={}
    for line in stdout.splitlines():
        if '=' not in line:continue
        name,value=line.split('=',1)
        if name in fields or name in outputs:raise ValueError('Duplicate target/RTL evidence field')
        if name.endswith('_OUTPUT'):
            if not re.fullmatch(r'(?:[0-9a-fA-F]{2})+',value):raise ValueError('Malformed output bytes')
            outputs[name]=value.lower()
        elif re.fullmatch('[A-Z_0-9]+',name):
            if not re.fullmatch('[0-9a-fA-F]+',value):raise ValueError('Malformed numeric evidence')
            fields[name]=int(value,10 if name.startswith('RTL_') else 16)
    return fields,outputs


def check_termination(fields,code):
    if not (code==0 and fields.get('T5_STATUS')==0 and fields.get('T5_RUNTIME_ABI')==2 and fields.get('T5_POINTER_BYTES')==4 and
        fields.get('RTL_DONE')==1 and fields.get('RTL_EXIT')==0 and fields.get('RTL_TRAPS')==0 and
        fields.get('RTL_STACK_STARTED')==1 and fields.get('RTL_STACK_VIOLATIONS')==0 and
        type(fields.get('RTL_CYCLES')) is int and fields['RTL_CYCLES']>0 and
        type(fields.get('RTL_MIN_SP')) is int and 0xe000<=fields['RTL_MIN_SP']<=65536 and fields['RTL_MIN_SP']%16==0):
        raise ValueError('Target completion, ABI, trap or stack evidence failed/incomplete')


class NumericalMismatch(ValueError):
    """Complete execution evidence, but actual numerical bytes differ."""


def validate_recovery_run(stdout,code,gate,expected):
    fields,outputs=parse_stream(stdout)
    if set(outputs)!=set(expected):raise ValueError('Recovery output identities missing')
    if outputs==expected:return gate(stdout,code)
    repaired='\n'.join(k+'='+expected[k] if (k:=line.split('=',1)[0]) in expected else line for line in stdout.splitlines())
    gate(repaired,code)  # Prove all original controls before classifying the actual output mismatch.
    raise NumericalMismatch('Complete fault recovery produced wrong bytes')


def validate_exact_run(stdout,code,expected,nodes):
    fields,outputs=parse_stream(stdout)
    required={'RUN_0_OUTPUT','RUN_1_OUTPUT','RUN_2_OUTPUT','RECOVER_OUTPUT','REBIND_OUTPUT'}
    if set(outputs)!=required or set(expected)!=required:raise ValueError('Complete five output identities required')
    result=validate_sample_run(stdout,code,outputs,nodes)
    if outputs!=expected:raise NumericalMismatch('Actual target output bytes differ')
    return result


def validate_sample_run(stdout,code,expected,nodes):
    fields,outputs=parse_stream(stdout);check_termination(fields,code)
    if fields.get('T5_CHECKS_MASK')!=8191 or any(fields.get(f'RUN_{i}_NODES')!=nodes for i in range(3)):
        raise ValueError('Repeated execution or negative/lifecycle checks missing')
    if fields.get('T5_SYNC_PUBLISH')!=6 or fields.get('T5_SYNC_ACQUIRE')!=6:raise ValueError('Synchronization/recovery/rebind runs missing')
    if outputs!=expected:raise ValueError('Actual target output bytes differ or are missing')
    return {'passed':True,'fields':fields,'outputs':outputs,'observed_stack_bytes':65536-fields['RTL_MIN_SP'],
            'full_stack_worst_case':None,'board_verified':False}


def validate_overflow_run(stdout,code,expected):
    fields,outputs=parse_stream(stdout);check_termination(fields,code)
    if any(fields.get(name)!=value for name,value in {'T5_OVERFLOW_STATUS':6,'T5_OVERFLOW_NODES':0,'T5_ATOMIC':1,'T5_REPAIRED':1}.items()) or set(outputs)!={'RECOVER_OUTPUT'}:
        raise ValueError('Numeric overflow/atomicity/repaired execution evidence missing')
    if outputs!={'RECOVER_OUTPUT':expected}:raise NumericalMismatch('Overflow repaired output bytes differ')
    return {'passed':True,'fields':fields,'outputs':outputs,'observed_stack_bytes':65536-fields['RTL_MIN_SP'],
            'full_stack_worst_case':None,'board_verified':False}
