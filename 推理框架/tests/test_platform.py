import importlib
import unittest
import os
import shutil
from dataclasses import replace
from pathlib import Path

import numpy as np

from inference_ref.contracts import ContractError
from tests.support import Workspace

try: api=importlib.import_module('inference_ref.platform')
except ModuleNotFoundError: api=None


class PlatformPrimitiveTests(unittest.TestCase):
    def setUp(self): self.assertIsNotNone(api,'S3 platform API missing')

    def test_u64_and_32bit_boundaries_never_truncate(self):
        self.assertEqual(api.checked_span(0xffffffff,1,bits=32),1<<32)
        self.assertEqual(api.checked_span(0,0,bits=32),0)
        for base,size in ((1<<32,0),(0xffffffff,2),(-1,1),(0,1<<32),(True,1),(0,False)):
            with self.subTest(base=base,size=size):
                with self.assertRaises(ContractError): api.checked_span(base,size,bits=32)
        self.assertEqual(api.checked_range(7,3,10),10)
        for args in ((7,4,10),((1<<64)-1,1,(1<<64)-1),(0,-1,10)):
            with self.assertRaises(ContractError): api.checked_range(*args)
        with self.assertRaises(ContractError): api.checked_mul(1<<63,2)

    def test_exact_read_rejects_short_read_and_wrong_types(self):
        class Source(api.ReadSource):
            size=4
            def read_at(self,offset,length): return b'abc'
            def close(self): pass
        with self.assertRaises(ContractError) as caught: api.read_exact(Source(),0,4)
        self.assertEqual(caught.exception.code,'IO_ERROR')
        with self.assertRaises(ContractError): api.read_exact(Source(),3,2)

    def test_read_memory_failure_has_typed_resource_error(self):
        class Source(api.ReadSource):
            size=4
            def read_at(self,offset,length): raise MemoryError('read allocation probe')
            def close(self): pass
        with self.assertRaises(ContractError) as caught: api.read_exact(Source(),0,4)
        self.assertEqual(caught.exception.code,'RESOURCE_LIMIT')

    def test_read_blob_limit_uses_one_size_snapshot(self):
        class Source(api.ReadSource):
            def __init__(self): self.calls=0; self.requested=[]
            @property
            def size(self):
                self.calls+=1
                return 4 if self.calls<=2 else 1000
            def read_at(self,offset,length): self.requested.append(length); return b'x'*length
            def close(self): pass
        source=Source()
        class Platform(api.PCPlatform):
            def open_read(self,path): return source
        self.assertEqual(Platform().read_blob('unused',4),b'xxxx')
        self.assertEqual(source.requested,[4])

    def test_direct_clock_failure_cannot_leave_complete_true(self):
        from inference_ref.tracing import TraceRecorder
        class Clock(api.ClockSource):
            def __init__(self): self.values=iter((10,None))
            def now_ns(self): return next(self.values)
        trace=TraceRecorder(clock=Clock())
        with self.assertRaises(ContractError): trace.record('bad_clock')
        self.assertFalse(trace.snapshot()['complete'])

    def test_pc_file_random_access_bounds_and_close(self):
        work=Workspace(); self.addCleanup(work.cleanup)
        path=Path(work.name)/'data.bin'; path.write_bytes(b'abcdef')
        platform=api.PCPlatform()
        with platform.open_read(path) as source:
            self.assertEqual(api.read_exact(source,2,3),b'cde')
            self.assertEqual(api.read_exact(source,6,0),b'')
            with self.assertRaises(ContractError): api.read_exact(source,5,2)
        self.assertEqual(platform.stats()['open_sources'],0)
        with self.assertRaises(ContractError): source.read_at(0,1)

    def test_allocator_alignment_budget_and_explicit_release(self):
        allocator=api.PCAllocator(budget_bytes=10000)
        for alignment in (4,16,64,4096):
            block=allocator.allocate(37,alignment)
            self.assertEqual(block.address%alignment,0)
            self.assertEqual(block.backing.nbytes,37+alignment-1)
            self.assertEqual(block.data.nbytes,37)
            block.close(); block.close()
        self.assertEqual(allocator.stats()['live_allocations'],0)
        with self.assertRaises(ContractError): allocator.allocate(10001,64)
        with self.assertRaises(ContractError): allocator.allocate(5,3)
        empty=allocator.allocate(0,64); self.assertEqual(empty.address,0); empty.close()

    def test_allocation_failure_or_32bit_host_rejection_does_not_charge_budget(self):
        class Failing(api.PCAllocator):
            def _allocate_backing(self,size): raise MemoryError('allocation probe')
        allocator=Failing()
        with self.assertRaises(ContractError) as caught: allocator.allocate(32,64)
        self.assertEqual(caught.exception.code,'RESOURCE_LIMIT')
        self.assertEqual(allocator.stats()['backing_bytes'],0)
        native=api.PCAllocator(); block=native.allocate(32,64)
        if block.address>0xffffffff:
            limited=api.PCAllocator(pointer_bits=32)
            with self.assertRaises(ContractError): limited.allocate(32,64)
            self.assertEqual(limited.stats()['live_allocations'],0)
        block.close()

    def test_foreign_release_and_released_sync_are_rejected(self):
        one,two=api.PCAllocator(),api.PCAllocator()
        block=one.allocate(16,64)
        with self.assertRaises(ContractError): two.release(block)
        sync=api.PCSynchronizer()
        self.assertIs(sync.for_device((block,)),True)
        self.assertIs(sync.for_cpu((block,)),True)
        block.close()
        with self.assertRaises(ContractError): sync.for_cpu((block,))

    def test_clock_source_unavailable_or_backwards_marks_trace_incomplete(self):
        from inference_ref.tracing import TraceRecorder,safe_record,validate_trace
        class Clock(api.ClockSource):
            def __init__(self,values): self.values=iter(values)
            def now_ns(self): return next(self.values)
        trace=TraceRecorder(clock=Clock([10,20,19,30]))
        safe_record(trace,'one'); safe_record(trace,'backwards'); safe_record(trace,'two')
        doc=trace.snapshot()
        self.assertFalse(doc['complete'])
        self.assertEqual(len(doc['events']),2)
        self.assertEqual(doc['clock'],'host_monotonic_ns_relative')
        self.assertFalse(validate_trace(doc)['passed'])
        unavailable=TraceRecorder(clock=Clock([None,None]))
        safe_record(unavailable,'one')
        self.assertFalse(unavailable.snapshot()['complete'])

    def test_plan_addressing_checks_target_width_without_mapping_pc_pointer(self):
        from inference_ref.memory import MemoryPlan,validate_plan_addressing
        plan=MemoryPlan(64,(),0,128,64,126,318,318)
        validate_plan_addressing(plan,address_bits=32)
        with self.assertRaises(ContractError): validate_plan_addressing(replace(plan,total_bytes=1<<32),address_bits=32)


class PlatformRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not any(shutil.which(c) for c in ('cc','gcc','clang')):
            if os.environ.get('IR_REQUIRE_C')=='1': raise RuntimeError('C compiler required')
            raise unittest.SkipTest('Use WSL with C compiler')
        from inference_ref.c_backend import CBackend,build_backend
        from inference_ref.model_package import write_package
        from tests.package_support import chain_definition
        cls.work=Workspace(); cls.addClassCleanup(cls.work.cleanup)
        cls.backend=CBackend(build_backend(Path(cls.work.name)/'backend'))
        cls.path=Path(cls.work.name)/'model'; write_package(cls.path,**chain_definition())

    def test_platform_reads_and_owned_model_session_memory(self):
        from inference_ref.runtime import load_model,create_session
        class Platform(api.PCPlatform):
            def __init__(self): super().__init__(); self.reads=[]
            def open_read(self,path): self.reads.append(Path(path).name); return super().open_read(path)
        platform=Platform(); model=load_model(self.path,platform=platform)
        self.assertEqual(platform.reads,['manifest.json','weights.bin'])
        session=create_session(model,self.backend)
        with self.assertRaises(ContractError): model.close()
        np.testing.assert_array_equal(session.run({'x':np.array([2,-3,4],np.int32)})['y'],[20,-25])
        self.assertEqual(session.memory_info()['total_backing_bytes'],model.plan.total_bytes)
        session.close(); model.close(); model.close()
        self.assertEqual(platform.stats()['live_allocations'],0)
        self.assertEqual(platform.stats()['open_sources'],0)
        with self.assertRaises(ContractError): create_session(model,self.backend)

    def test_short_package_read_closes_source_and_returns_no_model(self):
        from inference_ref.runtime import load_model
        class Short(api.PCPlatform):
            def open_read(self,path):
                source=super().open_read(path)
                class Wrapper(api.ReadSource):
                    size=source.size
                    def read_at(self,offset,length): return source.read_at(offset,length)[:-1]
                    def close(self): source.close()
                return Wrapper()
        platform=Short()
        with self.assertRaises(ContractError) as caught: load_model(self.path,platform=platform)
        self.assertEqual(caught.exception.code,'IO_ERROR')
        self.assertEqual(platform.stats()['open_sources'],0)
        self.assertEqual(platform.stats()['live_allocations'],0)

    def test_partial_session_allocation_failure_rolls_back_only_session_memory(self):
        from inference_ref.runtime import load_model,create_session
        class Failing(api.PCAllocator):
            def __init__(self): super().__init__(); self.calls=0
            def _allocate_backing(self,size):
                self.calls+=1
                if self.calls==3: raise MemoryError('workspace allocation probe')
                return super()._allocate_backing(size)
        platform=api.PCPlatform(allocator=Failing())
        model=load_model(self.path,platform=platform)
        before=platform.stats()['backing_bytes']
        with self.assertRaises(ContractError): create_session(model,self.backend)
        self.assertEqual(platform.stats()['backing_bytes'],before)
        model.close(); self.assertEqual(platform.stats()['live_allocations'],0)

    def test_platform_sync_order_and_trace_links(self):
        from inference_ref.runtime import load_model,create_session
        from inference_ref.c_execution import CStaticBackend
        from inference_ref.tracing import TraceRecorder,validate_trace
        order=[]
        class Sync(api.PCSynchronizer):
            def for_device(self,blocks): order.append('publish'); return super().for_device(blocks)
            def for_cpu(self,blocks): order.append('visible'); return super().for_cpu(blocks)
        class Backend(CStaticBackend):
            def prepare(self,*args,**kwargs):
                binding=super().prepare(*args,**kwargs); execute=binding.execute
                def run(): order.append('compute'); return execute()
                binding.execute=run; return binding
        platform=api.PCPlatform(synchronizer=Sync()); trace=TraceRecorder(clock=platform.clock)
        model=load_model(self.path,platform=platform,trace=trace)
        with create_session(model,Backend(self.backend)) as session: session.run({'x':np.zeros(3,np.int32)})
        model.close()
        self.assertEqual(order,['publish','compute','visible'])
        kinds={e['kind'] for e in trace.snapshot()['events']}
        self.assertTrue({'platform.read','platform.allocate','platform.sync.to_backend','platform.sync.to_cpu'}<=kinds)
        checked=validate_trace(trace.snapshot()); self.assertTrue(checked['passed'],checked)

    def test_failed_output_sync_quarantines_until_sync_service_acknowledges(self):
        from inference_ref.runtime import load_model
        from inference_ref.sim_device import SimDevice
        from inference_ref.tracing import TraceRecorder,validate_trace
        class Sync(api.PCSynchronizer):
            acknowledged=False
            def for_cpu(self,blocks): raise ContractError('DEVICE_ERROR','visibility unconfirmed')
            def recover(self): return self.acknowledged
        sync=Sync(); platform=api.PCPlatform(synchronizer=sync)
        trace=TraceRecorder(clock=platform.clock)
        model=load_model(self.path,platform=platform,trace=trace)
        device=SimDevice(self.backend,platform=platform,trace=trace); session=device.create_session(model)
        handle=session.submit({'x':np.zeros(3,np.int32)})
        result=device.wait(handle,timeout_ticks=10)
        self.assertEqual(result.task.state,'QUARANTINED')
        self.assertEqual(result.task.completed_steps,4)
        with self.assertRaises(ContractError): device.result(handle)
        with self.assertRaises(ContractError): device.release(handle)
        device.recover(handle); self.assertEqual(device.wait(handle,timeout_ticks=10).task.state,'QUARANTINED')
        sync.acknowledged=True
        device.recover(handle); device.wait(handle,timeout_ticks=10); device.release(handle); device.close(); model.close()
        self.assertEqual(platform.stats()['live_allocations'],0)
        checked=validate_trace(trace.snapshot()); self.assertTrue(checked['passed'],checked)

    def test_unavailable_platform_clock_does_not_change_c_result(self):
        from inference_ref.runtime import load_model,create_session
        from inference_ref.tracing import TraceRecorder
        class Clock(api.ClockSource):
            def now_ns(self): return None
        platform=api.PCPlatform(clock=Clock()); trace=TraceRecorder(clock=platform.clock)
        model=load_model(self.path,platform=platform,trace=trace)
        with create_session(model,self.backend) as session:
            np.testing.assert_array_equal(session.run({'x':np.array([2,-3,4],np.int32)})['y'],[20,-25])
        model.close()
        self.assertFalse(trace.snapshot()['complete'])
        self.assertEqual(platform.stats()['live_allocations'],0)

    def test_partial_close_failure_blocks_run_and_allows_explicit_close_retry(self):
        from inference_ref.runtime import load_model,create_session
        class Allocator(api.PCAllocator):
            def __init__(self): super().__init__(); self.calls=0
            def release(self,block):
                self.calls+=1
                if self.calls==2: raise ContractError('IO_ERROR','release failure probe')
                super().release(block)
        platform=api.PCPlatform(allocator=Allocator()); model=load_model(self.path,platform=platform)
        session=create_session(model,self.backend)
        with self.assertRaises(ContractError): session.close()
        with self.assertRaises(ContractError) as caught: session.run({'x':np.zeros(3,np.int32)})
        self.assertEqual(caught.exception.code,'BUSY')
        with self.assertRaises(ContractError): model.close()
        session.close(); model.close()
        self.assertEqual(platform.stats()['live_allocations'],0)

    def test_successful_trace_requires_output_visibility_sync(self):
        import json
        from inference_ref.runtime import load_model,create_session
        from inference_ref.tracing import TraceRecorder,validate_trace,_encode
        trace=TraceRecorder(); model=load_model(self.path,trace=trace)
        with create_session(model,self.backend) as session: session.run({'x':np.zeros(3,np.int32)})
        model.close(); document=trace.snapshot()
        self.assertTrue(validate_trace(document)['passed'])
        document['events']=[e for e in document['events'] if e['kind']!='platform.sync.to_cpu']
        for i,e in enumerate(document['events'],1): e['seq']=i
        document['recorded_bytes']=sum(len(_encode(e)) for e in document['events'])
        self.assertFalse(validate_trace(document)['passed'])

    def test_platform_acceptance_cli(self):
        import json,subprocess,sys
        work=Workspace(); self.addCleanup(work.cleanup)
        output=Path(work.name)/'acceptance'
        command=[sys.executable,'-B','-m','inference_ref','verify-platform','--fixtures',str(Path(__file__).resolve().parents[1]/'fixtures/synthetic-v1'),'--output',str(output)]
        run=subprocess.run(command,capture_output=True,text=True,timeout=180)
        self.assertEqual(run.returncode,0,run.stderr)
        report=json.loads((output/'report.json').read_text())
        self.assertTrue(report['passed'])
        self.assertEqual(report['passed_count'],54)
        self.assertTrue(all(p['passed'] for p in report['platform_probes']))
        self.assertEqual(report['platform_stats']['live_allocations'],0)
        self.assertFalse(report.get('negative_wrong_sync_context',{}).get('passed',True))
        self.assertEqual(report['platform_stats']['retained_resources'],0)
        self.assertEqual(subprocess.run(command,capture_output=True).returncode,2)

    def test_legacy_garbage_collection_does_not_leave_model_permanently_borrowed(self):
        import gc,weakref
        from inference_ref.runtime import load_model,create_session
        platform=api.PCPlatform(); model=load_model(self.path,platform=platform)
        session=create_session(model,self.backend); ref=weakref.ref(session)
        del session; gc.collect()
        self.assertIsNone(ref())
        model.close(); gc.collect()
        self.assertEqual(platform.stats()['live_allocations'],0)

    def test_failed_input_sync_does_not_enter_backend_or_return_outputs(self):
        from inference_ref.runtime import load_model,create_session
        from inference_ref.c_execution import CStaticBackend
        calls=[]
        class Sync(api.PCSynchronizer):
            def for_device(self,blocks): raise ContractError('DEVICE_ERROR','input synchronization probe')
        class Backend(CStaticBackend):
            def prepare(self,*args,**kwargs):
                binding=super().prepare(*args,**kwargs); execute=binding.execute
                def run(): calls.append('execute'); return execute()
                binding.execute=run; return binding
        platform=api.PCPlatform(synchronizer=Sync()); model=load_model(self.path,platform=platform)
        session=create_session(model,Backend(self.backend))
        with self.assertRaises(RuntimeError): session.run({'x':np.zeros(3,np.int32)})
        self.assertEqual(calls,[])
        self.assertEqual(session.last_result['completed_steps'],0)
        with self.assertRaises(ContractError): session.close()
        session.recover(); session.close(); model.close()
        self.assertEqual(platform.stats()['live_allocations'],0)

    def test_unknown_resources_survive_gc_even_after_all_client_handles_are_lost(self):
        import gc,weakref
        from inference_ref.runtime import load_model,create_session
        class Sync(api.PCSynchronizer):
            acknowledged=False
            def for_device(self,blocks): raise RuntimeError('unknown synchronization')
            def recover(self): return self.acknowledged
        platform=api.PCPlatform(synchronizer=Sync()); model=load_model(self.path,platform=platform)
        session=create_session(model,self.backend)
        with self.assertRaises(RuntimeError): session.run({'x':np.zeros(3,np.int32)})
        refs=tuple(weakref.ref(obj) for obj in (session,model,platform,session._activation._block,session._workspace._block))
        del session,model,platform; gc.collect()
        try:
            self.assertTrue(all(r() is not None for r in refs),'Unknown resources were collected without acknowledgement')
            records=api.retained_resources()
            retained=next(r.owner for r in records if r.owner is refs[0]())
            self.assertEqual(retained.platform.stats()['live_allocations'],3)
            with self.assertRaises(ContractError): retained.recover()
        finally:
            for record in getattr(api,'retained_resources',lambda:())():
                if record.owner is refs[0]():
                    owned=record.owner; owned.platform.synchronizer.acknowledged=True
                    owner_model=owned._model
                    owned.recover(); owned.close(); owner_model.close()

    def test_binding_close_failure_latches_closing_and_retries_binding_close(self):
        from inference_ref.runtime import load_model,create_session
        from inference_ref.c_execution import CStaticBackend
        from inference_ref.backend import BoundChain
        calls=[]
        class Binding(BoundChain):
            def __init__(self,inner): self.inner,self.closes=inner,0
            def execute(self): calls.append('execute'); return self.inner.execute()
            def close(self):
                self.closes+=1; calls.append('close')
                if self.closes==1: raise ContractError('IO_ERROR','binding close probe')
                self.inner.close()
        class Backend(CStaticBackend):
            def prepare(self,*args,**kwargs): return Binding(super().prepare(*args,**kwargs))
        platform=api.PCPlatform(); model=load_model(self.path,platform=platform)
        session=create_session(model,Backend(self.backend))
        with self.assertRaises(ContractError): session.close()
        try:
            with self.assertRaises(ContractError) as caught: session.run({'x':np.zeros(3,np.int32)})
            self.assertEqual(caught.exception.code,'BUSY')
        finally: session.close(); model.close()
        self.assertEqual(calls,['close','close'])
        self.assertEqual(platform.stats()['live_allocations'],0)

    def test_sync_events_are_bound_to_full_run_context(self):
        import json
        from inference_ref.runtime import load_model,create_session
        from inference_ref.tracing import TraceRecorder,validate_trace,_encode
        platform=api.PCPlatform(); trace=TraceRecorder(clock=platform.clock)
        model=load_model(self.path,platform=platform,trace=trace)
        for _ in range(2):
            with create_session(model,self.backend) as session: session.run({'x':np.zeros(3,np.int32)})
        model.close(); original=trace.snapshot()
        self.assertTrue(validate_trace(original)['passed'])
        first=next(e for e in original['events'] if e['kind']=='session.open')['context']['session_ref']
        for key,value in (('session_ref',first),('model_ref','wrong_model'),('task_ref','wrong_task'),
                          ('device_ref','wrong_device'),('selected_backend','wrong_backend')):
            with self.subTest(key=key):
                doc=json.loads(json.dumps(original))
                event=next(e for e in reversed(doc['events']) if e['kind']=='platform.sync.to_cpu')
                event['context'][key]=value
                doc['recorded_bytes']=sum(len(_encode(e)) for e in doc['events'])
                self.assertFalse(validate_trace(doc)['passed'])
