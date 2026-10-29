"""T8 coverage/status contract and independent replay of current-run artifacts."""
import copy,json,re,hashlib
from pathlib import Path
import numpy as np
from reproduce import ROOT,sha
from rv32_samples import inventory,verify_fixture_mapping,parse_stream,check_termination,validate_sample_run,validate_exact_run,validate_recovery_run,NumericalMismatch,validate_overflow_run,link_state,FROZEN_SUITE_SHA256
from rv32_fp32 import validate_float_run,validate_float_faults,check_softfloat_symbols,FP32Mismatch,compare_output
from rv32_chains import verify_package,manual_result,validate_chain_fault,ChainMismatch,IDENTITIES,definition_record
from rv32_evidence import check_elf,check_attributes
from rv32_profiles import parameters,check_build_parameters
from inference_ref.model_package import read_package
from inference_ref.fixtures import read_fixture
from inference_ref import reference,oracle
from inference_ref.package_validation import _evaluate
from inference_ref.package_validation import chain_definition
from inference_ref.static_validation import validate_c_trace

STATES=('passed','blocked_tcm','failed','unproven','tool_error')
PROFILES={'single_issue','dual_issue'}


def combine_status(states):
    if not states or any(s not in STATES for s in states):raise ValueError('Complete known stage states required')
    return next((s for s in ('failed','tool_error','unproven','blocked_tcm') if s in states),'passed')


def truth(status):return True if status=='passed' else False if status=='failed' else None


def aggregate_cases(cases,expected_ids):
    if not expected_ids or not isinstance(cases,list) or len(cases)!=len(expected_ids) or {r.get('case_id') for r in cases}!=set(expected_ids):raise ValueError('Missing/duplicate/extra/empty acceptance cases')
    for row in cases:
        state=row.get('status')
        if state not in STATES or row.get('passed') is not truth(state):raise ValueError('Inconsistent three-state case result')
        if state=='passed':
            profiles=row.get('profiles',{})
            if set(profiles)!=PROFILES or not re.fullmatch('[0-9a-f]{64}',row.get('elf_sha256','')):raise ValueError('Both profiles and ELF identity required')
            for p in profiles.values():
                if p.get('status')!='passed' or p.get('simulator_exit')!=0 or p.get('elf_sha256')!=row['elf_sha256'] or p.get('result',{}).get('passed') is not True or not p.get('result',{}).get('outputs'):
                    raise ValueError('Valid numerical/profile/ELF/output evidence required')
            if profiles['single_issue']['result']['outputs']!=profiles['dual_issue']['result']['outputs']:raise ValueError('Single/dual actual bytes differ')
    counts={s:sum(r['status']==s for r in cases) for s in STATES};state=combine_status([r['status'] for r in cases])
    return {'status':state,'passed':truth(state),'counts':counts,'all_selected_rv32_validated':counts['passed']==len(expected_ids),'case_count':len(cases)}


def validate_pc(report,iterations):
    if report.get('passed') is not True:raise ValueError('PC acceptance did not pass')
    for key,minimum in [('framework_tests',174),('tool_tests',61)]:
        r=report.get(key,{})
        if r.get('passed') is not True or r.get('tests_run',0)<minimum or any(r.get(k)!=0 for k in ('skipped','failures','errors')):raise ValueError('Incomplete/skipped/failed PC tests')
    if report['framework_tests']['tests_run']!=174:raise ValueError('Original 174 test identity count changed')
    expected=dict(cases=54,chains=4,resource_probes=24,native_runs=6,sanitizer_runs=3,iterations=iterations)
    if report.get('resource_acceptance')!=expected:raise ValueError('Complete PC pressure/native acceptance required')
    return {'status':'passed','passed':True,'framework_tests':174,'tool_tests':report['tool_tests']['tests_run'],'resource_acceptance':expected}


def observe(stdout,code,validator):
    try:return {'status':'passed','passed':True,'validation':validator(stdout,code)}
    except ValueError as error:
        try:fields,outputs=parse_stream(stdout)
        except ValueError:fields,outputs={},{}
        confirmed=any(fields.get(k,0)>0 for k in ('T5_STATUS','RTL_TRAPS','RTL_STACK_VIOLATIONS')) or isinstance(error,(FP32Mismatch,NumericalMismatch,ChainMismatch))
        state='failed' if confirmed else 'unproven'
        return {'status':state,'passed':truth(state),'reason':str(error),'fields':fields,'outputs':outputs}


def execution_counts(matrix):
    counts=dict(positive_profile_executions=0,valid_positive_output_records=0,partial_failure_profile_executions=0,valid_recovery_output_records=0,validated_sync_unknown_runs=0)
    for case in matrix:
        for name,phase in case['phases'].items():
            fault=name.endswith('_fault');profiles=phase.get('profiles',{})
            counts['partial_failure_profile_executions' if fault else 'positive_profile_executions']+=len(profiles)
            for p in profiles.values():
                if p['status']=='passed':
                    counts['valid_recovery_output_records' if fault else 'valid_positive_output_records']+=len(p['validation']['outputs'])
                    if not fault:counts['validated_sync_unknown_runs']+=1
    return counts


def reference_outputs(normal,zero,spec):
    def physical(values):
        out=np.zeros(spec.storage_shape,dtype='<f4' if spec.dtype=='float32' else '<i4')
        out[tuple(slice(0,d) for d in spec.shape)]=values
        return out.tobytes().hex()
    return {k:physical(zero if k=='RUN_1_OUTPUT' else normal) for k in ('RUN_0_OUTPUT','RUN_1_OUTPUT','RUN_2_OUTPUT','RECOVER_OUTPUT','REBIND_OUTPUT')}


def check_expected_outputs(recorded,expected):
    if recorded!=expected:raise ValueError('Receipt expected outputs differ from independent reference')


def boundary_outputs():
    from inference_ref.contracts import TensorSpec
    normal=np.array([0x3f800000,0x3f800002,2,0,0x7f7fffff,0],dtype='<u4').view('<f4')
    return reference_outputs(normal,np.zeros(6,np.float32),TensorSpec('float32',(6,),(6,)))


def check_chain_record(name,record,policy,package,feeds):
    dtype={'chain_int32':'int32','chain_float32':'float32'}.get(name)
    if dtype is None or record.get('dtype')!=dtype:raise ValueError('Chain label/dtype substitution')
    original=chain_definition(dtype)
    if record.get('definition_sha256')!=IDENTITIES[dtype] or record.get('definition')!=definition_record(original) or record.get('input_sha256')!=hashlib.sha256(np.array([2,-3,4],dtype=dtype).tobytes()).hexdigest():raise ValueError('Original chain identity metadata differs')
    expected_policy={'mode':'abs_plus_rel' if dtype=='float32' else 'exact','atol':1e-6 if dtype=='float32' else 0,'rtol':1e-5 if dtype=='float32' else 0}
    if policy!=expected_policy:raise ValueError('Original chain comparison policy differs')
    verify_package(package,feeds,dtype)
    if record.get('package_manifest_sha256')!=package.manifest_sha256 or record.get('weights_sha256')!=package.weights_sha256 or record.get('node_count')!=4 or record.get('tensor_count')!=9:raise ValueError('Original chain package identity differs')


def verify_pc_artifacts(base,label,execution,nodes,output_bytes):
    directory=Path(base)/('pc_'+label)
    stdout=json.loads((directory/'stdout.log').read_text());stderr=(directory/'stderr.log').read_text();trace=json.loads((directory/'trace.json').read_text())
    validation=validate_c_trace(trace)
    if stdout!={'status':0,'trace_complete':True,'live_allocations':0} or stderr or not validation['passed'] or validation!=execution.get('trace_validation'):raise ValueError('Actual PC logs/trace mismatch')
    if trace['node_count']!=nodes or trace['output_bytes']!=output_bytes or execution.get('exit_code')!=0 or execution.get('node_count')!=nodes:raise ValueError('PC execution size/progress differs')
    command=execution['command'];paths=[directory/'export/execution.bin',directory/'export/weights.bin',directory/'inputs.bin',directory/'outputs.bin',directory/'trace.json']
    if [str(p) for p in paths]!=command[1:] or not Path(command[0]).is_file() or any(not p.is_file() for p in paths):raise ValueError('Actual PC executable/artifacts missing')


def verify_image(item,name,directory,dtype):
    directory=Path(directory);elf=directory/name/'firmware.elf'
    if sha(elf)!=item.get('elf_sha256'):raise ValueError('Actual ELF hash mismatch')
    check_elf(elf.read_bytes());check_attributes((directory/(name+'_readelf.stdout')).read_text())
    if set(item.get('profiles',{}))!=PROFILES or any(p.get('elf_sha256')!=item['elf_sha256'] for p in item['profiles'].values()):raise ValueError('Probe requires both profiles and same actual ELF')
    if dtype=='float32':check_softfloat_symbols((directory/(name+'_symbols.stdout')).read_text(),(directory/(name+'_objdump.stdout')).read_text())


def reconcile_profiles(profiles):
    if all(p['status']=='passed' for p in profiles.values()) and profiles['single_issue']['validation']['outputs']!=profiles['dual_issue']['validation']['outputs']:
        profiles['dual_issue']={'status':'failed','passed':False,'reason':'Same ELF single/dual outputs differ bitwise','validation':profiles['dual_issue']['validation']}
    return profiles


def replay_target(report,directory):
    directory=Path(directory);fixture_rows=inventory(ROOT/'fixtures/synthetic-v1');expected={r['case_id'] for r in fixture_rows}|{'chain_int32','chain_float32'}
    if report.get('workload')!='all' or report.get('selected_count')!=56 or report.get('frozen_suite_sha256')!=FROZEN_SUITE_SHA256 or report.get('fixtures_unchanged') is not True:raise ValueError('Current complete all-workload receipt required')
    aggregate_cases(report.get('cases'),expected)
    if set(report.get('profiles',{}))!=PROFILES:raise ValueError('Both explicit RTL configurations required')
    for name,p in report['profiles'].items():
        if p['parameters']!=parameters(name):raise ValueError('RTL parameters changed')
        check_build_parameters(p['build_command'],p['parameters'])
    matrix=[];controls=None;case_artifacts=[];frozen={r['case_id']:r for r in fixture_rows}
    for case in report['cases']:
        name=case['case_id'];base=directory/name;chain=name.startswith('chain_');dtype=case['record']['dtype'];package=read_package(base/'package');spec=next(t.spec for t in package.tensors if t.role=='output')
        if chain:
            feeds={'x':np.array([2,-3,4],dtype=dtype)};check_chain_record(name,case['record'],case['comparison_policy'],package,feeds)
            refs={label:{k:np.frombuffer(bytes.fromhex(v),dtype='<f4' if dtype=='float32' else '<i4').reshape(spec.shape).copy() for k,v in row['values_hex'].items()} for label,row in case['references'].items()}
            policy=case['comparison_policy'];normal=manual_result(dtype,'normal');zero=manual_result(dtype,'zero')
        else:
            for key,value in frozen[name].items():
                if key not in ('selected','target_status') and case['record'].get(key)!=value:raise ValueError('Case record differs from frozen inventory: '+key)
            fixture=read_fixture(ROOT/'fixtures/synthetic-v1'/name);feeds={t.id:fixture.inputs[t.id] for t in package.tensors if t.role=='input'};verify_fixture_mapping(fixture,package,feeds)
            policy=fixture.metadata['comparison'];op=fixture.metadata['operation']['name'];zero_data={**fixture.inputs,**{k:np.zeros_like(v) for k,v in feeds.items()}}
            normal=reference.execute(op,fixture.inputs);zero=reference.execute(op,zero_data)
            if dtype=='float32':refs={label:{k:np.frombuffer(bytes.fromhex(v),dtype='<f4').reshape(spec.shape).copy() for k,v in values.items()} for label,values in case['float_references'].items()}
        independent=reference_outputs(normal,zero,spec)
        if case.get('profiles'):check_expected_outputs(case.get('expected_outputs'),independent)
        for label,values in [('normal',normal),('zero',zero)]:
            pc=(base/('pc_'+label)/'outputs.bin').read_bytes()
            if pc.hex()!=case['references'][label]['physical_output']:raise ValueError('PC physical artifact/receipt differs')
            if dtype=='float32':
                if refs[label]['scalar'].tobytes()!=values.tobytes() or not compare_output(pc.hex(),values,spec,policy)['passed']:raise ValueError('Independent scalar/PC FP32 mismatch')
            else:
                storage=np.zeros(spec.storage_shape,dtype='<i4');storage[tuple(slice(0,d) for d in spec.shape)]=values
                if pc!=storage.tobytes():raise ValueError('Independent scalar/PC INT32 mismatch')
            execution=case['references'][label]['pc_execution']
            verify_pc_artifacts(base,label,execution,len(package.nodes),spec.byte_length)
        phases=[(name,case,False)]
        if chain:phases.append((name+'_fault',case['partial_failure'],True))
        phase_states=[];observations={}
        for phase,item,fault in phases:
            phase_dir=directory/phase
            if fault:verify_package(read_package(phase_dir/'package'),feeds,dtype)
            if item.get('status')=='blocked_tcm' and not item.get('profiles'):
                if link_state(item.get('link_exit_code'),(directory/(phase+'_link.stderr')).read_text())!='blocked_tcm':raise ValueError('Unproven capacity block')
                phase_states.append('blocked_tcm');observations[phase]={'status':'blocked_tcm','passed':None};continue
            verify_image(item,phase,directory,dtype)
            profiles={}
            for profile in sorted(PROFILES):
                p=item['profiles'][profile]
                if p['elf_sha256']!=item['elf_sha256']:raise ValueError('Different ELF per profile')
                stdout=(directory/(phase+'_'+profile+'.stdout')).read_text()
                validator=(lambda text,code:validate_chain_fault(text,code,dtype)) if fault else (lambda text,code:validate_float_run(text,code,refs,spec,policy,len(package.nodes))) if dtype=='float32' else (lambda text,code:validate_exact_run(text,code,independent,len(package.nodes)))
                observed=observe(stdout,p['simulator_exit'],validator);profiles[profile]=observed
                if controls is None and dtype=='float32' and not chain and observed['status']=='passed':controls=evidence_controls(stdout,refs,spec,policy,len(package.nodes))
            reconcile_profiles(profiles)
            for profile,observed in profiles.items():
                p=item['profiles'][profile]
                if observed['status']!='failed' and observed['status']!=p['status']:raise ValueError('Recorded and replayed target state differ')
                if observed['status']=='passed' and observed['validation']!=p['result']:raise ValueError('Recorded and actual gate result differ')
            states=[p['status'] for p in profiles.values()];phase_states.extend(states);observations[phase]={'status':combine_status(states),'profiles':profiles}
        state=combine_status(phase_states)
        if state!='failed' and state!=case['status']:raise ValueError('Case and actual phase status differ')
        matrix.append({'case_id':name,'kind':'chain' if chain else 'sample','dtype':dtype,'status':state,'passed':truth(state),'phases':observations})
        case_artifacts.append({'case_id':name,'initialized_bytes':case.get('initialized_bytes'),'layout':case.get('layout'),'elf_sha256':case.get('elf_sha256')})
    counts={s:sum(r['status']==s for r in matrix) for s in STATES};status=combine_status([r['status'] for r in matrix])
    summary=dict(status=status,passed=truth(status),counts=counts,all_selected_rv32_validated=counts['passed']==len(expected),case_count=len(matrix))
    if controls is None:controls={'status':'unproven','passed':None,'reason':'No passing FP32 evidence available for host gate controls'}
    capacity=report.get('capacity_probe',{})
    if capacity.get('passed') is not True or link_state(capacity.get('exit_code'),(directory/'capacity_link.stderr').read_text())!='blocked_tcm':raise ValueError('Actual oversized linker negative missing')
    extras=report['softfloat']
    if sha(Path(extras['libgcc']))!=extras['libgcc_sha256']:raise ValueError('Soft-float identity mismatch')
    boundary_expected=boundary_outputs()
    check_expected_outputs(extras['boundary']['expected_outputs'],boundary_expected)
    for label in ('normal','zero'):verify_pc_artifacts(directory/'fp32_boundary',label,extras['boundary_pc'][label]['execution'],1,24)
    auxiliaries={}
    for name,item,dtype,gate in [('fp32_faults',extras['faults'],'float32',lambda t,c:validate_recovery_run(t,c,validate_float_faults,{'RECOVER_OUTPUT':'0000000000000000'})),('numeric_overflow',report['numeric_overflow'],'int32',lambda t,c:validate_overflow_run(t,c,'00000000')),('fp32_boundary',extras['boundary'],'float32',lambda t,c:validate_exact_run(t,c,boundary_expected,1))]:
        verify_image(item,name,directory,dtype);observed={}
        for profile in PROFILES:
            p=item['profiles'][profile];observed[profile]=observe((directory/(name+'_'+profile+'.stdout')).read_text(),p['simulator_exit'],gate)
            if observed[profile]['status']=='passed' and observed[profile]['validation']['outputs']!=p['result']['outputs']:raise ValueError('Auxiliary actual/recorded outputs differ')
        reconcile_profiles(observed);s=combine_status([p['status'] for p in observed.values()]);auxiliaries[name]={'status':s,'passed':truth(s),'profiles':observed}
    status=combine_status([summary['status'],*[r['status'] for r in auxiliaries.values()]])
    return {**summary,'status':status,'passed':truth(status),'auxiliary_probes':auxiliaries,'validation_completed':True,'matrix':matrix,'case_artifacts':case_artifacts,**execution_counts(matrix),
        'capacity_negative':{'status':'passed','passed':True},'evidence_controls':controls,
        'scope':'current-source selected RTL simulation only','board_verified':False,'full_stack_worst_case':None}


def evidence_controls(stdout,refs,spec,policy,nodes):
    validator=lambda text,code:validate_float_run(text,code,refs,spec,policy,nodes)
    changed=copy.deepcopy(refs);changed['normal']['scalar'].flat[0]+=max(1.0,abs(float(changed['normal']['scalar'].flat[0]))*0.1)
    wrong=observe(stdout,0,lambda text,code:validate_float_run(text,code,changed,spec,policy,nodes))
    missing=observe('\n'.join(line for line in stdout.splitlines() if not line.startswith('RTL_TRAPS=')),0,validator)
    host=observe(stdout,2,validator)
    duplicate=observe(stdout+'\n'+next(line for line in stdout.splitlines() if line.startswith('RUN_0_OUTPUT='))+'\n',0,validator)
    rows={'wrong_expected':wrong,'missing_summary':missing,'host_exit_error':host,'duplicate_output':duplicate}
    expected={'wrong_expected':'failed','missing_summary':'unproven','host_exit_error':'unproven','duplicate_output':'unproven'}
    passed=all(row['status']==expected[name] for name,row in rows.items())
    return {'status':'passed' if passed else 'failed','passed':passed,'scope':'host gate mutations of one actual successful UART log; not additional target executions','controls':rows}
