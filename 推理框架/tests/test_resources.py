"""S5 managed payload ledger and lifecycle regressions."""
import gc
from pathlib import Path
import tempfile
import unittest
import shutil
import subprocess
import sys
import json
from unittest import mock
import numpy as np

from inference_ref.contracts import ContractError
from inference_ref.c_backend import ROOT
from inference_ref.model_package import write_package
from inference_ref.package_validation import chain_definition


class LedgerTests(unittest.TestCase):
    def test_limits_peak_atomic_resize_and_release(self):
        from inference_ref.resources import ResourceLedger
        ledger=ResourceLedger(budget_bytes=10,byte_limits={'arena':8},count_limits={'task_records':1})
        a=ledger.reserve('arena',8,resident_bytes=8,label='one')
        with self.assertRaises(ContractError):ledger.reserve('arena',1)
        with self.assertRaises(ContractError):a.resize(9)
        t=ledger.reserve('task_records',0,count=1)
        with self.assertRaises(ContractError):ledger.reserve('task_records',0)
        a.resize(6,resident_bytes=6)
        self.assertEqual(ledger.snapshot()['live_bytes'],6)
        self.assertEqual(ledger.snapshot()['peak_bytes'],8)
        a.close();a.close();t.close();self.assertEqual(ledger.snapshot()['live_entries'],0)

    def test_injection_overflow_and_gc(self):
        from inference_ref.resources import ResourceLedger
        ledger=ResourceLedger(budget_bytes=(1<<64)-1)
        with self.assertRaises(ContractError):ledger.reserve('arena',1<<64)
        token=ledger.reserve('arena',4)
        ledger.fail_after=0
        with self.assertRaises(ContractError):ledger.reserve('arena',1)
        self.assertEqual(ledger.snapshot()['live_bytes'],4)
        del token;gc.collect();self.assertEqual(ledger.snapshot()['live_bytes'],0)

    def test_group_rolls_back_failed_native_allocation(self):
        from inference_ref.resources import ResourceLedger,ResourceGroup
        ledger=ResourceLedger(budget_bytes=10)
        group=ResourceGroup(ledger)
        def broken():raise MemoryError('native allocation')
        with self.assertRaises(ContractError):group.allocate(broken,4,label='probe')
        self.assertEqual(ledger.snapshot()['live_bytes'],0)
        group.allocate(lambda:object(),4,label='small');group.close()
        self.assertEqual(ledger.snapshot()['live_entries'],0)


class ResourcePlatformTests(unittest.TestCase):
    def test_arena_budget_and_partial_allocation_cleanup(self):
        from inference_ref.resources import ResourceLedger
        from inference_ref.platform import PCPlatform,PCAllocator
        ledger=ResourceLedger(budget_bytes=70)
        platform=PCPlatform(ledger=ledger)
        with self.assertRaises(ContractError):platform.allocate(8,64)
        self.assertEqual(ledger.snapshot()['live_bytes'],0)
        block=platform.allocate(7,64)
        self.assertEqual(ledger.snapshot()['categories']['arena']['live_bytes'],70)
        block.close();self.assertEqual(ledger.snapshot()['live_entries'],0)
        class Broken(PCAllocator):
            def _allocate_backing(self,size):raise MemoryError('arena failure')
        with self.assertRaises(ContractError):PCPlatform(ledger=ledger,allocator=Broken()).allocate(4,64)
        self.assertEqual(ledger.snapshot()['live_entries'],0)

    def test_trace_budget_growth_and_close(self):
        from inference_ref.resources import ResourceLedger
        from inference_ref.tracing import TraceRecorder,safe_record
        ledger=ResourceLedger(byte_limits={'trace':200})
        trace=TraceRecorder(ledger=ledger)
        for _ in range(10):safe_record(trace,'probe',data={'status':'OK'})
        snapshot=trace.snapshot();self.assertFalse(snapshot['complete'])
        self.assertEqual(ledger.snapshot()['categories']['trace']['live_bytes'],snapshot['recorded_bytes'])
        trace.close();self.assertEqual(ledger.snapshot()['live_entries'],0)
        self.assertGreater(len(snapshot['events']),0)


@unittest.skipUnless(shutil.which('gcc'),'C compiler required')
class ResourceRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from inference_ref.static_backend import build_static,CStaticRuntimeBackend
        from inference_ref.c_execution import CStaticBackend
        from inference_ref.c_backend import CBackend
        cls.tmp=tempfile.TemporaryDirectory(dir=ROOT/'build');cls.root=Path(cls.tmp.name)
        cls.build=build_static(cls.root/'build')
        cls.backends=[CStaticBackend(CBackend(Path(cls.build['library']))),CStaticRuntimeBackend(cls.build['library'])]
        write_package(cls.root/'model',**chain_definition('int32'))
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()

    def test_shared_weight_arena_metadata_and_trace_lifetimes(self):
        from inference_ref.resources import ResourceLedger
        from inference_ref.platform import PCPlatform
        from inference_ref.tracing import TraceRecorder
        from inference_ref.runtime import load_model,create_session
        for backend in self.backends:
            with self.subTest(backend=backend.backend_id):
                ledger=ResourceLedger();platform=PCPlatform(ledger=ledger);trace=TraceRecorder(ledger=ledger)
                model=load_model(self.root/'model',platform=platform,trace=trace)
                base=ledger.snapshot()['categories']['arena']['live_bytes']
                one=create_session(model,backend);two=create_session(model,backend)
                cats=ledger.snapshot()['categories'];self.assertGreater(cats['c_metadata']['live_bytes'],0);self.assertGreater(cats['c_profiles']['live_bytes'],0)
                expected=base+2*(model.plan.activation_bytes+model.plan.workspace_bytes+2*(model.plan.alignment-1))
                self.assertEqual(cats['arena']['live_bytes'],expected)
                addresses=one.memory_info()
                for i in range(50):np.testing.assert_array_equal(one.run({'x':np.array([2,-3,4],np.int32)})['y'],[20,-25])
                self.assertEqual(one.memory_info(),addresses)
                one.close();two.close();model.close()
                cats=ledger.snapshot()['categories']
                for category in ('arena','c_metadata','c_profiles','session_records'):self.assertEqual(cats[category]['live_bytes']+cats[category]['live_count'],0)
                self.assertGreater(cats['trace']['live_bytes'],0);trace.close();self.assertEqual(ledger.snapshot()['live_entries'],0)

    def test_metadata_refusal_rolls_back_and_profile_refusal_is_observational(self):
        from inference_ref.resources import ResourceLedger
        from inference_ref.platform import PCPlatform
        from inference_ref.tracing import TraceRecorder
        from inference_ref.runtime import load_model,create_session
        for backend in self.backends:
            for category in ('c_metadata','c_profiles'):
                with self.subTest(backend=backend.backend_id,category=category):
                    ledger=ResourceLedger(byte_limits={category:0});platform=PCPlatform(ledger=ledger);trace=TraceRecorder(ledger=ledger)
                    model=load_model(self.root/'model',platform=platform,trace=trace)
                    before=ledger.snapshot()['categories']['arena']['live_bytes']
                    if category=='c_metadata':
                        with self.assertRaises(ContractError):create_session(model,backend)
                        self.assertEqual(ledger.snapshot()['categories']['arena']['live_bytes'],before)
                    else:
                        with create_session(model,backend) as session:
                            np.testing.assert_array_equal(session.run({'x':np.array([2,-3,4],np.int32)})['y'],[20,-25])
                        self.assertFalse(trace.snapshot()['complete'])
                    model.close();trace.close();self.assertEqual(ledger.snapshot()['live_entries'],0)

    def test_task_budget_failure_and_event_history_bound(self):
        from inference_ref.resources import ResourceLedger
        from inference_ref.platform import PCPlatform
        from inference_ref.runtime import load_model
        from inference_ref.sim_device import SimDevice,SimConfig
        import inference_ref.sim_device as sim
        ledger=ResourceLedger(count_limits={'task_records':1});platform=PCPlatform(ledger=ledger)
        model=load_model(self.root/'model',platform=platform)
        device=SimDevice(self.backends[1],platform=platform,config=SimConfig(max_task_events=8))
        session=device.create_session(model);second=device.create_session(model);feeds={'x':np.array([2,-3,4],np.int32)}
        baseline=ledger.snapshot()['live_bytes']
        with mock.patch.object(sim,'_copy_feeds',side_effect=MemoryError('snapshot')):
            with self.assertRaises(ContractError):session.submit(feeds)
        self.assertEqual(ledger.snapshot()['live_bytes'],baseline)
        handle=session.submit(feeds,fault='lost_completion')
        with self.assertRaises(ContractError):second.submit(feeds)
        device.wait(handle,timeout_ticks=10)
        before=ledger.snapshot()['categories']['task_staging']['live_bytes'];self.assertEqual(before,20)
        with self.assertRaises(ContractError):device.release(handle)
        self.assertEqual(ledger.snapshot()['categories']['task_staging']['live_bytes'],20)
        device.recover(handle);device.wait(handle,timeout_ticks=10);device.release(handle)
        self.assertEqual(ledger.snapshot()['categories']['task_staging']['live_bytes'],0)
        for _ in range(40):
            handle=session.submit(feeds);device.wait(handle,timeout_ticks=10)
            self.assertLessEqual(len(device.events(handle)),8)
            device.release(handle)
        second.close();session.close();device.close();model.close()
        self.assertEqual(ledger.snapshot()['live_entries'],0)

    def test_unknown_device_graph_survives_gc_and_recovery_history_is_bounded(self):
        from inference_ref.resources import ResourceLedger
        from inference_ref.platform import PCPlatform,PCSynchronizer,retained_resources
        from inference_ref.runtime import load_model
        from inference_ref.sim_device import SimDevice,SimConfig
        class Sync(PCSynchronizer):
            allow=False
            def for_cpu(self,blocks):raise RuntimeError('sync unknown')
            def recover(self):return self.allow
        sync=Sync();ledger=ResourceLedger();platform=PCPlatform(ledger=ledger,synchronizer=sync)
        model=load_model(self.root/'model',platform=platform)
        device=SimDevice(self.backends[1],platform=platform,config=SimConfig(max_task_events=4))
        session=device.create_session(model);handle=session.submit({'x':np.array([2,-3,4],np.int32)})
        device.wait(handle,timeout_ticks=10)
        for _ in range(20):device.recover(handle);device.wait(handle,timeout_ticks=10)
        self.assertLessEqual(len(device.events(handle)),4)
        del device,session,model;gc.collect()
        self.assertEqual(ledger.snapshot()['categories']['task_staging']['live_bytes'],20)
        owners=[r.owner for r in retained_resources(platform.platform_id) if isinstance(r.owner,SimDevice)]
        self.assertEqual(len(owners),1)
        device=owners.pop();self.assertGreater(device.resource_info()['dropped_task_events'],0)
        sync.allow=True;device.recover(handle);device.wait(handle,timeout_ticks=10)
        session=device._tasks[handle.task_id].session;model=session._session._model
        device.release(handle);session.close();device.close();model.close()
        self.assertEqual(len(retained_resources(platform.platform_id)),0);self.assertEqual(ledger.snapshot()['live_entries'],0)

    def test_native_metadata_each_allocation_failure_and_normal_gc(self):
        from inference_ref.resources import ResourceLedger,ResourceGroup
        from inference_ref.platform import PCPlatform
        from inference_ref.runtime import load_model,create_session
        for backend in self.backends:
            for stop in range(1,7):
                ledger=ResourceLedger();platform=PCPlatform(ledger=ledger);model=load_model(self.root/'model',platform=platform)
                base=ledger.snapshot()['live_bytes'];original=ResourceGroup._create;calls=[0]
                def create(group,factory):
                    calls[0]+=1
                    if calls[0]==stop:raise MemoryError('native metadata fault')
                    return original(group,factory)
                with mock.patch.object(ResourceGroup,'_create',create):
                    try:session=create_session(model,backend)
                    except ContractError as exc:self.assertEqual(exc.code,'RESOURCE_LIMIT')
                    else:session.close()
                self.assertEqual(ledger.snapshot()['live_bytes'],base)
                session=create_session(model,backend);del session;gc.collect()
                self.assertEqual(ledger.snapshot()['live_bytes'],base)
                model.close();self.assertEqual(ledger.snapshot()['live_entries'],0)

    def test_verify_resources_cli_and_exclusive_output(self):
        with tempfile.TemporaryDirectory(dir=self.root) as tmp:
            output=Path(tmp)/'validation'
            command=[sys.executable,'-B','-m','inference_ref','verify-resources','--fixtures',str(ROOT/'fixtures/synthetic-v1'),
                '--output',str(output),'--iterations','2']
            run=subprocess.run(command,cwd=ROOT,capture_output=True,text=True,timeout=120)
            self.assertEqual(run.returncode,0,run.stdout+run.stderr)
            report=json.loads((output/'report.json').read_text());self.assertTrue(report['passed']);self.assertEqual(report['case_count'],54)
            self.assertTrue(all(p['passed'] for p in report['stress_probes']))
            self.assertEqual(subprocess.run(command,cwd=ROOT,capture_output=True).returncode,2)

    def test_no_unbudgeted_temporary_native_struct_constructors(self):
        from inference_ref.resources import ResourceLedger
        from inference_ref.platform import PCPlatform
        from inference_ref.runtime import load_model,create_session
        from inference_ref.c_backend import CCall,CTensor
        for kind in (CCall,CTensor):
            with self.subTest(kind=kind.__name__):
                original=kind.__init__
                def audited(obj,*args,**kwargs):
                    if args or kwargs:raise AssertionError('Unbudgeted temporary native structure/shape initializer')
                    original(obj)
                ledger=ResourceLedger();platform=PCPlatform(ledger=ledger);model=load_model(self.root/'model',platform=platform)
                try:
                    with mock.patch.object(kind,'__init__',audited):
                        with create_session(model,self.backends[0]) as session:
                            np.testing.assert_array_equal(session.run({'x':np.array([2,-3,4],np.int32)})['y'],[20,-25])
                finally:model.close()
                self.assertEqual(ledger.snapshot()['live_entries'],0)

    def test_optional_profiles_do_not_take_mandatory_prepare_budget(self):
        from inference_ref.resources import ResourceLedger
        from inference_ref.platform import PCPlatform
        from inference_ref.tracing import TraceRecorder
        from inference_ref.runtime import load_model,create_session
        for backend in self.backends:
            with self.subTest(backend=backend.backend_id):
                measure=ResourceLedger();platform=PCPlatform(ledger=measure);model=load_model(self.root/'model',platform=platform)
                session=create_session(model,backend);minimum=measure.snapshot()['peak_bytes'];session.close();model.close()
                ledger=ResourceLedger(budget_bytes=minimum);platform=PCPlatform(ledger=ledger);trace=TraceRecorder()
                model=load_model(self.root/'model',platform=platform,trace=trace)
                try:
                    with create_session(model,backend) as session:
                        np.testing.assert_array_equal(session.run({'x':np.array([2,-3,4],np.int32)})['y'],[20,-25])
                        self.assertFalse(session._binding.profiled)
                    self.assertFalse(trace.snapshot()['complete'])
                finally:model.close();trace.close()
                self.assertEqual(ledger.snapshot()['live_entries'],0)


if __name__=='__main__':unittest.main()
