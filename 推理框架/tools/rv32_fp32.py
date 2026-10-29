"""Finite FP32 evidence with frozen tolerances, separate byte/padding/determinism gates."""
import re
import numpy as np
from inference_ref.compare import compare_arrays
from rv32_samples import parse_stream,check_termination,validate_sample_run

SOURCES={'scalar','numpy','pc_core','pc_static'}
OUTPUTS={'RUN_0_OUTPUT','RUN_1_OUTPUT','RUN_2_OUTPUT','RECOVER_OUTPUT','REBIND_OUTPUT'}
HELPERS={'__adddf3','__subdf3','__muldf3','__extendsfdf2','__truncdfsf2'}


class FP32Mismatch(ValueError):
    """Complete successful target execution proved a numerical/determinism mismatch."""


def compare_output(actual_hex,expected,spec,policy):
    if spec.dtype!='float32' or policy.get('mode')!='abs_plus_rel':raise ValueError('FP32 abs_plus_rel policy required')
    raw=bytes.fromhex(actual_hex)
    if len(raw)!=spec.byte_length:raise ValueError('Physical FP32 output length mismatch')
    storage=np.frombuffer(raw,dtype='<f4').reshape(spec.storage_shape)
    selection=tuple(slice(0,d) for d in spec.shape);logical=storage[selection].copy()
    if expected.shape!=spec.shape or expected.dtype.name!='float32':raise ValueError('Reference dtype/shape changed')
    padding=np.ones(spec.storage_shape,dtype=bool);padding[selection]=False
    canonical=bool(np.all(storage.view('<u4')[padding]==0))
    result=compare_arrays(expected,logical,policy['atol'],policy['rtol'])
    return {**result,'passed':result['passed'] and canonical,'padding_zero_bytes':canonical,
            'bitwise_equal':logical.tobytes()==expected.tobytes()}


def validate_float_run(stdout,code,references,spec,policy,nodes):
    fields,outputs=parse_stream(stdout)
    if set(outputs)!=OUTPUTS or set(references)!={'normal','zero'} or any(not SOURCES<=set(r)<=SOURCES|{'stored'} for r in references.values()):
        raise ValueError('Every repeat/output and four independent references required')
    # Reuse lifecycle/termination checks only; FP numerics are checked below.
    lifecycle=validate_sample_run(stdout,code,outputs,nodes)
    if len({outputs[k] for k in OUTPUTS-{'RUN_1_OUTPUT'}})!=1:raise FP32Mismatch('Same-input repeats/recovery/rebind differ bitwise')
    comparisons={}
    for key,actual in outputs.items():
        label='zero' if key=='RUN_1_OUTPUT' else 'normal'
        comparisons[key]={name:compare_output(actual,ref,spec,policy) for name,ref in references[label].items()}
    if not all(c['passed'] for row in comparisons.values() for c in row.values()):raise FP32Mismatch('FP32 tolerance/nonfinite/padding comparison failed')
    return {**lifecycle,'comparisons':comparisons,'same_input_bitwise_deterministic':True}


def check_softfloat_symbols(symbols,disassembly):
    present={line.split()[-1] for line in symbols.splitlines() if len(line.split())>=3}
    if not HELPERS<=present:raise ValueError('Required FP64 soft-float helpers missing')
    opcodes=re.findall(r'^\s*[0-9a-f]+:\s+[0-9a-f]+\s+(\S+)',disassembly,re.M)
    if any(op.startswith('f') and op not in ('fence','fence.i') for op in opcodes):raise ValueError('Unexpected hardware FP instruction')
    return {'passed':True,'required_helpers':sorted(HELPERS),'hardware_fp_instructions':False}


def validate_float_faults(stdout,code):
    fields,outputs=parse_stream(stdout);check_termination(fields,code)
    required={'T6_NAN':5,'T6_POS_INF':5,'T6_NEG_INF':5,'T6_NONFINITE_EXEC':5,'T6_OVERFLOW':6,
              'T6_COMPLETED':0,'T6_INPUT_ATOMIC':1,'T6_OUTPUT_ATOMIC':1,'T6_RECOVERED':1}
    if any(fields.get(k)!=v for k,v in required.items()) or outputs!={'RECOVER_OUTPUT':'0000000000000000'}:
        raise ValueError('FP32 nonfinite/overflow/atomicity/recovery evidence failed/incomplete')
    return {'passed':True,'fields':fields,'outputs':outputs,'observed_stack_bytes':65536-fields['RTL_MIN_SP'],
            'full_stack_worst_case':None,'board_verified':False}
