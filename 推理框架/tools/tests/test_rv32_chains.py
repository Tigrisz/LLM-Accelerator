from pathlib import Path
import sys,unittest,importlib.util,copy,tempfile
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'tools'))

class ChainMigrationTests(unittest.TestCase):
    def module(self):
        self.assertIsNotNone(importlib.util.find_spec('rv32_chains'),'Chain migration contract missing')
        import rv32_chains
        return rv32_chains

    def test_original_definition_is_locked_against_shape_constant_and_node_changes(self):
        m=self.module()
        from inference_ref.package_validation import chain_definition
        for dtype in ('int32','float32'):
            definition=chain_definition(dtype);self.assertTrue(m.verify_definition(definition,dtype))
            for mutate in (lambda d:d['tensors'][0]['shape'].__setitem__(0,2),lambda d:d['constants']['bias'].__setitem__(0,2),lambda d:d['nodes'].reverse()):
                changed=copy.deepcopy(definition);mutate(changed)
                with self.assertRaises(ValueError):m.verify_definition(changed,dtype)
            from inference_ref.model_package import write_package,read_package
            with tempfile.TemporaryDirectory(dir=ROOT/'build') as tmp:
                path=Path(tmp)/'p';write_package(path,**definition);package=read_package(path);feeds={'x':np.array([2,-3,4],dtype=dtype)}
                self.assertTrue(m.verify_package(package,feeds,dtype))
                feeds['x'][0]=1
                with self.assertRaises(ValueError):m.verify_package(package,feeds,dtype)

    def test_manual_chain_results_do_not_change_with_dtype(self):
        m=self.module()
        for dtype in ('int32','float32'):
            self.assertEqual(m.manual_result(dtype,'normal').tolist(),[20,-25])
            self.assertEqual(m.manual_result(dtype,'zero').tolist(),[0,-5])
        with self.assertRaises(ValueError):m.manual_result('float32','unknown')

    def test_partial_failure_gate_requires_two_completed_and_full_recovery(self):
        m=self.module()
        base=['T5_STATUS=00000000','T5_RUNTIME_ABI=00000002','T5_POINTER_BYTES=00000004',
            'T7_FAILURE=00000005','T7_COMPLETED=00000002','T7_OUTPUT_INVALID=00000001','T7_RECOVERED_NODES=00000004','T7_ZERO_NODES=00000004','T7_CLOSED=00000001',
            'RTL_DONE=1','RTL_EXIT=0','RTL_CYCLES=100','RTL_MIN_SP=64000','RTL_STACK_STARTED=1','RTL_STACK_VIOLATIONS=0','RTL_TRAPS=0',
            'RECOVER_OUTPUT=0000a0410000c8c1','ZERO_OUTPUT=000000000000a0c0']
        text='\n'.join(base)
        self.assertTrue(m.validate_chain_fault(text,0,'float32')['passed'])
        for bad,code in [(text.replace('T7_COMPLETED=00000002','T7_COMPLETED=00000004'),0),(text.replace('T7_OUTPUT_INVALID=00000001',''),0),
                         (text.replace('RECOVER_OUTPUT=0000a0410000c8c1','RECOVER_OUTPUT=0000000000000000'),0),(text,2),(text.replace('RTL_TRAPS=0',''),0)]:
            with self.assertRaises(ValueError):m.validate_chain_fault(bad,code,'float32')
