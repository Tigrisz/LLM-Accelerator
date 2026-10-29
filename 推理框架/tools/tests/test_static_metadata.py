"""T3 real native contracts; separate from the frozen original 174 tests."""
import ctypes as ct
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'tools'))
from inference_ref.c_backend import FLAGS


class StaticMetadataTests(unittest.TestCase):
    def run_native(self,sanitize):
        self.assertTrue(shutil.which('gcc'),'gcc is mandatory; no skipped T3 checks')
        with tempfile.TemporaryDirectory() as tmp:
            binary=Path(tmp)/'metadata'
            flags=['-fsanitize=address,undefined','-fno-omit-frame-pointer','-fno-pie','-no-pie'] if sanitize else []
            command=['gcc',*FLAGS,'-O1' if sanitize else '-O2',*flags,'-I',str(ROOT/'c/include'),str(ROOT/'c/tests/test_metadata.c'),
                *[str(ROOT/'c/src'/s) for s in ('ir_core.c','ir_static.c','ir_pc.c')],'-lm','-o',str(binary)]
            built=subprocess.run(command,capture_output=True,text=True,timeout=120)
            self.assertEqual(built.returncode,0,built.stderr)
            run=subprocess.run([str(binary)],capture_output=True,text=True,timeout=60)
            self.assertEqual(run.returncode,0,run.stdout+run.stderr);self.assertEqual(run.stderr,'')
            row=json.loads(run.stdout.splitlines()[-1]);self.assertTrue(row['passed']);self.assertLess(row['context_bytes'],1024)
            self.assertEqual((row['state_3'],row['inspect_3']),(3,12))

    def test_native_metadata_contract(self):self.run_native(False)
    def test_sanitized_metadata_contract(self):self.run_native(True)

    def test_reject_old_runtime_abi_before_binding(self):
        from inference_ref.static_backend import require_runtime_abi
        from inference_ref.contracts import ContractError
        class Legacy:pass
        class Wrong:
            def irs_runtime_abi_version(self):return 1
        with self.assertRaises(ContractError):require_runtime_abi(Legacy())
        with self.assertRaises(ContractError):require_runtime_abi(Wrong())

    def test_compiler_frames_and_size_queries(self):
        from audit_static_metadata import audit
        with tempfile.TemporaryDirectory() as tmp:
            report=audit(Path(tmp)/'audit')
            self.assertTrue(report['passed']);self.assertIsNone(report['target_stack_peak'])
            self.assertIsNone(report['target_layout'])

    def test_static_object_has_no_allocator_or_abi1_entrypoints(self):
        with tempfile.TemporaryDirectory() as tmp:
            obj=Path(tmp)/'static.o'
            run=subprocess.run(['gcc',*FLAGS,'-O2','-I',str(ROOT/'c/include'),'-c',str(ROOT/'c/src/ir_static.c'),'-o',str(obj)],capture_output=True,text=True,timeout=60)
            self.assertEqual(run.returncode,0,run.stderr)
            undefined=subprocess.check_output(['nm','-u',str(obj)],text=True)
            for symbol in ('malloc','calloc','realloc','free','alloca'):
                self.assertNotIn(symbol,undefined.split())
            defined=subprocess.check_output(['nm','--defined-only',str(obj)],text=True).split()
            self.assertIn('irs_bind_v2',defined);self.assertIn('irs_inspect_v2',defined)
            self.assertNotIn('irs_bind',defined);self.assertNotIn('irs_inspect',defined)

    def test_host_profile_budget_and_allocation_failure_degrade(self):
        from inference_ref.model_package import write_package
        from inference_ref.package_validation import chain_definition
        from inference_ref.static_export import export_static
        import numpy as np
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);write_package(root/'model',**chain_definition('int32'));export_static(root/'model',root/'export')
            (root/'input.bin').write_bytes(np.array([2,-3,4],'<i4').tobytes())
            wrapper=root/'fault.c'
            wrapper.write_text('#include "ir_pc.h"\nuint32_t __real_irs_pc_alloc_kind(irs_pc*,uint64_t,uint32_t,uint32_t,irs_block*);\n'
                'uint32_t __wrap_irs_pc_alloc_kind(irs_pc *p,uint64_t n,uint32_t a,uint32_t kind,irs_block *out){'
                'if(kind==IRS_RES_PROFILE){if(PROFILE_BUDGET)p->category_limits[kind]=0;else p->fail_after=0;}'
                'return __real_irs_pc_alloc_kind(p,n,a,kind,out);}\n',encoding='utf-8')
            for budget in (0,1):
                for sanitize in (False,True):
                    with self.subTest(budget=budget,sanitize=sanitize):
                        name=f'profile_{budget}_{int(sanitize)}';binary=root/name
                        flags=['-fsanitize=address,undefined','-fno-omit-frame-pointer','-fno-pie','-no-pie'] if sanitize else []
                        command=['gcc',*FLAGS,'-O1' if sanitize else '-O2',*flags,f'-DPROFILE_BUDGET={budget}',
                            '-I',str(ROOT/'c/include'),str(ROOT/'c/src/ir_static_host.c'),str(wrapper),
                            *[str(ROOT/'c/src'/s) for s in ('ir_core.c','ir_static.c','ir_pc.c')],'-Wl,--wrap=irs_pc_alloc_kind','-lm','-o',str(binary)]
                        built=subprocess.run(command,capture_output=True,text=True,timeout=120)
                        self.assertEqual(built.returncode,0,built.stderr)
                        run=subprocess.run([str(binary),str(root/'export/execution.bin'),str(root/'export/weights.bin'),str(root/'input.bin'),
                            str(root/(name+'.out')),str(root/(name+'.json'))],env={**os.environ,'PATH':'/no-python'},capture_output=True,text=True,timeout=30)
                        self.assertEqual(run.returncode,0,run.stdout+run.stderr);self.assertEqual(run.stderr,'')
                        np.testing.assert_array_equal(np.frombuffer((root/(name+'.out')).read_bytes(),'<i4'),[20,-25])
                        trace=json.loads((root/(name+'.json')).read_text());summary=json.loads(run.stdout)
                        self.assertEqual(trace['status'],0);self.assertFalse(trace['complete']);self.assertFalse(trace['profile_available'])
                        self.assertEqual(trace['profile_status'],4);self.assertEqual(trace['events'][-1]['completed_steps'],4)
                        self.assertFalse(summary['trace_complete']);self.assertEqual(trace['nodes'],[])
                        self.assertEqual(trace['live_allocations']+trace['live_backing_bytes'],0)
                        self.assertTrue(all(c['live_bytes']==0 for c in trace['resources']['categories']))

    def test_ledger_workspace_is_transient_and_required(self):
        from inference_ref.static_backend import build_static,CStaticRuntimeBackend
        from inference_ref.resources import ResourceLedger
        from inference_ref.platform import PCPlatform
        from inference_ref.model_package import write_package
        from inference_ref.package_validation import chain_definition
        from inference_ref.runtime import load_model,create_session
        from inference_ref.contracts import ContractError
        import numpy as np
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);built=build_static(root/'build');backend=CStaticRuntimeBackend(built['library'])
            write_package(root/'model',**chain_definition('int32'))
            ledger=ResourceLedger();platform=PCPlatform(ledger=ledger);model=load_model(root/'model',platform=platform)
            with create_session(model,backend) as session:
                snap=ledger.snapshot();entries=[x for x in snap['entries'] if x['category']=='c_metadata']
                self.assertEqual([x['bytes'] for x in entries if x['label']=='tensor_state'],[9])
                self.assertFalse(any(x['label']=='c_inspect_workspace' for x in entries))
                meta=snap['categories']['c_metadata'];peak=meta['peak_bytes']
                self.assertEqual(peak-meta['live_bytes'],36)
                np.testing.assert_array_equal(session.run({'x':np.array([2,-3,4],np.int32)})['y'],[20,-25])
            before=ledger.snapshot()['live_bytes'];ledger.byte_limits['c_metadata']=peak-1
            with self.assertRaises(ContractError):create_session(model,backend)
            self.assertEqual(ledger.snapshot()['live_bytes'],before)
            self.assertEqual(ledger.snapshot()['categories']['c_metadata']['live_bytes'],0)
            ledger.byte_limits['c_metadata']=peak
            with create_session(model,backend) as session:
                np.testing.assert_array_equal(session.run({'x':np.array([2,-3,4],np.int32)})['y'],[20,-25])
            model.close();self.assertEqual(ledger.snapshot()['live_entries'],0)
