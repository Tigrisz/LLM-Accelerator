"""S5 bounded PC resource pressure; nested S4 preserves numerical acceptance."""
import gc
import hashlib
from pathlib import Path

import numpy as np
from .backend import BoundChain
from .c_backend import ROOT,_new_directory,CBackend
from .c_execution import CStaticBackend
from .contracts import ContractError,require
from .model_package import write_package
from .package_validation import chain_definition
from .platform import PCPlatform,PCSynchronizer,retained_resources
from .reporting import write_json_exclusive
from .resources import ResourceLedger
from .runtime import load_model,create_session
from .sim_device import SimDevice,SimConfig
from .static_backend import CStaticRuntimeBackend
from .static_validation import run_static_validation
from .tracing import TraceRecorder


def _zero(ledger):
    snap=ledger.snapshot();require(snap['live_entries']==snap['live_bytes']==snap['resident_bytes']==0,'INVALID_STATE','Resources remain')
    return snap


def _rejected(fn):
    try:fn()
    except ContractError as exc:
        require(exc.code=='RESOURCE_LIMIT','INVALID_STATE','Wrong budget failure classification');return
    raise ContractError('INVALID_STATE','Expected resource refusal')


def _pressure(path,backend,dtype,iterations):
    ledger=ResourceLedger();platform=PCPlatform(ledger=ledger);trace=TraceRecorder(ledger=ledger,max_events=128,max_bytes=32768)
    model=load_model(path,platform=platform,trace=trace);device=SimDevice(backend,platform=platform,trace=trace,config=SimConfig(max_task_events=16))
    sessions=[device.create_session(model) for _ in range(3)];feeds={'x':np.array([2,-3,4],dtype)}
    addresses=[s.memory_info() for s in sessions];plateau=None
    for cycle in range(iterations):
        handles=[s.submit(feeds) for s in sessions]
        for handle in handles:
            require(device.wait(handle,timeout_ticks=30).task.state=='SUCCEEDED','INVALID_STATE','Stress task failed')
            require(np.array_equal(device.result(handle)['y'],np.array([20,-25],dtype)),'INVALID_STATE','Stress numeric mismatch')
            device.release(handle)
        current=ledger.snapshot()
        require(current['categories']['task_records']['live_count']==current['categories']['task_staging']['live_bytes']==current['categories']['task_events']['live_count']==0,'INVALID_STATE','Released task still charged')
        require([s.memory_info() for s in sessions]==addresses,'INVALID_STATE','Arenas moved')
        if cycle>=1:
            if plateau is None:plateau=current['live_bytes']
            require(current['live_bytes']==plateau,'INVALID_STATE','Resource baseline grows across repeats')
    for fault in ('lost_completion','stuck_cancel','device_error'):
        handle=sessions[0].submit(feeds,fault=fault)
        if fault=='stuck_cancel':device.cancel(handle)
        done=device.wait(handle,timeout_ticks=30).task
        if done.state=='QUARANTINED':
            require(ledger.snapshot()['categories']['task_staging']['live_bytes']==20,'INVALID_STATE','Quarantine released staging')
            device.recover(handle);device.wait(handle,timeout_ticks=30)
        device.release(handle)
    for s in sessions:s.close()
    device_stats=device.stats();device.close();model.close();before_close=ledger.snapshot()
    require(trace.snapshot()['complete'] is False,'INVALID_STATE','Expected bounded trace overflow')
    require(before_close['categories']['trace']['live_bytes']>0,'INVALID_STATE','Trace cache prematurely uncharged')
    trace.close();final=_zero(ledger)
    require(not retained_resources(platform.platform_id),'INVALID_STATE','Recovery owners remain')
    return {'backend':backend.backend_id,'dtype':dtype,'iterations':iterations,'successful_tasks':iterations*3,
        'session_count':3,'stable_arena_addresses':True,'steady_state_plateau':True,'final_ledger':final,
        'trace_retained_until_close':before_close['categories']['trace'],'final_device_stats':device_stats}


def _budget_probe(path,backend,category):
    kwargs={'count_limits':{category:0}} if category in {'task_records','session_records','task_events'} else {'byte_limits':{category:0}}
    ledger=ResourceLedger(**kwargs);platform=PCPlatform(ledger=ledger);model=None;session=None;device=None
    trace=TraceRecorder(ledger=ledger,max_events=128) if category in {'c_profiles','trace'} else None
    if category=='arena':_rejected(lambda:load_model(path,platform=platform))
    else:
        model=load_model(path,platform=platform,trace=trace)
        if category in {'c_metadata','session_records'}:_rejected(lambda:create_session(model,backend))
        elif category in {'task_records','task_staging','task_events'}:
            device=SimDevice(backend,platform=platform);session=device.create_session(model)
            feeds={'x':np.array([2,-3,4],np.int32)}
            if category!='task_events':_rejected(lambda:session.submit(feeds))
            else:
                handle=session.submit(feeds);device.wait(handle,timeout_ticks=10)
                require(device.resource_info()['dropped_task_events']>0,'INVALID_STATE','Task history limit ignored');device.release(handle)
        else:
            session=create_session(model,backend)
            require(np.array_equal(session.run({'x':np.array([2,-3,4],np.int32)})['y'],[20,-25]),'INVALID_STATE','Observation limit changed numerics')
            require(not trace.snapshot()['complete'],'INVALID_STATE','Observation limit must be explicit')
    if session is not None:session.close()
    if device is not None:device.close()
    if model is not None:model.close()
    if trace is not None:trace.close()
    return {'category':category,'final_ledger':_zero(ledger)}


def _allocation_sweep(path,backend):
    rows=[]
    for stop in range(20):
        ledger=ResourceLedger();platform=PCPlatform(ledger=ledger);ledger.fail_after=stop;model=session=None;status='OK'
        try:
            model=load_model(path,platform=platform);session=create_session(model,backend)
        except ContractError as exc:
            require(exc.code=='RESOURCE_LIMIT','INVALID_STATE','Fault misclassified');status=exc.code
        finally:
            ledger.fail_after=None
            if session is not None:session.close()
            if model is not None:model.close()
        rows.append({'fail_after':stop,'status':status,'released':_zero(ledger)['live_bytes']==0})
    require(any(r['status']=='OK' for r in rows) and any(r['status']=='RESOURCE_LIMIT' for r in rows),'INVALID_STATE','Sweep did not cross admission boundary')
    return {'backend':backend.backend_id,'allocation_points':rows}


def _recover_and_close(path,backend):
    class Sync(PCSynchronizer):
        allow=False
        def for_cpu(self,blocks):raise RuntimeError('S5 sync failure')
        def recover(self):return self.allow
    sync=Sync();ledger=ResourceLedger();platform=PCPlatform(ledger=ledger,synchronizer=sync)
    model=load_model(path,platform=platform);device=SimDevice(backend,platform=platform,config=SimConfig(max_task_events=8))
    session=device.create_session(model);handle=session.submit({'x':np.array([2,-3,4],np.int32)})
    device.wait(handle,timeout_ticks=10)
    for _ in range(50):device.recover(handle);device.wait(handle,timeout_ticks=10)
    require(len(device.events(handle))<=8,'INVALID_STATE','Unbounded recovery history')
    held=ledger.snapshot()['live_bytes'];del session,model,device;gc.collect()
    owners=[r.owner for r in retained_resources(platform.platform_id) if isinstance(r.owner,SimDevice)]
    require(len(owners)==1 and ledger.snapshot()['live_bytes']==held,'INVALID_STATE','Unknown device graph escaped')
    device=owners.pop();session=device._tasks[handle.task_id].session;model=session._session._model
    dropped=device.resource_info()['dropped_task_events'];sync.allow=True;device.recover(handle);device.wait(handle,timeout_ticks=10);device.release(handle)
    inner=session._session;binding=inner._binding;close=binding.close;attempts=[0]
    def close_once():
        attempts[0]+=1
        if attempts[0]==1:raise RuntimeError('S5 incomplete close')
        close()
    binding.close=close_once
    try:session.close()
    except RuntimeError:pass
    else:raise ContractError('INVALID_STATE','Close failure not injected')
    held_close=ledger.snapshot()['live_bytes'];gc.collect()
    require(held_close==ledger.snapshot()['live_bytes'] and held_close>0,'INVALID_STATE','Incomplete close uncharged')
    session.close();device.close();model.close()
    require(not retained_resources(platform.platform_id),'INVALID_STATE','Retained owners remain')
    return {'recovery_refusals':50,'dropped_history_events':dropped,'unknown_graph_retained':True,'close_attempts':attempts[0],'final_ledger':_zero(ledger)}


def run_resource_validation(root,output,compiler=None,*,iterations=200):
    require(type(iterations) is int and 1<=iterations<=10000,'INVALID_ARGUMENT','Iterations must be 1..10000')
    root=Path(root).resolve();output=Path(output).resolve()
    require(not output.is_relative_to(root),'INVALID_ARGUMENT','Output must be outside fixtures')
    directory=_new_directory(output)
    static=run_static_validation(root,directory/'static_runtime',compiler)
    library=static['build']['library'];backends=[CStaticBackend(CBackend(Path(library))),CStaticRuntimeBackend(library)]
    paths={}
    for dtype in ('int32','float32'):
        path=directory/'models'/dtype;write_package(path,**chain_definition(dtype));paths[dtype]=path
    rows=[]
    def probe(name,fn):
        try:rows.append({'name':name,'passed':True,**fn()})
        except Exception as exc:rows.append({'name':name,'passed':False,'error':{'code':getattr(exc,'code',type(exc).__name__),'message':str(exc)}})
    for backend in backends:
        for dtype in paths:probe('repeat_'+backend.backend_id+'_'+dtype,lambda b=backend,d=dtype:_pressure(paths[d],b,d,iterations))
        probe('allocation_sweep_'+backend.backend_id,lambda b=backend:_allocation_sweep(paths['int32'],b))
        probe('recover_close_'+backend.backend_id,lambda b=backend:_recover_and_close(paths['int32'],b))
        for category in ('arena','c_metadata','c_profiles','trace','task_staging','task_records','session_records','task_events'):
            probe('budget_'+backend.backend_id+'_'+category,lambda b=backend,c=category:_budget_probe(paths['int32'],b,c))
    report={'format':'inference-resource-report','version':1,'scope':'phase1a_s5','resource_api':1,
        'passed':static['passed'] and all(p['passed'] for p in rows),'case_count':static['case_count'],'passed_count':static['passed_count'],
        'iterations':iterations,'measurement':'managed_payload_and_records_not_process_rss','stress_probes':rows,
        'static_report':'static_runtime/report.json','static_validation_passed':static['passed'],
        'source_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((ROOT/'inference_ref').glob('*.py'))},
        'rv32_execution':False,'model_binding':None,'quantization_binding':None}
    write_json_exclusive(directory/'report.json',report);return report
