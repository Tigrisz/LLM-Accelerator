"""S3 PC platform acceptance. Address-width probes are checks, never RV32 execution."""

import hashlib
import json
from pathlib import Path

import numpy as np

from . import oracle,reference
from .backend_validation import run_backend_validation
from .c_backend import CBackend,ROOT,_new_directory,build_backend
from .compare import compare_arrays
from .contracts import ContractError,require
from .fixtures import read_fixture
from .package_validation import _hash_tree,package_fixture
from .platform import (PCPlatform,PCAllocator,ClockSource,PCSynchronizer,ReadSource,read_exact,
                       checked_span,checked_range,checked_mul,NATIVE_BITS)
from .reporting import write_json_exclusive
from .runtime import load_model,create_session
from .sim_device import SimDevice
from .suite import verify_suite
from .trace_validation import _execute
from .tracing import TraceRecorder,read_export,validate_trace,_encode


def _probes(path,backend):
    rows=[]
    def probe(name,fn):
        try: rows.append({'name':name,'passed':True,**fn()})
        except Exception as exc: rows.append({'name':name,'passed':False,'error':{'code':getattr(exc,'code',type(exc).__name__),'message':str(exc)}})
    def rejected(fn,code=None):
        try: fn()
        except ContractError as exc:
            require(code is None or exc.code==code,'INVALID_STATE','Wrong rejection status')
            return exc.code
        raise ContractError('INVALID_STATE','Expected operation to be rejected')
    def short():
        class Source(ReadSource):
            size=4
            def read_at(self,offset,length): return b'abc'
            def close(self): pass
        return {'status':rejected(lambda:read_exact(Source(),0,4),'IO_ERROR')}
    def ranges():
        require(checked_span(0xffffffff,1,bits=32)==1<<32,'INVALID_STATE','Last-byte check failed')
        rejected(lambda:checked_span(0xffffffff,2,bits=32))
        rejected(lambda:checked_span(1<<32,0,bits=32))
        rejected(lambda:checked_range((1<<64)-1,1,(1<<64)-1))
        rejected(lambda:checked_mul(1<<63,2))
        return {'target_bits_checked':32,'host_pointer_bits':NATIVE_BITS,'rv32_execution':False}
    def allocation():
        class Allocator(PCAllocator):
            def __init__(self): super().__init__(); self.calls=0
            def _allocate_backing(self,size):
                self.calls+=1
                if self.calls==3: raise MemoryError('allocation acceptance probe')
                return super()._allocate_backing(size)
        platform=PCPlatform(allocator=Allocator()); model=load_model(path,platform=platform)
        try:
            before=platform.stats()['backing_bytes']
            rejected(lambda:create_session(model,backend),'RESOURCE_LIMIT')
            require(platform.stats()['backing_bytes']==before,'INVALID_STATE','Partial allocation was not rolled back')
        finally: model.close()
        require(platform.stats()['live_allocations']==0,'INVALID_STATE','Allocation resources remain')
        return {'status':'RESOURCE_LIMIT','resources_released':True}
    def clock():
        class Clock(ClockSource):
            def now_ns(self): return None
        platform=PCPlatform(clock=Clock()); trace=TraceRecorder(clock=platform.clock)
        model=load_model(path,platform=platform,trace=trace)
        try:
            with create_session(model,backend) as session: actual=session.run({'x':np.array([2,-3,4],np.int32)})['y']
            require(compare_arrays(np.array([20,-25],np.int32),actual)['passed'],'INVALID_STATE','Clock changed numerical output')
        finally: model.close()
        require(not trace.snapshot()['complete'] and platform.stats()['live_allocations']==0,'INVALID_STATE','Bad clock not explicit')
        return {'numerics_passed':True,'trace_complete':False,'resources_released':True}
    def sync():
        class Sync(PCSynchronizer):
            acknowledged=False
            def for_cpu(self,blocks): raise ContractError('DEVICE_ERROR','visibility acceptance probe')
            def recover(self): return self.acknowledged
        service=Sync(); platform=PCPlatform(synchronizer=service)
        model=load_model(path,platform=platform); device=SimDevice(backend,platform=platform)
        session=device.create_session(model); handle=session.submit({'x':np.zeros(3,np.int32)})
        result=device.wait(handle,timeout_ticks=10)
        require(result.task.state=='QUARANTINED' and result.task.completed_steps==4,'INVALID_STATE','Sync failure lost progress/quarantine')
        rejected(lambda:device.result(handle)); rejected(lambda:device.release(handle),'BUSY')
        device.recover(handle)
        require(device.wait(handle,timeout_ticks=10).task.state=='QUARANTINED','INVALID_STATE','Unconfirmed sync was released')
        service.acknowledged=True
        device.recover(handle); device.wait(handle,timeout_ticks=10); device.release(handle); device.close(); model.close()
        require(platform.stats()['live_allocations']==0,'INVALID_STATE','Sync resources remain')
        return {'outputs_visible':False,'completed_steps':4,'lease_preserved_until_ack':True,'resources_released':True}
    for name,fn in (('short_read',short),('u64_and_target32_ranges',ranges),('partial_allocation_failure',allocation),
                    ('unavailable_clock',clock),('sync_visibility_and_recovery',sync)): probe(name,fn)
    return rows


def run_platform_validation(root,output,compiler=None):
    root,output=Path(root).resolve(),Path(output).resolve()
    require(not output.is_relative_to(root),'INVALID_ARGUMENT','Output must be outside fixture tree')
    before,baseline=_hash_tree(root),verify_suite(root)
    directory=_new_directory(output); backend=CBackend(build_backend(directory/'backend',compiler))
    platform=PCPlatform(); recorder=TraceRecorder(clock=platform.clock)
    device=SimDevice(backend,platform=platform,trace=recorder); results=[]
    for checked in baseline['cases']:
        name=checked['case_id']
        if not checked['passed']:
            results.append({'case_id':name,'passed':False,'python_validation':checked}); continue
        try:
            fixture=read_fixture(root/name); path=directory/'packages'/name
            feeds=package_fixture(path,fixture)
            model=load_model(path,platform=platform,trace=recorder)
            try: actual=_execute(device,model,feeds)
            finally: model.close()
            op=fixture.metadata['operation']['name']; p=fixture.metadata['comparison']
            comparisons={key:compare_arrays(value,actual,p['atol'],p['rtol']) for key,value in (
                ('stored_vs_platform',fixture.expected),('scalar_vs_platform',reference.execute(op,fixture.inputs)),
                ('numpy_vs_platform',oracle.execute(op,fixture.inputs)))}
            results.append({'case_id':name,'passed':all(c['passed'] for c in comparisons.values()),'comparisons':comparisons})
        except ContractError as exc: results.append({'case_id':name,'passed':False,'error':{'code':exc.code,'message':str(exc)}})
    device_stats=device.stats(); device.close()
    exported=recorder.export(directory/'trace'); loaded=read_export(directory/'trace')
    damaged=json.loads(json.dumps(loaded['trace']))
    damaged['events']=[e for e in damaged['events'] if e['kind']!='platform.sync.to_cpu']
    for i,e in enumerate(damaged['events'],1): e['seq']=i
    damaged['recorded_bytes']=sum(len(_encode(e)) for e in damaged['events'])
    negative=validate_trace(damaged)
    wrong=json.loads(json.dumps(loaded['trace']))
    next(e for e in wrong['events'] if e['kind']=='platform.sync.to_cpu')['context']['model_ref']='wrong_model'
    wrong['recorded_bytes']=sum(len(_encode(e)) for e in wrong['events'])
    negative_context=validate_trace(wrong)
    legacy=run_backend_validation(root,directory/'backends',compiler)
    probes=_probes(directory/'backends/runtime_trace/chains/int32',backend)
    unchanged=before==_hash_tree(root); count=sum(c['passed'] for c in results); stats=platform.stats()
    report={'format':'inference-platform-report','version':1,'scope':'phase1a_s3','source':'pc_platform',
        'execution':'pc_c_backend','passed':count==len(results) and baseline['passed'] and legacy['passed'] and unchanged and
            loaded['validation']['passed'] and not negative['passed'] and not negative_context['passed'] and all(p['passed'] for p in probes) and
            stats['live_allocations']==stats['backing_bytes']==stats['open_sources']==0 and
            stats['retained_resources']==0 and
            device_stats['live_tasks']==device_stats['live_sessions']==device_stats['staging_reserved_bytes']==0,
        'case_count':len(results),'passed_count':count,'cases':results,'platform_probes':probes,'platform_stats':stats,
        'final_device_stats':device_stats,'trace_validation':loaded['validation'],'trace_export':exported,
        'negative_missing_visibility_sync':negative,'backend_report':'backends/report.json','backend_validation_passed':legacy['passed'],
        'negative_wrong_sync_context':negative_context,
        'target_address_probe_bits':32,'rv32_execution':False,'fixture_files_unchanged':unchanged,
        'fixture_files_before_sha256':before,'environment':baseline['environment'],'build':backend.build,
        'source_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((ROOT/'inference_ref').glob('*.py'))}}
    write_json_exclusive(directory/'report.json',report)
    return report
