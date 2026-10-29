"""T1 tooling tests are deliberately separate from the 174 runtime tests."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
import sys
import copy
import subprocess
import time
from unittest import mock


def good_reports():
    zero={'live_entries':0,'live_bytes':0,'resident_bytes':0}
    device={'live_tasks':0,'live_sessions':0,'staging_reserved_bytes':0}
    probes=[]
    for backend in ('pc_c','pc_c_static'):
        for dtype in ('int32','float32'):
            probes.append({'name':f'repeat_{backend}_{dtype}','passed':True,'backend':backend,'dtype':dtype,'iterations':200,
                'successful_tasks':600,'session_count':3,'stable_arena_addresses':True,'steady_state_plateau':True,
                'final_ledger':dict(zero),'final_device_stats':dict(device)})
        probes.append({'name':'allocation_sweep_'+backend,'passed':True,'backend':backend,'allocation_points':[
            {'fail_after':i,'status':'RESOURCE_LIMIT' if i<10 else 'OK','released':True} for i in range(20)]})
        probes.append({'name':'recover_close_'+backend,'passed':True,'recovery_refusals':50,'close_attempts':2,
            'unknown_graph_retained':True,'dropped_history_events':96,'final_ledger':dict(zero)})
        for category in ('arena','c_metadata','c_profiles','trace','task_staging','task_records','session_records','task_events'):
            probes.append({'name':f'budget_{backend}_{category}','passed':True,'category':category,'final_ledger':dict(zero)})
    execute=lambda n:{'exit_code':0,'node_count':n,'live_allocations':0,'trace_validation':{'passed':True},'command':['host','image','weights','input','output','trace']}
    resource={'passed':True,'case_count':54,'passed_count':54,'iterations':200,'stress_probes':probes}
    static={'passed':True,'case_count':54,'passed_count':54,
        'cases':[{'case_id':str(i),'passed':True,'adapter_bitwise_equal':True,'execution':execute(1),
            'comparisons':{k:{'passed':True} for k in ('stored','scalar','numpy')}} for i in range(54)],
        'chains':[{'dtype':d,'input':v,'passed':True,'execution':execute(4),'sanitized_execution':execute(4),
            'comparisons':{k:{'passed':True} for k in ('scalar','numpy','manual')}} for d in ('int32','float32') for v in ('normal','zero')],
        'native_tests':[{'path':'/fresh/'+n,'passed':True,'exit_code':0,'sanitize':s} for n in ('test_static','test_pc','test_resources') for s in (False,True)]}
    return resource,static

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools'))


class ReproduceTests(unittest.TestCase):
    def setUp(self):
        (ROOT/'build').mkdir(exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(dir=ROOT/'build');self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name)

    def test_snapshot_excludes_old_build_and_preserves_fixtures(self):
        from reproduce import snapshot_source,verify_manifest
        target=self.base/'source';manifest=snapshot_source(ROOT,target)
        self.assertFalse((target/'build').exists());self.assertFalse((target/'.git').exists())
        self.assertEqual(len([p for p in manifest if p.startswith('fixtures/synthetic-v1/')]),109)
        self.assertTrue(verify_manifest(target,manifest))
        (target/'requirements.txt').write_text('changed')
        self.assertFalse(verify_manifest(target,manifest))

    def test_manifest_detects_extra_managed_source(self):
        from reproduce import snapshot_source,verify_manifest
        target=self.base/'source';manifest=snapshot_source(ROOT,target)
        (target/'inference_ref/unexpected.py').write_text('unexpected = True')
        self.assertFalse(verify_manifest(target,manifest))

    def test_rejected_existing_acceptance_output_is_unchanged(self):
        target=self.base/'existing';target.mkdir();(target/'keep').write_text('keep')
        run=subprocess.run([sys.executable,'-B',str(ROOT/'tools/acceptance.py'),'--output',str(target)],capture_output=True,text=True)
        self.assertNotEqual(run.returncode,0)
        self.assertEqual(sorted(p.name for p in target.iterdir()),['keep'])

    def test_snapshot_rejects_existing_destination_and_managed_source_output(self):
        from reproduce import snapshot_source,validate_output
        target=self.base/'existing';target.mkdir();(target/'keep').write_text('keep')
        with self.assertRaises(Exception):snapshot_source(ROOT,target)
        self.assertEqual((target/'keep').read_text(),'keep')
        for p in (ROOT,ROOT/'tests/new_output',ROOT/'fixtures/output',ROOT.parent):
            with self.subTest(path=p),self.assertRaises(Exception):validate_output(ROOT,p)

    def test_source_symlink_rejected(self):
        from reproduce import snapshot_source
        source=self.base/'source';source.mkdir()
        for name in ('README.md','requirements.txt','.gitignore'):(source/name).write_text('x')
        (source/'inference_ref').mkdir()
        try:(source/'inference_ref/link.py').symlink_to(ROOT/'inference_ref/__init__.py')
        except (OSError,NotImplementedError):self.skipTest('Symlink unavailable')
        with self.assertRaises(Exception):snapshot_source(source,self.base/'target')

    def test_required_tools_not_silently_optional(self):
        from reproduce import preflight
        with self.assertRaises(Exception):preflight(which=lambda _:None)

    def test_test_result_gate_rejects_skips_missing_ids_and_failure(self):
        from run_tests import result_passes
        good={'successful':True,'tests_run':2,'skipped':0,'failures':0,'errors':0,'test_ids':['a','b']}
        self.assertTrue(result_passes(good,['a','b']))
        for key,value in [('skipped',1),('failures',1),('errors',1),('tests_run',0),('test_ids',['a'])]:
            with self.subTest(key=key):self.assertFalse(result_passes({**good,key:value},['a','b']))

    def test_report_gate_rejects_failed_or_incomplete_resources(self):
        from acceptance import validate_resources
        with self.assertRaises(Exception):validate_resources({'passed':True},{})
        with self.assertRaises(Exception):validate_resources({'passed':False,'case_count':54,'passed_count':54},{'passed':True})

    def test_report_gate_checks_individual_comparisons_and_native_identities(self):
        from acceptance import validate_resources
        resource,static=good_reports()
        self.assertEqual(validate_resources(resource,static)['cases'],54)
        for modify in (lambda s:s['cases'][0]['comparisons']['stored'].update(passed=False),
                       lambda s:s['native_tests'][0].update(path=s['native_tests'][2]['path']),
                       lambda s:s['chains'].append(dict(s['chains'][0]))):
            broken=copy.deepcopy(static);modify(broken)
            with self.subTest(modify=modify),self.assertRaises(Exception):validate_resources(resource,broken)

    def test_pressure_and_execution_evidence_cannot_be_omitted(self):
        from acceptance import validate_resources
        for mutate in (lambda r,s:r.update(iterations=0),
            lambda r,s:r.update(stress_probes=[{'name':str(i),'passed':True} for i in range(24)]),
            lambda r,s:r['stress_probes'][0].update(successful_tasks=0),
            lambda r,s:s['cases'][0].pop('execution'),
            lambda r,s:s['chains'][0].pop('sanitized_execution'),
            lambda r,s:s['chains'][0]['execution'].update(node_count=0),
            lambda r,s:s['chains'][0].pop('comparisons')):
            resource,static=good_reports();mutate(resource,static)
            with self.subTest(mutate=mutate),self.assertRaises(Exception):validate_resources(resource,static)

    def test_environment_drops_build_overrides_and_pins_sanitizer(self):
        from reproduce import clean_environment
        overrides={k:'unsafe' for k in ('CPATH','LIBRARY_PATH','GCC_EXEC_PREFIX','LD_AUDIT','PYTHONPATH','C_INCLUDE_PATH')}
        with mock.patch.dict('os.environ',{**overrides,'ASAN_OPTIONS':'detect_leaks=0','UBSAN_OPTIONS':'halt_on_error=0'}):
            env=clean_environment()
        self.assertFalse(set(overrides)&set(env))
        self.assertIn('detect_leaks=1',env['ASAN_OPTIONS']);self.assertIn('halt_on_error=1',env['UBSAN_OPTIONS'])

    def test_exit_zero_with_sanitizer_diagnostic_is_rejected(self):
        from acceptance import validate_execution
        directory=self.base/'sanitized';directory.mkdir()
        trace=directory/'trace.json';trace.write_text('{}')
        (directory/'stderr.log').write_text('runtime error: signed integer overflow\n')
        (directory/'stdout.log').write_text('{"status":0,"trace_complete":true,"live_allocations":0}')
        execution={'exit_code':0,'node_count':4,'live_allocations':0,'trace_validation':{'passed':True},
            'command':[str(directory/'host'),'image','weights','input','output',str(trace)]}
        with self.assertRaisesRegex(Exception,'stderr|diagnostic'):validate_execution(execution,4,self.base)

    def test_real_recovering_ubsan_diagnostic_cannot_pass(self):
        from reproduce import clean_environment
        from acceptance import validate_execution
        source=self.base/'overflow.c';binary=self.base/'overflow'
        source.write_text('#include <limits.h>\nint main(void){volatile int x=INT_MAX;volatile int y=x+1;return y==0;}\n')
        compiled=subprocess.run(['gcc','-O1','-fsanitize=undefined',str(source),'-o',str(binary)],capture_output=True)
        self.assertEqual(compiled.returncode,0,compiled.stderr)
        env=clean_environment();env['UBSAN_OPTIONS']='halt_on_error=0'
        run=subprocess.run([str(binary)],env=env,capture_output=True,text=True)
        self.assertEqual(run.returncode,0);self.assertIn('runtime error:',run.stderr)
        (self.base/'stderr.log').write_text(run.stderr);(self.base/'stdout.log').write_text('{}')
        execution={'exit_code':0,'node_count':4,'live_allocations':0,'trace_validation':{'passed':True},
            'command':[str(binary),'image','weights','input','output',str(self.base/'trace.json')]}
        with self.assertRaisesRegex(Exception,'stderr|diagnostic'):validate_execution(execution,4,self.base)

    def test_timeout_stops_grandchild_writing_artifacts(self):
        from reproduce import run_command
        marker=self.base/'late.txt'
        grandchild="import time; from pathlib import Path; time.sleep(0.8); Path("+repr(str(marker))+").write_text('late')"
        parent="import subprocess,sys,time; subprocess.Popen([sys.executable,'-c',"+repr(grandchild)+"]); time.sleep(5)"
        with self.assertRaises(subprocess.TimeoutExpired):run_command([sys.executable,'-c',parent],timeout=0.3,cwd=ROOT)
        time.sleep(1.0);self.assertFalse(marker.exists())


if __name__=='__main__':unittest.main()
