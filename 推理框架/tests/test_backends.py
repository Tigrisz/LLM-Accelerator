import importlib
import os
from pathlib import Path
import shutil
import unittest
from dataclasses import replace

import numpy as np

from inference_ref.c_backend import CBackend,CCall,build_backend
from inference_ref.contracts import ContractError
from inference_ref.model_package import write_package
from inference_ref.runtime import load_model,create_session
from inference_ref.sim_device import SimDevice
from inference_ref.tracing import TraceRecorder,validate_trace
from tests.package_support import chain_definition
from tests.support import Workspace

try:
    api=importlib.import_module('inference_ref.backend')
    native=importlib.import_module('inference_ref.c_execution')
except ModuleNotFoundError:
    api=native=None


class BackendTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not any(shutil.which(c) for c in ('cc','gcc','clang')):
            if os.environ.get('IR_REQUIRE_C')=='1': raise RuntimeError('C compiler required')
            raise unittest.SkipTest('Use WSL with C compiler')
        cls.work=Workspace(); cls.addClassCleanup(cls.work.cleanup)
        cls.raw=CBackend(build_backend(Path(cls.work.name)/'backend'))
        cls.path=Path(cls.work.name)/'model'; write_package(cls.path,**chain_definition())

    def setUp(self):
        self.assertIsNotNone(api,'S2 backend API missing')
        self.model=load_model(self.path)

    def limited(self,**kwargs):
        class Limited(native.CStaticBackend):
            def query(self,requirements):
                report=super().query(requirements)
                rows=tuple(replace(n,supported=False,reason='test: relu unsupported') if requirements.nodes[n.index].op=='relu' else n for n in report.nodes)
                return api.SupportReport(self.backend_id,all(n.supported for n in rows),rows)
        return Limited(self.raw,backend_id=kwargs.get('backend_id','limited'))

    def test_capability_query_contains_node_reason_and_all_requirements(self):
        req=api.requirements_for(self.model.package,self.model.plan)
        self.assertEqual(req.nodes[0].inputs[0][1].memory_domain,'host')
        report=self.limited().query(req)
        self.assertFalse(report.supported)
        self.assertEqual(report.nodes[1].node_id,'n1')
        self.assertIn('relu',report.nodes[1].reason)
        self.assertEqual(req.nodes[0].attributes,())
        self.assertGreaterEqual(req.workspace_bytes,8)

    def test_explicit_fallback_and_disabled_fallback_are_distinct(self):
        registry=api.BackendRegistry([self.limited(),native.CStaticBackend(self.raw)])
        req=api.requirements_for(self.model.package,self.model.plan)
        denied=registry.select(req,api.BackendPolicy('limited',fallbacks=('pc_c',)))
        self.assertFalse(denied.supported)
        self.assertEqual(len(denied.attempts),1)
        selected=registry.select(req,api.BackendPolicy('limited',allow_fallback=True,fallbacks=('pc_c',)))
        self.assertTrue(selected.used_fallback)
        self.assertEqual(selected.backend.backend_id,'pc_c')
        self.assertEqual([r.backend_id for r in selected.attempts],['limited','pc_c'])

    def test_unsupported_domains_layout_dtype_attributes_and_shape_are_reported(self):
        backend=native.CStaticBackend(self.raw)
        req=api.requirements_for(self.model.package,self.model.plan)
        node=req.nodes[0]; name,tensor=node.inputs[0]
        for changed,keyword in ((replace(tensor,memory_domain='device'),'domain'),
                                (replace(tensor,layout='column_major'),'layout'),
                                (replace(tensor,dtype='int8'),'dtype'),
                                (replace(tensor,shape=(2,4)),'shape')):
            with self.subTest(keyword=keyword):
                altered=replace(node,inputs=((name,changed),)+node.inputs[1:])
                report=backend.query(replace(req,nodes=(altered,)+req.nodes[1:]))
                self.assertFalse(report.supported)
                self.assertIn(keyword,report.nodes[0].reason)
        report=backend.query(replace(req,nodes=(replace(node,attributes=(('transpose',True),)),)+req.nodes[1:]))
        self.assertFalse(report.supported)
        self.assertIn('attributes',report.nodes[0].reason)

    def test_bad_policy_or_query_does_not_silently_fallback(self):
        registry=api.BackendRegistry([native.CStaticBackend(self.raw)])
        req=api.requirements_for(self.model.package,self.model.plan)
        for policy in (api.BackendPolicy('missing'),api.BackendPolicy('pc_c',allow_fallback=True,fallbacks=('missing',))):
            with self.assertRaises(ContractError): registry.select(req,policy)
        class Broken(native.CStaticBackend):
            def query(self,requirements): return api.SupportReport(self.backend_id,True,())
        registry=api.BackendRegistry([Broken(self.raw,backend_id='broken'),native.CStaticBackend(self.raw)])
        with self.assertRaises(ContractError): registry.select(req,api.BackendPolicy('broken',True,('pc_c',)))

    def test_session_fallback_uses_existing_plan_c_and_tracing(self):
        trace=TraceRecorder(); model=load_model(self.path,trace=trace)
        registry=api.BackendRegistry([self.limited(),native.CStaticBackend(self.raw)])
        with create_session(model,registry=registry,policy=api.BackendPolicy('limited',True,('pc_c',))) as session:
            result=session.run({'x':np.array([2,-3,4],np.int32)})
            np.testing.assert_array_equal(result['y'],[20,-25])
            self.assertEqual(session.selection.backend.backend_id,'pc_c')
            self.assertEqual(session.memory_info()['total_backing_bytes'],model.plan.total_bytes)
        document=trace.snapshot()
        event=next(e for e in document['events'] if e['kind']=='backend.selection')
        self.assertTrue(event['data']['used_fallback'])
        self.assertEqual(event['data']['selected_backend'],'pc_c')
        tracing_result=validate_trace(document)
        self.assertTrue(tracing_result['passed'],tracing_result)

    def test_device_rejection_has_no_session_or_task_and_query_explains_reason(self):
        device=SimDevice(self.limited())
        report=device.query_support(self.model)
        self.assertFalse(report['supported'])
        self.assertIn('relu',report['attempts'][0]['nodes'][1]['reason'])
        with self.assertRaises(ContractError): device.create_session(self.model)
        self.assertEqual(device.stats()['live_sessions'],0)
        self.assertEqual(device.stats()['live_tasks'],0)
        self.assertEqual(device.stats()['staging_reserved_bytes'],0)
        device.close()

    def test_numeric_failure_does_not_invoke_fallback_or_change_lease(self):
        class NeverQuery(native.CStaticBackend):
            def query(self,requirements): raise AssertionError('Fallback queried after supported preferred')
        registry=api.BackendRegistry([native.CStaticBackend(self.raw),NeverQuery(self.raw,backend_id='unused')])
        device=SimDevice(registry=registry,policy=api.BackendPolicy('pc_c',True,('unused',)))
        session=device.create_session(self.model)
        for values,completed in (([2**30,0,0],0),([0,1000000000,1000000000],3)):
            handle=session.submit({'x':np.array(values,np.int32)})
            done=device.wait(handle,timeout_ticks=10).task
            self.assertEqual(done.status,'NUMERIC_OVERFLOW')
            self.assertEqual(done.completed_steps,completed)
            with self.assertRaises(ContractError): session.close()
            device.release(handle)
        device.close()

    def test_non_c_backend_executes_entire_chain_and_has_distinct_trace_domain(self):
        class ArrayChain(api.BoundChain):
            profiled=True
            def __init__(self,package,views): self.package,self.views=package,views
            def execute(self):
                for node in self.package.nodes:
                    b=dict(node.inputs)
                    if node.op=='linear':
                        value=self.views[b['weight']]@self.views[b['input']]
                        if 'bias' in b: value=value+self.views[b['bias']]
                    elif node.op=='add': value=self.views[b['a']]+self.views[b['b']]
                    else: value=np.maximum(self.views[b['input']],0)
                    self.views[node.output][:]=value
                return api.ChainResult('OK',len(self.package.nodes))
            def observe_nodes(self):
                return tuple({'index':i,'node_id':n.id,'op':n.op,'dtype':self.package.tensor(n.output).spec.dtype,
                    'executed':True,'status':'OK','clock':'unavailable','timing_valid':False,'ticks_per_second':None,
                    'start_ticks':None,'end_ticks':None,'cpu_duration_ns':None} for i,n in enumerate(self.package.nodes))
            def close(self): self.package=self.views=None
        class ArrayBackend(api.StaticBackend):
            backend_id='test_array'
            execution_kind='test_numpy_chain'
            def query(self,requirements):
                return api.SupportReport(self.backend_id,True,tuple(api.NodeSupport(n.index,n.node_id,True,'',0) for n in requirements.nodes))
            def prepare(self,package,plan,views,workspace,*,profile=False): return ArrayChain(package,views)
        recorder=TraceRecorder(); model=load_model(self.path,trace=recorder)
        with create_session(model,ArrayBackend()) as session:
            np.testing.assert_array_equal(session.run({'x':np.array([2,-3,4],np.int32)})['y'],[20,-25])
        document=recorder.snapshot(); kinds={e['kind'] for e in document['events']}
        self.assertIn('backend.chain',kinds)
        self.assertNotIn('c.chain',kinds)
        result=validate_trace(document)
        self.assertTrue(result['passed'],result)

    def test_unknown_execution_exception_or_malformed_success_quarantines_without_fallback(self):
        for malformed in (False,True):
            class FailingChain(api.BoundChain):
                def execute(self):
                    if malformed: return api.ChainResult('OK',0)
                    raise ContractError('DEVICE_ERROR','backend failed without quiescence confirmation')
                def close(self): pass
                def recover(self): return True  # Explicit test-backend quiescence acknowledgement.
            class Failing(native.CStaticBackend):
                def prepare(self,*args,**kwargs): return FailingChain()
            registry=api.BackendRegistry([Failing(self.raw,backend_id='bad'),native.CStaticBackend(self.raw)])
            device=SimDevice(registry=registry,policy=api.BackendPolicy('bad',True,('pc_c',)))
            session=device.create_session(self.model)
            handle=session.submit({'x':np.zeros(3,np.int32)})
            result=device.wait(handle,timeout_ticks=10)
            self.assertEqual(result.wait_status,'DEVICE_ERROR')
            self.assertEqual(result.task.state,'QUARANTINED')
            self.assertEqual(result.task.execution_status,'DEVICE_ERROR')
            self.assertFalse(result.task.quiescent)
            with self.assertRaises(ContractError): device.release(handle)
            device.recover(handle); device.wait(handle,timeout_ticks=10); device.release(handle); device.close()

    def test_prepare_exception_is_not_an_unsupported_fallback(self):
        class Failing(native.CStaticBackend):
            def prepare(self,*args,**kwargs): raise ContractError('RESOURCE_LIMIT','prepare allocation probe')
        registry=api.BackendRegistry([Failing(self.raw,backend_id='bad'),native.CStaticBackend(self.raw)])
        device=SimDevice(registry=registry,policy=api.BackendPolicy('bad',True,('pc_c',)))
        with self.assertRaises(ContractError) as caught: device.create_session(self.model)
        self.assertEqual(caught.exception.code,'RESOURCE_LIMIT')
        self.assertEqual(device.stats()['live_sessions'],0)
        device.close()

    def test_trace_rejects_changed_selected_backend(self):
        import json
        from inference_ref.tracing import _encode
        recorder=TraceRecorder(); model=load_model(self.path,trace=recorder)
        with create_session(model,self.raw) as session: session.run({'x':np.zeros(3,np.int32)})
        document=recorder.snapshot()
        row=next(e for e in document['events'] if e['kind']=='c.chain')
        row['data']['selected_backend']='unselected'
        document['recorded_bytes']=sum(len(_encode(e)) for e in document['events'])
        self.assertFalse(validate_trace(document)['passed'])

    def test_unsupported_query_does_not_allocate_session_arenas(self):
        from unittest import mock
        import inference_ref.runtime as runtime
        with mock.patch.object(runtime,'Arena',side_effect=AssertionError('Rejected selection allocated an arena')):
            with self.assertRaises(ContractError) as caught: create_session(self.model,self.limited())
        self.assertEqual(caught.exception.code,'UNSUPPORTED')

    def test_query_exception_does_not_try_next_backend(self):
        class Broken(native.CStaticBackend):
            def query(self,requirements): raise RuntimeError('query failed, not unsupported')
        registry=api.BackendRegistry([Broken(self.raw,backend_id='broken'),native.CStaticBackend(self.raw)])
        with self.assertRaises(RuntimeError): registry.select(api.requirements_for(self.model.package,self.model.plan),api.BackendPolicy('broken',True,('pc_c',)))

    def test_backend_acceptance_cli(self):
        import json,subprocess,sys
        work=Workspace(); self.addCleanup(work.cleanup)
        output=Path(work.name)/'acceptance'
        args=[sys.executable,'-B','-m','inference_ref','verify-backends','--fixtures',str(Path(__file__).resolve().parents[1]/'fixtures/synthetic-v1'),'--output',str(output)]
        run=subprocess.run(args,capture_output=True,text=True,timeout=120)
        self.assertEqual(run.returncode,0,run.stderr)
        report=json.loads((output/'report.json').read_text())
        self.assertTrue(report['passed'])
        self.assertEqual(report['passed_count'],54)
        self.assertEqual(report['explicit_fallback_count'],54)
        self.assertEqual(report['trace_validation']['passed'],True)
        self.assertEqual(len(report.get('selection_negative_controls',{})),2)
        self.assertTrue(all(not c['passed'] for c in report['selection_negative_controls'].values()))
        self.assertEqual(subprocess.run(args,capture_output=True).returncode,2)

    def test_unknown_direct_session_blocks_reuse_and_close_until_backend_ack(self):
        class Once(api.BoundChain):
            def __init__(self,inner): self.inner,self.first=inner,True
            def execute(self):
                if self.first:
                    self.first=False
                    raise RuntimeError('unknown execution probe')
                return self.inner.execute()
            def recover(self): return True
            def close(self): self.inner.close()
        class Backend(native.CStaticBackend):
            def prepare(self,*args,**kwargs): return Once(super().prepare(*args,**kwargs))
        session=create_session(self.model,Backend(self.raw))
        with self.assertRaises(RuntimeError): session.run({'x':np.zeros(3,np.int32)})
        with self.assertRaises(ContractError): session.run({'x':np.zeros(3,np.int32)})
        with self.assertRaises(ContractError): session.close()
        session.recover()
        np.testing.assert_array_equal(session.run({'x':np.array([2,-3,4],np.int32)})['y'],[20,-25])
        session.close()

    def test_capability_rejects_readonly_output(self):
        req=api.requirements_for(self.model.package,self.model.plan)
        altered=replace(req.nodes[0],output=replace(req.nodes[0].output,read_only=True))
        report=native.CStaticBackend(self.raw).query(replace(req,nodes=(altered,)+req.nodes[1:]))
        self.assertFalse(report.supported)
        self.assertIn('permission',report.nodes[0].reason)

    def test_recovery_refusal_keeps_task_lease_until_backend_confirms(self):
        class Binding(api.BoundChain):
            acknowledged=False
            def execute(self): raise RuntimeError('unknown execution')
            def recover(self): return self.acknowledged
            def close(self): pass
        class Backend(native.CStaticBackend):
            def prepare(self,*args,**kwargs): return Binding()
        device=SimDevice(Backend(self.raw)); session=device.create_session(self.model)
        handle=session.submit({'x':np.zeros(3,np.int32)})
        device.wait(handle,timeout_ticks=10)
        reserved=device.stats()['staging_reserved_bytes']
        device.recover(handle)
        result=device.wait(handle,timeout_ticks=10)
        self.assertEqual(result.task.state,'QUARANTINED')
        self.assertEqual(device.stats()['staging_reserved_bytes'],reserved)
        with self.assertRaises(ContractError): device.release(handle)
        session._session._binding.acknowledged=True
        device.recover(handle); device.wait(handle,timeout_ticks=10); device.release(handle)
        self.assertEqual(device.stats()['staging_reserved_bytes'],0)
        device.close()

    def test_profile_observer_failure_does_not_fail_selected_execution(self):
        class Backend(native.CStaticBackend):
            def prepare(self,*args,**kwargs):
                binding=super().prepare(*args,**kwargs)
                def broken(): raise RuntimeError('profile observer failure')
                binding.observe_nodes=broken
                return binding
        recorder=TraceRecorder(); model=load_model(self.path,trace=recorder)
        device=SimDevice(Backend(self.raw),trace=recorder); session=device.create_session(model)
        handle=session.submit({'x':np.array([2,-3,4],np.int32)})
        self.assertEqual(device.wait(handle,timeout_ticks=10).task.state,'SUCCEEDED')
        np.testing.assert_array_equal(device.result(handle)['y'],[20,-25])
        device.release(handle); device.close()
        self.assertFalse(recorder.snapshot()['complete'])

    def test_generic_acknowledged_device_error_between_or_after_nodes_has_valid_trace(self):
        class LateBinding(api.BoundChain):
            profiled=True
            def __init__(self,inner): self.inner=inner
            def execute(self):
                original=self.inner.calls
                try:
                    self.inner.calls=(CCall*prefix)(*original[:prefix])
                    result=self.inner.execute()
                finally: self.inner.calls=original
                return api.ChainResult('DEVICE_ERROR',result.completed_steps)
            def observe_nodes(self):
                return tuple({**r,'clock':'unavailable','timing_valid':False,'ticks_per_second':None,
                              'start_ticks':None,'end_ticks':None,'cpu_duration_ns':None} for r in self.inner.observe_nodes())
            def close(self): self.inner.close()
        class Late(native.CStaticBackend):
            trace_kind='backend'
            execution_kind='test_acknowledged_late_error'
            def prepare(self,*args,**kwargs): return LateBinding(super().prepare(*args,**kwargs))
        for prefix in (2,4):
            with self.subTest(completed=prefix):
                trace=TraceRecorder(); model=load_model(self.path,trace=trace)
                with create_session(model,Late(self.raw)) as session:
                    with self.assertRaises(ContractError) as caught: session.run({'x':np.zeros(3,np.int32)})
                    self.assertEqual(caught.exception.code,'DEVICE_ERROR')
                    self.assertEqual(session.last_result['completed_steps'],prefix)
                checked=validate_trace(trace.snapshot())
                self.assertTrue(checked['passed'],checked)

    def test_missing_session_backend_field_cannot_bypass_identity_validation(self):
        from inference_ref.tracing import _encode
        trace=TraceRecorder(); model=load_model(self.path,trace=trace)
        with create_session(model,self.raw) as session: session.run({'x':np.zeros(3,np.int32)})
        doc=trace.snapshot()
        next(e for e in doc['events'] if e['kind']=='session.open')['data'].pop('selected_backend')
        next(e for e in doc['events'] if e['kind']=='c.chain')['data']['selected_backend']='wrong_backend'
        doc['recorded_bytes']=sum(len(_encode(e)) for e in doc['events'])
        self.assertFalse(validate_trace(doc)['passed'])
