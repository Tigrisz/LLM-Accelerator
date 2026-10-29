from pathlib import Path
import sys,unittest
import tempfile
import shutil,json
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'tools'))


class SampleEvidenceTests(unittest.TestCase):
    def test_inventory_rejects_missing_cases_changed_index_and_manifest(self):
        from rv32_samples import inventory
        source=ROOT/'fixtures/synthetic-v1'
        with tempfile.TemporaryDirectory(dir=ROOT/'build') as tmp:
            directory=Path(tmp)
            with self.assertRaises(ValueError):inventory(directory/'absent')
            copy=directory/'fixtures';shutil.copytree(source,copy)
            for p in (copy/'int_add').iterdir():p.unlink()
            (copy/'int_add').rmdir()
            with self.assertRaises(ValueError):inventory(copy)
            shutil.copytree(source/'int_add',copy/'int_add')
            suite=(copy/'suite.json').read_bytes();index=json.loads(suite);index['cases'].pop()
            (copy/'suite.json').write_text(json.dumps(index))
            with self.assertRaises(ValueError):inventory(copy)
            (copy/'suite.json').write_bytes(suite)
            manifest=copy/'int_add/manifest.json';manifest.write_bytes(manifest.read_bytes()+b'\n')
            with self.assertRaises(ValueError):inventory(copy)
    def test_migration_rejects_shape_or_feed_changes_instead_of_resizing(self):
        from rv32_samples import verify_fixture_mapping
        from inference_ref.fixtures import read_fixture
        from inference_ref.package_validation import package_fixture
        from inference_ref.model_package import read_package
        from inference_ref.contracts import TensorSpec
        from types import SimpleNamespace
        fixture=read_fixture(ROOT/'fixtures/synthetic-v1/int_add')
        with tempfile.TemporaryDirectory(dir=ROOT/'build') as tmp:
            path=Path(tmp)/'package';feeds=package_fixture(path,fixture);package=read_package(path)
            self.assertTrue(verify_fixture_mapping(fixture,package,feeds))
            changed=dict(feeds);first=next(iter(changed));changed[first]=changed[first].copy();changed[first].flat[0]+=1
            with self.assertRaises(ValueError):verify_fixture_mapping(fixture,package,changed)
            tensors=[]
            for t in package.tensors:
                spec=TensorSpec('int32',(2,2),t.spec.storage_shape) if t.id==first else t.spec
                tensors.append(SimpleNamespace(id=t.id,role=t.role,spec=spec))
            fake=SimpleNamespace(tensors=tensors,constant_array=package.constant_array)
            with self.assertRaises(ValueError):verify_fixture_mapping(fixture,fake,feeds)

    def test_inventory_keeps_all_int_shapes_and_excludes_float_without_passing_it(self):
        from rv32_samples import inventory
        rows=inventory(ROOT/'fixtures/synthetic-v1')
        selected=[r for r in rows if r['selected']]
        self.assertEqual(len(rows),54);self.assertEqual(len(selected),27)
        self.assertEqual(next(r for r in selected if r['case_id']=='int_padded')['shapes']['weight'],[3,17])
        self.assertTrue(all(r['target_status']=='not_in_scope' for r in rows if not r['selected']))

    def test_capacity_is_not_confused_with_a_general_link_failure(self):
        from rv32_samples import link_state
        self.assertEqual(link_state(0,''),'linked')
        self.assertEqual(link_state(1,'ld: TCM image/static buffers overlap reserved stack'),'blocked_tcm')
        self.assertEqual(link_state(1,"ld: region `RAM' overflowed by 100 bytes"),'blocked_tcm')
        self.assertEqual(link_state(1,'undefined reference to some_missing_function'),'tool_error')
        self.assertEqual(link_state(-11,'ld: TCM image/static buffers overlap reserved stack'),'tool_error')
        for extra in ('ld: undefined reference to missing_function','ld: unknown tool malfunction'):
            self.assertEqual(link_state(1,'ld: TCM image/static buffers overlap reserved stack\n'+extra),'tool_error')

    def test_overflow_requires_atomic_failure_and_repaired_output(self):
        from rv32_samples import validate_overflow_run
        fields={'T5_STATUS':0,'T5_RUNTIME_ABI':2,'T5_POINTER_BYTES':4,'T5_OVERFLOW_STATUS':6,
            'T5_OVERFLOW_NODES':0,'T5_ATOMIC':1,'T5_REPAIRED':1}
        rtl={'RTL_DONE':1,'RTL_EXIT':0,'RTL_CYCLES':100,'RTL_MIN_SP':64000,'RTL_STACK_STARTED':1,'RTL_STACK_VIOLATIONS':0,'RTL_TRAPS':0}
        text='\n'.join([*(f'{k}={v:08x}' for k,v in fields.items()),*(f'{k}={v}' for k,v in rtl.items()),'RECOVER_OUTPUT=00000000'])
        self.assertTrue(validate_overflow_run(text,0,'00000000')['passed'])
        for bad in (text.replace('T5_ATOMIC=00000001','T5_ATOMIC=00000000'),text.replace('T5_OVERFLOW_NODES=00000000','T5_OVERFLOW_NODES=00000001'),text.replace('RECOVER_OUTPUT=00000000','RECOVER_OUTPUT=01000000')):
            with self.assertRaises(ValueError):validate_overflow_run(bad,0,'00000000')

    def test_output_gate_requires_all_repeats_recovery_and_real_completion(self):
        from rv32_samples import validate_sample_run
        expected={'RUN_0_OUTPUT':'01000000','RUN_1_OUTPUT':'00000000','RUN_2_OUTPUT':'01000000',
                  'RECOVER_OUTPUT':'01000000','REBIND_OUTPUT':'01000000'}
        fields={'T5_STATUS':0,'T5_CHECKS_MASK':8191,'T5_RUNTIME_ABI':2,'T5_POINTER_BYTES':4,
                'RUN_0_NODES':1,'RUN_1_NODES':1,'RUN_2_NODES':1,'T5_SYNC_PUBLISH':6,'T5_SYNC_ACQUIRE':6}
        rtl={'RTL_DONE':1,'RTL_EXIT':0,'RTL_CYCLES':100,'RTL_MIN_SP':64000,'RTL_STACK_STARTED':1,'RTL_STACK_VIOLATIONS':0,'RTL_TRAPS':0}
        text='\n'.join([*(f'{k}={v:08x}' for k,v in fields.items()),*(f'{k}={v}' for k,v in expected.items()),*(f'{k}={v}' for k,v in rtl.items())])
        self.assertTrue(validate_sample_run(text,0,expected,1)['passed'])
        for bad in (text.replace('RUN_2_OUTPUT=01000000','RUN_2_OUTPUT=02000000'),
                    text.replace('RECOVER_OUTPUT=01000000',''),text.replace('RTL_DONE=1','RTL_DONE=0'),
                    text.replace('RTL_TRAPS=0','RTL_TRAPS=1'),text.replace('T5_CHECKS_MASK=00001fff','T5_CHECKS_MASK=00000000'),
                    text+'\nRUN_0_OUTPUT=01000000'):
            with self.assertRaises(ValueError):validate_sample_run(bad,0,expected,1)
        with self.assertRaises(ValueError):validate_sample_run(text,-11,expected,1)
