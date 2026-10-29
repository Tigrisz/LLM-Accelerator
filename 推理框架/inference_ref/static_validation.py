"""Offline orchestration only. Every measured static execution is a C process."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess

import numpy as np
from . import reference,oracle
from .compare import compare_arrays
from .contracts import require
from .c_backend import ROOT,_new_directory
from .fixtures import read_fixture
from .model_package import write_package,read_package
from .package_validation import package_fixture,chain_definition,_evaluate,_hash_tree
from .platform import PCPlatform
from .reporting import write_json_exclusive
from .runtime import load_model
from .sim_device import SimDevice
from .static_backend import build_static,CStaticRuntimeBackend,source_hashes
from .static_export import export_static
from .trace_validation import _execute
from .tracing import TraceRecorder,read_export
from .suite import verify_suite


def validate_c_trace(t):
    errors=[]
    try:
        require(t['format']=='inference-c-static-trace' and t['version']==1,'INVALID_ARGUMENT','C trace version')
        require(t['complete'] is True and t['status']==0,'INVALID_ARGUMENT','C trace incomplete or execution failed')
        require(t['clock']=='host_monotonic_ns' and t['backend']=='pc_c_static','INVALID_ARGUMENT','Clock/backend missing')
        events=t['events'];expected=['bind','run.begin','sync.to_backend','backend.chain','sync.to_cpu','run.end']
        require([e['kind'] for e in events]==expected,'INVALID_ARGUMENT','Missing or out-of-order lifecycle')
        require(type(t['node_count']) is int and 0<t['node_count']<=1024,'INVALID_ARGUMENT','Node count')
        require(all(e['status']==0 and e['timing_valid'] is True and type(e['host_ns']) is int and e['host_ns']>=0 for e in events),'INVALID_ARGUMENT','Invalid event time/status')
        require(all(a['host_ns']<=b['host_ns'] for a,b in zip(events,events[1:])),'INVALID_ARGUMENT','Clock reversed')
        require([e['completed_steps'] for e in events]==[0,0,0,t['node_count'],t['node_count'],t['node_count']], 'INVALID_ARGUMENT','Progress mismatch')
        require(t['c_clock']=='c_process_cpu' and type(t['ticks_per_second']) is int and t['ticks_per_second']>0,'INVALID_ARGUMENT','CPU clock')
        require(len(t['nodes'])==t['node_count'] and all(n['index']==i and n['executed'] is True and n['status']==0 and
            n['timing_valid'] is True and 0<=n['start_ticks']<=n['end_ticks'] for i,n in enumerate(t['nodes'])),'INVALID_ARGUMENT','Node profile missing or invalid')
        require(t['live_allocations']==t['live_backing_bytes']==0,'INVALID_ARGUMENT','Live resources')
    except (KeyError,TypeError,ValueError,Exception) as exc:
        errors.append(str(exc))
    return {'passed':not errors,'errors':errors}


def run_standalone(build,package_path,feeds,directory):
    directory=_new_directory(directory);export_static(package_path,directory/'export')
    package=read_package(package_path);chunks=[]
    for t in package.tensors:
        if t.role=='input':
            array=np.zeros(t.spec.storage_shape,dtype=t.spec.dtype)
            array[tuple(slice(0,d) for d in t.spec.shape)]=feeds[t.id];chunks.append(array.astype(array.dtype.newbyteorder('<'),copy=False).tobytes())
    (directory/'inputs.bin').write_bytes(b''.join(chunks))
    command=[build['host'],str(directory/'export/execution.bin'),str(directory/'export/weights.bin'),
             str(directory/'inputs.bin'),str(directory/'outputs.bin'),str(directory/'trace.json')]
    run=subprocess.run(command,env={'PATH':'/no-python'},capture_output=True,text=True,timeout=30)
    (directory/'stdout.log').write_text(run.stdout,encoding='utf-8');(directory/'stderr.log').write_text(run.stderr,encoding='utf-8')
    require(run.returncode==0,'DEVICE_ERROR',f'Standalone C failed: {run.returncode} {run.stderr}')
    trace=json.loads((directory/'trace.json').read_text());validation=validate_c_trace(trace)
    require(validation['passed'],'INVALID_STATE',str(validation['errors']))
    raw=(directory/'outputs.bin').read_bytes();outputs={};offset=0
    for t in package.tensors:
        if t.role=='output':
            n=t.spec.byte_length
            require(offset+n<=len(raw),'IO_ERROR','Short C output')
            array=np.frombuffer(raw,dtype=np.dtype(t.spec.dtype).newbyteorder('<'),count=n//4,offset=offset).reshape(t.spec.storage_shape)
            outputs[t.id]=array[tuple(slice(0,d) for d in t.spec.shape)].copy();offset+=n
    require(offset==len(raw)==trace['output_bytes'],'INVALID_STATE','Output length mismatch')
    return outputs,{'command':command,'exit_code':run.returncode,'execution_environment':{'PATH':'/no-python'},
        'trace_validation':validation,'node_count':trace['node_count'],'live_allocations':trace['live_allocations']}


def run_static_validation(root,output,compiler=None):
    root=Path(root).resolve();output=Path(output).resolve()
    require(not output.is_relative_to(root),'INVALID_ARGUMENT','Output must be outside frozen fixtures')
    before=_hash_tree(root);baseline=verify_suite(root);directory=_new_directory(output)
    build=build_static(directory/'build',compiler);sanitized=build_static(directory/'sanitized',compiler,sanitize=True)
    native=[]
    for variant in (build,sanitized):
        for executable in variant['tests']:
            run=subprocess.run([executable],capture_output=True,text=True,timeout=30)
            log=Path(executable).with_suffix('.run.log');log.write_text(run.stdout+run.stderr,encoding='utf-8')
            native.append({'path':executable,'sanitize':variant['sanitize'],'exit_code':run.returncode,'passed':run.returncode==0 and not run.stderr})
    platform=PCPlatform();trace=TraceRecorder(clock=platform.clock);backend=CStaticRuntimeBackend(build['library'])
    device=SimDevice(backend,platform=platform,trace=trace);results=[]
    for checked in baseline['cases']:
        name=checked['case_id'];fixture=read_fixture(root/name);path=directory/'packages'/name
        feeds=package_fixture(path,fixture)
        actual,execution=run_standalone(build,path,feeds,directory/'standalone'/name)
        model=load_model(path,platform=platform,trace=trace)
        try: adapted=_execute(device,model,feeds)
        finally:model.close()
        op=fixture.metadata['operation']['name'];policy=fixture.metadata['comparison']
        comparisons={key:compare_arrays(expected,actual['y'],policy['atol'],policy['rtol']) for key,expected in (
            ('stored',fixture.expected),('scalar',reference.execute(op,fixture.inputs)),('numpy',oracle.execute(op,fixture.inputs)))}
        same=actual['y'].tobytes()==adapted.tobytes()
        results.append({'case_id':name,'passed':checked['passed'] and same and all(c['passed'] for c in comparisons.values()),
            'comparisons':comparisons,'adapter_bitwise_equal':same,'execution':execution})
    chains=[]
    for dtype in ('int32','float32'):
        path=directory/'chains'/dtype;write_package(path,**chain_definition(dtype));package=read_package(path)
        for label,values,manual in [('normal',[2,-3,4],[20,-25]),('zero',[0,0,0],[0,-5])]:
            feeds={'x':np.array(values,dtype)}
            actual,execution=run_standalone(build,path,feeds,directory/'chain_runs'/dtype/label)
            sanitized_out,san_execution=run_standalone(sanitized,path,feeds,directory/'sanitized_runs'/dtype/label)
            model=load_model(path,platform=platform,trace=trace)
            try:adapted=_execute(device,model,feeds)
            finally:model.close()
            comparisons={key:compare_arrays(expected,actual['y']) for key,expected in (
                ('scalar',_evaluate(package,feeds,reference.execute)['y']),('numpy',_evaluate(package,feeds,oracle.execute)['y']),('manual',np.array(manual,dtype)))}
            chains.append({'dtype':dtype,'input':label,'passed':all(c['passed'] for c in comparisons.values()) and actual['y'].tobytes()==adapted.tobytes()==sanitized_out['y'].tobytes(),
                'comparisons':comparisons,'execution':execution,'sanitized_execution':san_execution})
    stats=device.stats();device.close();exported=trace.export(directory/'adapter_trace');loaded=read_export(directory/'adapter_trace')
    example=json.loads((directory/'chain_runs/int32/normal/trace.json').read_text())
    negatives=[]
    for name in ('missing_sync','missing_node','wrong_count','wrong_status','reverse_clock'):
        damaged=copy.deepcopy(example)
        if name=='missing_sync':damaged['events']=[e for e in damaged['events'] if e['kind']!='sync.to_cpu']
        elif name=='missing_node':damaged['nodes'].pop()
        elif name=='wrong_count':damaged['events'][-1]['completed_steps']=0
        elif name=='wrong_status':damaged['nodes'][0]['status']=6
        else:damaged['events'][-1]['host_ns']=0
        negatives.append({'name':name,'rejected':not validate_c_trace(damaged)['passed']})
    unchanged=before==_hash_tree(root);count=sum(c['passed'] for c in results);pstats=platform.stats()
    report={'format':'inference-static-report','version':1,'scope':'phase1a_s4','execution':'standalone_c_static_runtime',
        'passed':count==len(results) and baseline['passed'] and all(c['passed'] for c in chains+native) and all(c['rejected'] for c in negatives) and
            loaded['validation']['passed'] and unchanged and pstats['live_allocations']==pstats['backing_bytes']==pstats['open_sources']==pstats['retained_resources']==0 and
            stats['live_tasks']==stats['live_sessions']==stats['staging_reserved_bytes']==0,
        'case_count':len(results),'passed_count':count,'cases':results,'chains':chains,'native_tests':native,'c_trace_negatives':negatives,
        'platform_stats':pstats,'final_device_stats':stats,'adapter_trace':exported,'adapter_trace_validation':loaded['validation'],
        'build':build,'sanitized_build':sanitized,'c_source_sha256':source_hashes(),
        'source_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((ROOT/'inference_ref').glob('*.py'))},
        'fixture_files_unchanged':unchanged,'fixture_files_before_sha256':before,'rv32_execution':False}
    write_json_exclusive(directory/'report.json',report);return report
