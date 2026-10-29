"""Source-owned intake audit using only the specified fresh static build."""
import argparse
from dataclasses import replace
import ctypes as ct
import copy
import hashlib
import json
from pathlib import Path
import re
import sys
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from inference_ref import __version__,reference,oracle
from inference_ref.backend import BackendRegistry,ChainRequirements,NodeRequirement,TensorRequirement,requirements_for
from inference_ref.c_backend import CBackend,CTensor,CCall,CProfile
from inference_ref.c_execution import CStaticBackend
from inference_ref.compare import compare_arrays
from inference_ref.contracts import ContractError,TensorSpec,MAX_ELEMENTS,MAX_DATA_BYTES,require
from inference_ref.fixtures import read_fixture
from inference_ref.memory import plan_memory,validate_plan_addressing
from inference_ref.model_package import _validate,digest,read_package,write_package,MAX_NODES,MAX_TENSORS,MAX_MANIFEST
from inference_ref.package_validation import package_fixture,chain_definition,_evaluate
from inference_ref.platform import PCPlatform,checked_span
from inference_ref.resources import ResourceLedger
from inference_ref.runtime import load_model,create_session
from inference_ref.static_backend import CStaticRuntimeBackend
from inference_ref.suite import verify_suite
from inference_ref.tracing import read_export

SHA=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
from reproduce import validate_output


def rejected(fn,expected):
    try:fn()
    except ContractError as exc:
        require(exc.code==expected,'INVALID_STATE',f'Expected {expected}, got {exc.code}')
        return {'passed':True,'status':exc.code}
    raise AssertionError('Expected explicit rejection')


def execute_case(path,feeds,backends,platform,expected):
    model=load_model(path,platform=platform);rows=[];values=[]
    try:
        for backend in backends:
            query=BackendRegistry([backend]).query(requirements_for(model.package,model.plan),backend.backend_id)
            require(query.supported,'INVALID_STATE','Existing supported chain rejected')
            with create_session(model,backend) as session:
                actual=session.run(feeds)['y'];values.append(actual.tobytes())
                compares={k:compare_arrays(v,actual,*policy) for k,(v,policy) in expected.items()}
                observed=platform.ledger.snapshot()['categories']['c_metadata']['live_bytes']
                nt,nn=len(model.package.tensors),len(model.package.nodes)
                if backend.backend_id=='pc_c':predicted=nt*ct.sizeof(CTensor)+nn*ct.sizeof(CCall)+ct.sizeof(ct.c_uint32)
                else:predicted=64+96*nt+24*nn+1+backend.raw.lib.irs_context_size()+nt*ct.sizeof(CTensor)+nn*ct.sizeof(CCall)+backend.raw.lib.irs_tensor_state_bytes(nt)
                require(observed==predicted,'INVALID_STATE','Documented metadata formula differs from actual ledger')
                require(all(c['passed'] for c in compares.values()),'INVALID_STATE','Numeric comparison failed')
                rows.append({'backend':backend.backend_id,'support_report':query.to_dict(),'comparisons':compares,
                    'native_metadata_bytes':observed,'predicted_native_metadata_bytes':predicted})
        require(values[0]==values[1],'INVALID_STATE','Backend outputs differ')
        package,plan=model.package,model.plan
        info={'model_id':package.model_id,'node_count':len(package.nodes),'tensor_count':len(package.tensors),
            'plan':plan.to_dict(),'backends':rows,'backend_bitwise_equal':True,'passed':True}
        (path/'inspection.json').write_text(json.dumps(info,indent=2)+'\n',encoding='utf-8')
        return info
    finally:
        model.close()
        require(platform.ledger.snapshot()['live_entries']==0,'INVALID_STATE','Audit resources remain')


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--static-report',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();OUT=validate_output(ROOT,args.output);OUT.mkdir(parents=True,exist_ok=False)
    source_before={p.relative_to(ROOT).as_posix():SHA(p) for base in ('inference_ref','c','tests') for p in sorted((ROOT/base).rglob('*')) if p.is_file() and '__pycache__' not in p.parts}
    fixture_before={p.relative_to(ROOT).as_posix():SHA(p) for p in sorted((ROOT/'fixtures/synthetic-v1').rglob('*')) if p.is_file()}
    static_path=args.static_report.resolve()
    require(static_path.is_relative_to(ROOT/'build'),'INVALID_ARGUMENT','Static report must be built in this workspace')
    fresh=json.loads(static_path.read_text())
    require(fresh.get('passed') is True,'INVALID_STATE','Fresh static acceptance did not pass')
    require(all(SHA(ROOT/k)==v for k,v in fresh['c_source_sha256'].items()),'INVALID_STATE','C source differs from fresh build')
    require(all(SHA(ROOT/'inference_ref'/k)==v for k,v in fresh['source_sha256'].items()),'INVALID_STATE','Python source differs from fresh build')
    library=Path(fresh['build']['library']).resolve()
    require(library.is_relative_to(ROOT/'build'),'INVALID_ARGUMENT','Library must be built in this workspace')
    backends=[CStaticBackend(CBackend(library)),CStaticRuntimeBackend(library)]
    platform=PCPlatform(ledger=ResourceLedger());baseline=verify_suite(ROOT/'fixtures/synthetic-v1');rows=[]
    for case in baseline['cases']:
        require(case['passed'],'INVALID_STATE','Existing fixture failed baseline')
        fixture=read_fixture(ROOT/'fixtures/synthetic-v1'/case['case_id']);path=OUT/'packages'/case['case_id']
        feeds=package_fixture(path,fixture);op=fixture.metadata['operation']['name'];policy=fixture.metadata['comparison'];tol=(policy['atol'],policy['rtol'])
        expected={k:(value,tol) for k,value in [('stored',fixture.expected),('scalar',reference.execute(op,fixture.inputs)),('numpy',oracle.execute(op,fixture.inputs))]}
        rows.append({'case_id':case['case_id'],**execute_case(path,feeds,backends,platform,expected)})
    chains=[]
    for dtype in ('int32','float32'):
        path=OUT/'chains'/dtype;write_package(path,**chain_definition(dtype));package=read_package(path)
        feeds={'x':__import__('numpy').array([2,-3,4],dtype)}
        expected={k:(value,(1e-6,1e-5)) for k,value in [('manual',__import__('numpy').array([20,-25],dtype)),
            ('scalar',_evaluate(package,feeds,reference.execute)['y']),('numpy',_evaluate(package,feeds,oracle.execute)['y'])]}
        chains.append({'dtype':dtype,**execute_case(path,feeds,backends,platform,expected)})
    # Review regression: valid FP32 -0.0 physical padding has nonzero bytes.
    fixture=read_fixture(ROOT/'fixtures/synthetic-v1/float_padded')
    signed_path=OUT/'signed_zero_padding';feeds=package_fixture(signed_path,fixture)
    signed_manifest=json.loads((signed_path/'manifest.json').read_text());signed_data=bytearray((signed_path/'weights.bin').read_bytes())
    padded_constants=[]
    for record in signed_manifest['tensors']:
        if record['role']!='constant' or record['shape']==record['storage_shape']:continue
        blob=record['blob'];array=np.frombuffer(signed_data,dtype='<f4',count=blob['length']//4,offset=blob['offset']).reshape(record['storage_shape'])
        mask=np.ones(record['storage_shape'],dtype=bool);mask[tuple(slice(0,d) for d in record['shape'])]=False
        array[mask]=np.float32(-0.0)
        require(bool((array[mask]==0).all()) and bool(np.signbit(array[mask]).all()),'INVALID_STATE','Expected signed numerical zero')
        padded_constants.append((record,mask))
    require(bool(padded_constants),'INVALID_STATE','Signed zero probe needs padded constant')
    def refresh_hashes(manifest,data):
        for record in manifest['tensors']:
            if record['role']=='constant':
                blob=record['blob'];blob['sha256']=digest(data[blob['offset']:blob['offset']+blob['length']])
        manifest['weights']['sha256']=digest(data)
    refresh_hashes(signed_manifest,signed_data)
    (signed_path/'weights.bin').write_bytes(signed_data)
    (signed_path/'manifest.json').write_text(json.dumps(signed_manifest,indent=2)+'\n',encoding='utf-8')
    op=fixture.metadata['operation']['name'];policy=fixture.metadata['comparison'];tol=(policy['atol'],policy['rtol'])
    expected={k:(value,tol) for k,value in [('stored',fixture.expected),('scalar',reference.execute(op,fixture.inputs)),('numpy',oracle.execute(op,fixture.inputs))]}
    padding_probe=execute_case(signed_path,feeds,backends,platform,expected)
    padding_probe.update(name='float32_negative_zero_padding',padding_encoding='00000080_little_endian',status='accepted_numerical_zero')
    nonzero_data=bytearray(signed_data);record,mask=padded_constants[0];blob=record['blob']
    array=np.frombuffer(nonzero_data,dtype='<f4',count=blob['length']//4,offset=blob['offset']).reshape(record['storage_shape']);array[mask]=1.0
    nonzero_manifest=copy.deepcopy(signed_manifest);refresh_hashes(nonzero_manifest,nonzero_data)
    x=TensorRequirement('x','float32',(3,),(3,),'row_major','input')
    y=replace(x,tensor_id='y',role='output');base=ChainRequirements((NodeRequirement(0,'probe','relu',(('input',x),),y),),64,64,1024)
    probes=[]
    def probe(name,req):
        reports=[BackendRegistry([b]).query(req,b.backend_id).to_dict() for b in backends]
        require(all(r['supported'] is False for r in reports),'INVALID_STATE','Unsupported semantic requirement falsely supported')
        probes.append({'name':name,'source':'synthetic_capability_probe','candidate_model':None,'passed':True,'reports':reports})
    def altered(t):return replace(base,nodes=(replace(base.nodes[0],inputs=(('input',t),)),))
    for op in ('matmul','conv2d','softmax','layer_norm','embedding','transpose','reshape','cast','requantize'):
        probe('operator_'+op,replace(base,nodes=(replace(base.nodes[0],op=op),)))
    for dtype in ('float16','bfloat16','int8','int4','float8'):
        probe('dtype_'+dtype,replace(base,nodes=(replace(base.nodes[0],inputs=(('input',replace(x,dtype=dtype)),),output=replace(y,dtype=dtype)),)))
    for name,tensor in [('layout_strided',replace(x,layout='strided')),('rank_zero',replace(x,shape=(),storage_shape=())),
        ('rank_five',replace(x,shape=(1,1,1,1,3),storage_shape=(1,1,1,1,3))),('zero_dimension',replace(x,shape=(0,),storage_shape=(0,))),
        ('dynamic_dimension',replace(x,shape=('T',),storage_shape=('T',))),('over_elements',replace(x,shape=(MAX_ELEMENTS+1,),storage_shape=(MAX_ELEMENTS+1,))),
        ('device_domain',replace(x,memory_domain='device'))]:probe(name,altered(tensor))
    for name,attributes in [('transpose_attribute',(('transpose',True),)),('quantization_attribute',(('quantization','unimplemented'),))]:
        probe(name,replace(base,nodes=(replace(base.nodes[0],attributes=attributes),)))
    probe('readonly_output',replace(base,nodes=(replace(base.nodes[0],output=replace(y,read_only=True)),)))
    probe('insufficient_workspace',replace(base,workspace_bytes=0));probe('unaligned_requirement',replace(base,alignment=2))
    w=replace(x,tensor_id='w',shape=(2,3),storage_shape=(2,3),role='constant');liny=replace(y,shape=(2,),storage_shape=(2,))
    batch=replace(x,shape=(2,3),storage_shape=(2,3))
    probe('batched_linear',replace(base,nodes=(NodeRequirement(0,'probe','linear',(('weight',w),('input',batch)),liny),)))
    scalar=replace(x,tensor_id='scalar',shape=(1,),storage_shape=(1,))
    probe('broadcast_add',replace(base,nodes=(NodeRequirement(0,'probe','add',(('a',x),('b',scalar)),y),)))
    package=read_package(OUT/'chains/int32');manifest=json.loads((OUT/'chains/int32/manifest.json').read_text());negatives=[]
    for name,modify,expected in [('quantization_field',lambda m:m['tensors'][0].update(quantization={'scale':1.0}),'INVALID_MODEL'),
        ('state_field',lambda m:m.update(persistent_state=[]),'INVALID_MODEL'),
        ('too_many_nodes',lambda m:m.update(nodes=m['nodes']*(MAX_NODES//4+1)),'RESOURCE_LIMIT'),
        ('too_many_tensors',lambda m:m.update(tensors=[m['tensors'][0]]*(MAX_TENSORS+1)),'RESOURCE_LIMIT'),
        ('oversized_weights',lambda m:m['weights'].update(byte_length=MAX_DATA_BYTES+1),'RESOURCE_LIMIT')]:
        modified=copy.deepcopy(manifest);modify(modified)
        negatives.append({'name':name,**rejected(lambda m=modified:_validate(m,package.weights,''),expected)})
    plan=plan_memory(package)
    negatives.append({'name':'arena_budget_below_required',**rejected(lambda:plan_memory(package,memory_budget=plan.total_bytes-1),'RESOURCE_LIMIT')})
    require(plan_memory(package,memory_budget=plan.total_bytes)==plan,'INVALID_STATE','Exact arena budget rejected')
    negatives.append({'name':'address32_length_4GiB',**rejected(lambda:checked_span(0,1<<32,bits=32),'RESOURCE_LIMIT')})
    require(checked_span(0xffffffff,1,bits=32)==1<<32,'INVALID_STATE','32-bit last byte rejected')
    negatives.append({'name':'nonzero_physical_padding',**rejected(lambda:_validate(nonzero_manifest,bytes(nonzero_data),''),'INVALID_MODEL')})
    templates={}
    for p in sorted((ROOT/'templates').glob('*_v1.json')):
        doc=json.loads(p.read_text());require(doc['version']==1 and doc['status']=='unassessed','INVALID_STATE','Template default assessment')
        require(doc.get('assessment')=='pending' or doc.get('assessment',{}).get('overall_decision')=='pending','INVALID_STATE','Blank template wrongly approved')
        templates[p.name]={'sha256':SHA(p),'status':doc['status']}
    candidate=json.loads((ROOT/'templates/candidate_requirements_v1.json').read_text())
    require(candidate['candidate']['id'] is None and candidate['graph']['operator_inventory'] is None and candidate['numeric_contract']['quantization_inventory'] is None and candidate['target']['usable_memory_by_domain'] is None,'INVALID_STATE','Candidate assumptions slipped into blank template')
    require(len(templates)==4,'INVALID_STATE','Missing intake templates')
    docs=['docs/model_intake.md','docs/capability_matrix.md','docs/model_gap_analysis.md','docs/model_memory_requirements.md']
    require(all((ROOT/p).is_file() for p in docs),'INVALID_STATE','Missing document')
    require(all(SHA(ROOT/p)==h for p,h in source_before.items()),'INVALID_STATE','Runtime/tests changed in documentation audit')
    require(all(SHA(ROOT/p)==h for p,h in fixture_before.items()),'INVALID_STATE','Frozen fixtures changed')
    report={'format':'inference-model-intake-audit','version':1,'scope':'phase1a_s6','runtime_version':__version__,
        'candidate_model':None,'candidate_decision':'pending','passed':True,'case_count':len(rows),'passed_count':len(rows),
        'reference_comparisons':len(rows)*2*3,'backend_queries':len(rows)*2,'cases':rows,'chains':chains,
        'padding_probes':[padding_probe],'supplemental_reference_comparisons':len(chains)*2*3+2*3,
        'capability_negative_probes':probes,'package_budget_address_negatives':negatives,'templates':templates,
        'source_sha256':source_before,'frozen_inputs_sha256':fixture_before,'documents_sha256':{p:SHA(ROOT/p) for p in docs},
        'audit_script_sha256':SHA(Path(__file__)),'library_sha256':SHA(library),'library_build':backends[1].raw.build,
        'current_limits':{'max_elements':MAX_ELEMENTS,'max_tensor_bytes':MAX_ELEMENTS*4,'max_source_weights_bytes':MAX_DATA_BYTES,
            'max_manifest_bytes':MAX_MANIFEST,'max_nodes':MAX_NODES,'max_tensors':MAX_TENSORS},
        'final_resource_ledger':platform.ledger.snapshot(),'final_platform_stats':platform.stats(),
        'fresh_static_report':str(static_path),'historical_evidence_required':False,
        'runtime_and_tests_unchanged':True,'rv32_execution':False,'model_accuracy_verified':False,'target_memory_verified':False}
    (OUT/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'passed':True,'cases':len(rows),'comparisons':report['reference_comparisons'],'negative_query_probes':len(probes),
        'other_negative_probes':len(negatives),'templates':len(templates),'resource_entries':platform.ledger.snapshot()['live_entries']}))


if __name__=='__main__':main()
