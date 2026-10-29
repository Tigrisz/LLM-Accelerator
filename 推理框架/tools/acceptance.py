"""T1 clean-workspace acceptance; all dependencies built inside this workspace."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'tools'))
from reproduce import clean_environment,preflight,sha,write_json,run_command


def check(condition,message):
    if not condition:raise ValueError(message)


def validate_execution(execution,nodes,root=None):
    check(isinstance(execution,dict) and execution.get('exit_code')==0 and execution.get('node_count')==nodes and execution.get('live_allocations')==0 and execution.get('trace_validation',{}).get('passed') is True,'Missing/failed C execution or node/trace evidence')
    command=execution.get('command',[]);check(len(command)==6,'C execution command missing')
    if root is not None:
        root=Path(root).resolve();trace=Path(command[-1]).resolve()
        check(trace.is_relative_to(root) and Path(command[0]).resolve().is_relative_to(root),'Execution evidence escaped fresh static build')
        check((trace.parent/'stderr.log').read_bytes()==b'','C/sanitizer stderr diagnostic found')
        stdout=json.loads((trace.parent/'stdout.log').read_text())
        check(stdout.get('status')==0 and stdout.get('trace_complete') is True and stdout.get('live_allocations')==0,'C stdout did not confirm success')
        from inference_ref.static_validation import validate_c_trace
        document=json.loads(trace.read_text())
        check(validate_c_trace(document)['passed'] and document['node_count']==nodes,'C trace incomplete/mismatched')
        check(all(Path(p).resolve().is_relative_to(root) and Path(p).is_file() for p in command[1:]),'C input/output artifacts missing')
        check(Path(command[4]).stat().st_size==document['output_bytes'],'C output bytes mismatch')


def zero_ledger(row):
    check(all(row.get(k)==0 for k in ('live_entries','live_bytes','resident_bytes')),'Ledger resources remain or are missing')


def zero_device(row):
    check(all(row.get(k)==0 for k in ('live_tasks','live_sessions','staging_reserved_bytes')),'Device resources remain or are missing')


def validate_resources(resource,static,requested_iterations=200,root=None):
    check(type(requested_iterations) is int and requested_iterations>0 and resource.get('iterations')==requested_iterations,'Requested pressure iterations not executed')
    if resource.get('passed') is not True or resource.get('case_count')!=54 or resource.get('passed_count')!=54:raise ValueError('54-case resource acceptance failed')
    probes=resource.get('stress_probes',[])
    if len(probes)!=24 or len({p.get('name') for p in probes})!=24 or any(p.get('passed') is not True for p in probes):raise ValueError('Missing/failed resource pressure probes')
    expected=set();by_name={p['name']:p for p in probes}
    for backend in ('pc_c','pc_c_static'):
        for dtype in ('int32','float32'):
            name=f'repeat_{backend}_{dtype}';expected.add(name);p=by_name.get(name,{})
            check(p.get('backend')==backend and p.get('dtype')==dtype and p.get('iterations')==requested_iterations and p.get('session_count')==3 and p.get('successful_tasks')==requested_iterations*3 and p.get('stable_arena_addresses') is True and p.get('steady_state_plateau') is True,'Repeat pressure evidence missing')
            zero_ledger(p.get('final_ledger',{}));zero_device(p.get('final_device_stats',{}))
        name='allocation_sweep_'+backend;expected.add(name);points=by_name.get(name,{}).get('allocation_points',[])
        check(len(points)==20 and {p.get('fail_after') for p in points}==set(range(20)) and {p.get('status') for p in points}=={'OK','RESOURCE_LIMIT'} and all(p.get('released') is True for p in points),'Allocation sweep missing/incomplete')
        name='recover_close_'+backend;expected.add(name);p=by_name.get(name,{})
        check(p.get('recovery_refusals')==50 and p.get('close_attempts')==2 and p.get('unknown_graph_retained') is True and p.get('dropped_history_events',0)>0,'Recovery/close pressure evidence missing')
        zero_ledger(p.get('final_ledger',{}))
        for category in ('arena','c_metadata','c_profiles','trace','task_staging','task_records','session_records','task_events'):
            name=f'budget_{backend}_{category}';expected.add(name);p=by_name.get(name,{})
            check(p.get('category')==category,'Category budget probe missing');zero_ledger(p.get('final_ledger',{}))
    check(set(by_name)==expected,'Unexpected/missing pressure probe identities')
    if static.get('passed') is not True or static.get('case_count')!=54 or static.get('passed_count')!=54:raise ValueError('Static numerical acceptance failed')
    if len(static.get('cases',[]))!=54 or any(c.get('passed') is not True or c.get('adapter_bitwise_equal') is not True for c in static['cases']):raise ValueError('Case comparison/adapter failure')
    if len({c['case_id'] for c in static['cases']})!=54 or any(set(c.get('comparisons',{}))!={'stored','scalar','numpy'} or any(v.get('passed') is not True for v in c['comparisons'].values()) for c in static['cases']):raise ValueError('Individual reference comparison failed/missing')
    for c in static['cases']:validate_execution(c.get('execution'),1,root)
    chains=static.get('chains',[])
    if len(chains)!=4 or {(c.get('dtype'),c.get('input')) for c in chains}!={(d,i) for d in ('int32','float32') for i in ('normal','zero')} or any(c.get('passed') is not True for c in chains):raise ValueError('Four-node chains incomplete')
    for c in chains:
        check(set(c.get('comparisons',{}))=={'scalar','numpy','manual'} and all(v.get('passed') is True for v in c['comparisons'].values()),'Chain numeric evidence missing')
        validate_execution(c.get('execution'),4,root);validate_execution(c.get('sanitized_execution'),4,root)
    native=static.get('native_tests',[])
    if len(native)!=6 or any(n.get('passed') is not True or n.get('exit_code')!=0 for n in native) or {(Path(n['path']).name,n.get('sanitize')) for n in native}!={(name,s) for name in ('test_static','test_pc','test_resources') for s in (False,True)}:raise ValueError('Native/sanitizer acceptance incomplete')
    if root is not None:
        for n in native:
            path=Path(n['path']).resolve();check(path.is_relative_to(Path(root).resolve()),'Native artifact escaped fresh build')
            log=path.with_suffix('.run.log').read_text()
            check(not any(marker in log for marker in ('runtime error:','AddressSanitizer','LeakSanitizer','UndefinedBehaviorSanitizer')),'Native sanitizer diagnostic found')
            if path.name=='test_resources':
                info=json.loads(log.splitlines()[-1])
                check(info.get('iterations')==1000 and info.get('live_bytes')==0 and info.get('allocation_failures')==6 and info.get('recovery_released') is True,'Native resource pressure not executed')
        check(all(static.get('platform_stats',{}).get(k)==0 for k in ('live_allocations','backing_bytes','open_sources','retained_resources')),'Final platform resources missing/nonzero')
        zero_device(static.get('final_device_stats',{}))
        check(static.get('adapter_trace_validation',{}).get('passed') is True,'Adapter trace not verified')
    return {'cases':54,'chains':4,'resource_probes':24,'native_runs':6,'sanitizer_runs':3,'iterations':resource['iterations']}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);parser.add_argument('--iterations',type=int,default=200)
    args=parser.parse_args();output=args.output.resolve();checks={};commands=[];created=False
    try:
        environment=preflight()
        if not output.is_relative_to(ROOT/'build') or output.exists():raise ValueError('Fresh output under workspace/build required')
        if (ROOT/'build').exists() and any((ROOT/'build').iterdir()):raise ValueError('Acceptance requires an initially empty build directory')
        output.mkdir(parents=True,exist_ok=False)
        created=True
        def run(name,arguments,timeout):
            command=[sys.executable,'-B',*map(str,arguments)];commands.append(command);print('T1 stage: '+name,flush=True)
            with (output/(name+'.log')).open('x',encoding='utf-8') as stream:
                result=run_command(command,cwd=ROOT,env=clean_environment(),stdout=stream,stderr=subprocess.STDOUT,timeout=timeout)
            if result.returncode:raise RuntimeError(f'{name} failed ({result.returncode}); see {name}.log')
        run('framework_tests',[ROOT/'tools/run_tests.py','--suite','framework','--output',output/'framework_tests'],900)
        checks['framework_tests']=json.loads((output/'framework_tests/result.json').read_text())
        if not checks['framework_tests']['passed']:raise ValueError('Framework tests failed/skipped')
        run('tool_tests',[ROOT/'tools/run_tests.py','--suite','tools','--output',output/'tool_tests'],120)
        checks['tool_tests']=json.loads((output/'tool_tests/result.json').read_text())
        if not checks['tool_tests']['passed']:raise ValueError('Tool tests failed/skipped')
        run('resources',['-m','inference_ref','verify-resources','--fixtures',ROOT/'fixtures/synthetic-v1','--output',output/'resources','--iterations',args.iterations],600)
        resource=json.loads((output/'resources/report.json').read_text());static_path=output/'resources/static_runtime/report.json';static=json.loads(static_path.read_text())
        checks['resource_acceptance']=validate_resources(resource,static,args.iterations,static_path.parent)
        run('intake_audit',[ROOT/'tools/audit_intake.py','--static-report',static_path,'--output',output/'intake_audit'],120)
        audit=json.loads((output/'intake_audit/report.json').read_text())
        if audit.get('passed') is not True or audit.get('case_count')!=54 or audit.get('candidate_decision')!='pending':raise ValueError('Intake audit failed')
        checks['intake_audit']={'passed':True,'cases':54,'sample_reference_comparisons':audit['reference_comparisons'],'capability_negatives':len(audit['capability_negative_probes'])}
        origin=run_command([sys.executable,'-B','-c','import inference_ref; print(inference_ref.__file__)'],cwd=ROOT,env=clean_environment(),stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=30).stdout.strip()
        if not Path(origin).resolve().is_relative_to(ROOT):raise ValueError('Runtime import escaped clean workspace')
        checks['runtime_import_origin']=origin
        run('static_metadata',[ROOT/'tools/audit_static_metadata.py','--output',output/'static_metadata'],120)
        metadata=json.loads((output/'static_metadata/report.json').read_text())
        if metadata.get('passed') is not True or metadata.get('target_stack_peak') is not None:raise ValueError('PC metadata audit failed or target status promoted')
        checks['static_metadata']={'passed':True,'measurements':{k:v['sizes'] for k,v in metadata['measurements'].items()},'target_layout':None,'target_stack_peak':None}
        run('target_constraints',[ROOT/'tools/check_target_platform.py','--output',output/'target_constraints.json'],120)
        target=json.loads((output/'target_constraints.json').read_text())
        if target.get('passed') is not True or target.get('target_ready') is not False:raise ValueError('Historical target constraints failed')
        checks['target_constraints']={'passed':True,'scope':target['evidence_scope'],'unknown':target['statuses']['unknown']}
        report={'format':'inference-clean-acceptance','version':1,'passed':True,'environment':environment,'initial_build_empty':True,'commands':commands,**checks}
        write_json(output/'report.json',report);print('T1 clean acceptance passed',flush=True);return 0
    except Exception as exc:
        if created and not (output/'report.json').exists():write_json(output/'report.json',{'format':'inference-clean-acceptance','version':1,'passed':False,'error':type(exc).__name__,'message':str(exc),'commands':commands,**checks})
        print(str(exc),file=sys.stderr);return 1


if __name__=='__main__':raise SystemExit(main())
