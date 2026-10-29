"""S2 acceptance. A deliberate capability rejection exercises explicit selection, not hardware."""

from dataclasses import replace
import hashlib
import json
from pathlib import Path

from . import oracle,reference
from .backend import BackendPolicy,BackendRegistry,SupportReport
from .c_execution import CStaticBackend
from .c_backend import CBackend,ROOT,_new_directory,build_backend
from .compare import compare_arrays
from .contracts import ContractError,require
from .fixtures import read_fixture
from .package_validation import _hash_tree,package_fixture
from .reporting import write_json_exclusive
from .runtime import load_model
from .sim_device import SimDevice
from .suite import verify_suite
from .trace_validation import _execute,run_trace_validation
from .tracing import TraceRecorder,read_export,validate_trace,_encode


class _CapabilityDenied(CStaticBackend):
    """Validation-only rejected candidate; prepare must never be invoked."""
    def query(self,requirements):
        report=super().query(requirements)
        return SupportReport(self.backend_id,False,tuple(replace(n,supported=False,
            reason='acceptance deliberately unsupported; not a hardware backend') for n in report.nodes))

    def prepare(self,*args,**kwargs):
        raise AssertionError('Unsupported acceptance backend reached prepare')


def run_backend_validation(root,output,compiler=None):
    root,output=Path(root).resolve(),Path(output).resolve()
    require(not output.is_relative_to(root),'INVALID_ARGUMENT','Output must be outside fixture tree')
    before,baseline=_hash_tree(root),verify_suite(root)
    directory=_new_directory(output)
    raw=CBackend(build_backend(directory/'backend',compiler))
    recorder=TraceRecorder()
    registry=BackendRegistry([_CapabilityDenied(raw,backend_id='test_denied'),CStaticBackend(raw)])
    policy=BackendPolicy('test_denied',True,('pc_c',))
    direct=SimDevice(raw,trace=recorder)
    fallback=SimDevice(registry=registry,policy=policy,trace=recorder)
    results=[]
    for checked in baseline['cases']:
        name=checked['case_id']
        if not checked['passed']:
            results.append({'case_id':name,'passed':False,'python_validation':checked})
            continue
        try:
            fixture=read_fixture(root/name)
            path=directory/'packages'/name
            feeds=package_fixture(path,fixture)
            model=load_model(path,trace=recorder)
            expected=_execute(direct,model,feeds)
            actual=_execute(fallback,model,feeds)
            toggle=expected.dtype==actual.dtype and expected.shape==actual.shape and expected.tobytes()==actual.tobytes()
            op=fixture.metadata['operation']['name']; p=fixture.metadata['comparison']
            comparisons={key:compare_arrays(value,actual,p['atol'],p['rtol']) for key,value in (
                ('stored_vs_selected',fixture.expected),('scalar_vs_selected',reference.execute(op,fixture.inputs)),
                ('numpy_vs_selected',oracle.execute(op,fixture.inputs)))}
            results.append({'case_id':name,'passed':toggle and all(c['passed'] for c in comparisons.values()),
                            'direct_vs_fallback_bitwise_equal':toggle,'comparisons':comparisons})
        except ContractError as exc: results.append({'case_id':name,'passed':False,'error':{'code':exc.code,'message':str(exc)}})
    stats={'direct':direct.stats(),'fallback':fallback.stats()}
    direct.close(); fallback.close()
    exported=recorder.export(directory/'trace')
    trace=read_export(directory/'trace')
    negatives={}
    for name in ('wrong_backend','missing_session_backend'):
        damaged=json.loads(json.dumps(trace['trace']))
        if name=='missing_session_backend':
            next(e for e in damaged['events'] if e['kind']=='session.open')['data'].pop('selected_backend')
        next(e for e in damaged['events'] if e['kind']=='c.chain')['data']['selected_backend']='wrong_backend'
        damaged['recorded_bytes']=sum(len(_encode(e)) for e in damaged['events'])
        negatives[name]=validate_trace(damaged)
    selections=[e['data'] for e in trace['trace']['events'] if e['kind']=='backend.selection']
    fallback_count=sum(e['used_fallback'] for e in selections)
    fixed_backend=all(e['selected_backend']=='pc_c' and e['execution']=='pc_c_backend' for e in selections)
    # Re-run original model/memory/device/tracing scenarios on the extracted C binding.
    runtime_trace=run_trace_validation(root,directory/'runtime_trace',compiler)
    unchanged=before==_hash_tree(root)
    count=sum(c['passed'] for c in results)
    files=sorted((ROOT/'inference_ref').glob('*.py'))
    report={'format':'inference-backend-report','version':1,'scope':'phase1a_s2','source':'static_backend_selection',
        'execution':'pc_c_backend','passed':count==len(results) and baseline['passed'] and trace['validation']['passed'] and
            runtime_trace['passed'] and unchanged and fallback_count==len(results) and fixed_backend and
            all(not c['passed'] for c in negatives.values()) and
            all(s['live_tasks']==s['live_sessions']==s['staging_reserved_bytes']==0 for s in stats.values()),
        'case_count':len(results),'passed_count':count,'cases':results,'explicit_fallback_count':fallback_count,
        'actual_backend':'pc_c','candidate_note':'test_denied is validation-only; both numerical paths use actual PC C',
        'trace_validation':trace['validation'],'trace_export':exported,'summary':trace['summary'],
        'selection_negative_controls':negatives,
        'runtime_trace_report':'runtime_trace/report.json','runtime_trace_passed':runtime_trace['passed'],
        'final_device_stats':stats,'fixture_files_unchanged':unchanged,'fixture_files_before_sha256':before,
        'environment':baseline['environment'],'build':raw.build,'source_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in files}}
    write_json_exclusive(directory/'report.json',report)
    return report
