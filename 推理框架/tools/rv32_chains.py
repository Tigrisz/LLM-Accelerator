"""Original four-node chain identity, references and RV32 recovery acceptance."""
import hashlib,json
from pathlib import Path
import numpy as np
from inference_ref.package_validation import chain_definition,_evaluate
from inference_ref.model_package import write_package,read_package
from inference_ref.static_export import export_static
from inference_ref.static_validation import run_standalone
from inference_ref.compare import compare_arrays
from inference_ref import reference,oracle
from rv32_samples import parse_stream,check_termination

IDENTITIES={'int32':'b69b0818db0d1fe412b3f0e83d8850aabf451baba35946ebcd75d1bc5c914e5f',
            'float32':'106ef22c2322e2e2502102897e6e66620345f2f440296857a09e04f1d2e21634'}


def definition_record(definition):
    out={k:v for k,v in definition.items() if k!='constants'}
    out['constants']={k:{'dtype':v.dtype.name,'shape':list(v.shape),'sha256':hashlib.sha256(v.astype(v.dtype.newbyteorder('<'),copy=False).tobytes()).hexdigest()} for k,v in definition['constants'].items()}
    return out


def verify_definition(definition,dtype):
    actual=hashlib.sha256(json.dumps(definition_record(definition),sort_keys=True,separators=(',',':')).encode()).hexdigest()
    if actual!=IDENTITIES.get(dtype):raise ValueError('Original chain topology/shape/dtype/constants identity changed')
    return True


def verify_package(package,feeds,dtype):
    original=chain_definition(dtype);verify_definition(original,dtype)
    if len(package.tensors)!=9 or len(package.nodes)!=4 or package.inputs!=('x',) or package.outputs!=('y',):raise ValueError('Original chain graph interfaces changed')
    for t,raw in zip(package.tensors,original['tensors']):
        if (t.id,t.role,t.spec.dtype,list(t.spec.shape),list(t.spec.storage_shape))!=(raw['id'],raw['role'],raw['dtype'],raw['shape'],raw['storage_shape']):raise ValueError('Original chain tensor/storage mapping changed')
        if t.role=='constant' and package.constant_array(t.id).tobytes()!=original['constants'][t.id].tobytes():raise ValueError('Original chain weight bytes changed')
    for node,raw in zip(package.nodes,original['nodes']):
        if (node.id,node.op,dict(node.inputs),node.output)!=(raw['id'],raw['op'],raw['inputs'],raw['output']):raise ValueError('Original chain node mapping changed')
    expected=np.array([2,-3,4],dtype=dtype)
    if set(feeds)!={'x'} or feeds['x'].shape!=(3,) or feeds['x'].dtype.name!=dtype or feeds['x'].tobytes()!=expected.tobytes():raise ValueError('Original chain input bytes/shape changed')
    return True


def manual_result(dtype,label):
    if dtype not in IDENTITIES or label not in ('normal','zero'):raise ValueError('Known chain dtype/input required')
    return np.array([20,-25] if label=='normal' else [0,-5],dtype=dtype)


class ChainMismatch(ValueError):
    """Complete fault/recovery lifecycle with wrong recovered values."""


def validate_chain_fault(stdout,code,dtype):
    fields,outputs=parse_stream(stdout);check_termination(fields,code)
    wanted={'T7_FAILURE':5 if dtype=='float32' else 6,'T7_COMPLETED':2,'T7_OUTPUT_INVALID':1,'T7_RECOVERED_NODES':4,'T7_ZERO_NODES':4,'T7_CLOSED':1}
    expected={'RECOVER_OUTPUT':manual_result(dtype,'normal').tobytes().hex(),'ZERO_OUTPUT':manual_result(dtype,'zero').tobytes().hex()}
    if any(fields.get(k)!=v for k,v in wanted.items()) or set(outputs)!=set(expected):raise ValueError('Partial-chain failure/visibility/recovery evidence missing or wrong')
    if outputs!=expected:raise ChainMismatch('Recovered chain output bytes differ')
    return {'passed':True,'fields':fields,'outputs':outputs,'observed_stack_bytes':65536-fields['RTL_MIN_SP'],'full_stack_worst_case':None,'board_verified':False,'whole_graph_rollback_verified':False}


def run_chains(output,pc_static,pc_core,execute,link,cc,tool,flags,objects,profiles):
    from run_rv32_samples import build_case,physical,ROOT
    results=[];rows=[]
    for dtype in ('int32','float32'):
        name='chain_'+dtype;directory=output/name;directory.mkdir();definition=chain_definition(dtype);verify_definition(definition,dtype)
        write_package(directory/'package',**definition);package=read_package(directory/'package');feeds={'x':np.array([2,-3,4],dtype=dtype)};verify_package(package,feeds,dtype)
        spec=next(t.spec for t in package.tensors if t.id=='y');refs={};records={};expected={}
        policy={'mode':'abs_plus_rel' if dtype=='float32' else 'exact','atol':1e-6 if dtype=='float32' else 0,'rtol':1e-5 if dtype=='float32' else 0}
        for label,data in [('normal',feeds),('zero',{'x':np.zeros(3,dtype=dtype)})]:
            actual,execution=run_standalone(pc_static,directory/'package',data,directory/('pc_'+label))
            values={'scalar':_evaluate(package,data,reference.execute)['y'],'numpy':_evaluate(package,data,oracle.execute)['y'],
                    'pc_core':_evaluate(package,data,pc_core.execute)['y'],'pc_static':actual['y'],'stored':manual_result(dtype,label)}
            checks={k:compare_arrays(values['stored'],v,policy['atol'],policy['rtol']) for k,v in values.items()}
            if not all(c['passed'] for c in checks.values()):raise ValueError('Chain PC reference/manual mismatch')
            expected[label]=physical(values['stored'],spec).hex()
            if (directory/('pc_'+label)/'outputs.bin').read_bytes().hex()!=expected[label]:raise ValueError('Chain PC physical output mismatch')
            refs[label]=values;records[label]={'values_hex':{k:v.tobytes().hex() for k,v in values.items()},'comparisons':checks,'pc_execution':execution,'physical_output':expected[label]}
        exported=export_static(directory/'package',directory/'export',address_bits=32)
        runs={k:expected['zero'] if k=='RUN_1_OUTPUT' else expected['normal'] for k in ('RUN_0_OUTPUT','RUN_1_OUTPUT','RUN_2_OUTPUT','RECOVER_OUTPUT','REBIND_OUTPUT')}
        context=(refs,spec,policy) if dtype=='float32' else None
        result=build_case(name,directory,package,feeds,exported,False,runs,execute,link,cc,tool,flags,objects,profiles,float_context=context)
        fault=output/(name+'_fault');fault.mkdir();write_package(fault/'package',**definition);fp=read_package(fault/'package');verify_package(fp,feeds,dtype)
        fe=export_static(fault/'package',fault/'export',address_bits=32)
        delta=next(i for i,t in enumerate(fp.tensors) if t.id=='delta')
        fault_result=build_case(name+'_fault',fault,fp,feeds,fe,False,{'RECOVER_OUTPUT':expected['normal'],'ZERO_OUTPUT':expected['zero']},execute,link,cc,tool,flags,objects,profiles,
            harness=ROOT/'c/rv32/t7_chain_faults.c',gate=lambda stdout,code:validate_chain_fault(stdout,code,dtype),
            header_defines={'T7_DELTA_INDEX':delta,'T7_IS_FP32':int(dtype=='float32')})
        record={'case_id':name,'dtype':dtype,'selected':True,'target_status':'pending','definition_sha256':IDENTITIES[dtype],
                'definition':definition_record(definition),'input_sha256':hashlib.sha256(feeds['x'].tobytes()).hexdigest(),
                'package_manifest_sha256':package.manifest_sha256,'weights_sha256':package.weights_sha256,'node_count':4,'tensor_count':9}
        result.update(record=record,references=records,comparison_policy=policy,positive_status=result['status'],partial_failure=fault_result)
        states={result['status'],fault_result['status']}
        result['status']=next((s for s in ('failed','tool_error','unproven','blocked_tcm') if s in states),'passed')
        result['passed']=True if result['status']=='passed' else False if result['status']=='failed' else None
        results.append(result);rows.append(record);print(name,result['status'],flush=True)
    if len(results)!=2 or {r['record']['dtype'] for r in results}!=set(IDENTITIES):raise ValueError('Both original chains required')
    return results,rows
