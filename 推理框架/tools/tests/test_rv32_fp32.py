from pathlib import Path
import importlib.util
import sys,unittest,tempfile
import numpy as np
import struct
from types import SimpleNamespace
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'tools'))


class FP32MigrationTests(unittest.TestCase):
    @staticmethod
    def _uart():
        return '\n'.join(['T5_STATUS=00000000','T5_CHECKS_MASK=00001fff','T5_RUNTIME_ABI=00000002','T5_POINTER_BYTES=00000004',
            'RUN_0_NODES=00000001','RUN_1_NODES=00000001','RUN_2_NODES=00000001','T5_SYNC_PUBLISH=00000006','T5_SYNC_ACQUIRE=00000006',
            'RTL_DONE=1','RTL_EXIT=0','RTL_CYCLES=100','RTL_MIN_SP=64000','RTL_STACK_STARTED=1','RTL_STACK_VIOLATIONS=0','RTL_TRAPS=0',
            'RUN_0_OUTPUT=0000803f','RUN_1_OUTPUT=00000000','RUN_2_OUTPUT=0000803f','RECOVER_OUTPUT=0000803f','REBIND_OUTPUT=0000803f'])

    def _build_observation(self,stdout,exit_code=0):
        """Only compiler/simulator boundary is replaced; real package/export/build_case gates run."""
        from run_rv32_samples import build_case
        from inference_ref.model_package import write_package,read_package
        from inference_ref.static_export import export_static
        with tempfile.TemporaryDirectory(dir=ROOT/'build') as tmp:
            path=Path(tmp);records=[{'id':n,'role':'output' if n=='y' else 'input','dtype':'float32','layout':'row_major','shape':[1],'storage_shape':[1]} for n in ('a','b','y')]
            write_package(path/'p',model_id='gate_test',tensors=records,nodes=[{'id':'add','op':'add','inputs':{'a':'a','b':'b'},'output':'y'}],inputs=['a','b'],outputs=['y'],constants={})
            package=read_package(path/'p');exported=export_static(path/'p',path/'export',address_bits=32)
            blob=bytearray(88);blob[:7]=b'\x7fELF\x01\x01\x01';struct.pack_into('<HHIIIIIHHHHHH',blob,16,2,243,1,0,52,0,0,52,32,1,40,0,0);struct.pack_into('<IIIIIIII',blob,52,1,84,0,0,4,4,5,4)
            def link(name,directory,objects):
                (directory/'firmware.elf').write_bytes(blob);return SimpleNamespace(returncode=0,stdout='',stderr='')
            def execute(name,args,**kwargs):
                text='';code=0
                if name.endswith('_readelf'):text='Tag_RISCV_stack_align: 16-bytes\nTag_RISCV_arch: "rv32i2p1_m2p0_zicsr2p0_zifencei2p0"\n'
                elif name.endswith('_symbols'):
                    text='00000000 T _start\n00001000 B __bss_start\n00001100 B __bss_end\n0000e000 B __stack_bottom\n00010000 B __stack_top\n'+ '\n'.join('00000020 T '+s for s in ('__adddf3','__subdf3','__muldf3','__extendsfdf2','__truncdfsf2'))
                elif name.endswith('_objdump'):text=' 0: 00000013 nop\n'
                elif name.endswith('_binary'):(path/'firmware.bin').write_bytes(b'\x13\x00\x00\x00')
                elif name.endswith(('_single_issue','_dual_issue')):
                    text=stdout if isinstance(stdout,str) else stdout['single_issue' if name.endswith('_single_issue') else 'dual_issue'];code=exit_code
                return SimpleNamespace(returncode=code,stdout=text,stderr='')
            profiles={k:{'simulator':'controlled-external-simulator'} for k in ('single_issue','dual_issue')}
            normal=np.array([1],np.float32);zero=np.array([0],np.float32);refs={label:{k:value for k in ('scalar','numpy','pc_core','pc_static')} for label,value in [('normal',normal),('zero',zero)]}
            expected={'RUN_0_OUTPUT':'0000803f','RUN_1_OUTPUT':'00000000','RUN_2_OUTPUT':'0000803f','RECOVER_OUTPUT':'0000803f','REBIND_OUTPUT':'0000803f'}
            return build_case('test',path,package,{'a':normal,'b':zero},exported,False,expected,execute,link,Path('external-cc'),lambda n:n,[],[],profiles,float_context=(refs,package.tensors[-1].spec,{'mode':'abs_plus_rel','atol':1e-6,'rtol':1e-5}))

    def test_build_case_keeps_missing_evidence_and_host_errors_unproven(self):
        text=self._uart()
        for stdout,code in [(text.replace('T5_CHECKS_MASK=00001fff',''),0),(text.replace('RTL_TRAPS=0',''),0),(text,2)]:
            with self.subTest(code=code,missing=len(text)-len(stdout)):
                result=self._build_observation(stdout,code)
                self.assertEqual(result['status'],'unproven');self.assertIsNone(result['passed'])
        self.assertTrue(self._build_observation(text)['passed'])
        for stdout in (text.replace('RUN_2_OUTPUT=0000803f','RUN_2_OUTPUT=00000040'),text.replace('RUN_2_OUTPUT=0000803f','RUN_2_OUTPUT=0100803f')):
            with self.subTest(mismatch=stdout):self.assertEqual(self._build_observation(stdout)['status'],'failed')

    def test_unproven_outputs_do_not_claim_single_dual_equality(self):
        result=self._build_observation('',1)
        self.assertEqual(result['status'],'unproven');self.assertIsNone(result['single_dual_bitwise_equal'])
        text=self._uart();result=self._build_observation(text)
        self.assertTrue(result['single_dual_bitwise_equal'])
        result=self._build_observation({'single_issue':text,'dual_issue':text.replace('0000803f','0100803f')})
        self.assertEqual(result['status'],'failed');self.assertIs(result['single_dual_bitwise_equal'],False)

    def test_physical_feed_preserves_float_bits_padding_and_original_hash(self):
        from run_rv32_samples import physical
        from rv32_samples import verify_fixture_mapping
        from inference_ref.contracts import TensorSpec
        from inference_ref.fixtures import read_fixture
        from inference_ref.package_validation import package_fixture
        from inference_ref.model_package import read_package
        a=np.array([1.5,-0.0],dtype='<f4')
        self.assertEqual(physical(a,TensorSpec('float32',(2,),(3,))).hex(),'0000c03f0000008000000000')
        fixture=read_fixture(ROOT/'fixtures/synthetic-v1/float_padded')
        with tempfile.TemporaryDirectory(dir=ROOT/'build') as tmp:
            path=Path(tmp)/'p';feeds=package_fixture(path,fixture);package=read_package(path)
            self.assertTrue(verify_fixture_mapping(fixture,package,feeds))
            changed={k:v.copy() for k,v in feeds.items()};changed[next(iter(changed))].flat[0]+=0.5
            with self.assertRaises(ValueError):verify_fixture_mapping(fixture,package,changed)

    def test_inventory_selects_all_float_without_claiming_int32_rerun(self):
        from rv32_samples import inventory
        rows=inventory(ROOT/'fixtures/synthetic-v1',dtype='float32')
        self.assertEqual(len(rows),54)
        self.assertEqual(sum(r['selected'] for r in rows),27)
        self.assertTrue(all(r['dtype']=='float32' for r in rows if r['selected']))
        self.assertTrue(all(r['target_status']=='not_in_scope' for r in rows if not r['selected']))
        with self.assertRaises(ValueError):inventory(ROOT/'fixtures/synthetic-v1',dtype='float16')

    def _module(self):
        self.assertIsNotNone(importlib.util.find_spec('rv32_fp32'),'FP32 evidence gates missing')
        import rv32_fp32
        return rv32_fp32

    def test_comparison_uses_tolerance_but_rejects_nonfinite_and_dirty_padding(self):
        m=self._module();from inference_ref.contracts import TensorSpec
        spec=TensorSpec('float32',(2,),(3,));policy={'mode':'abs_plus_rel','atol':1e-6,'rtol':1e-5}
        ref=np.array([1.0,0.0],np.float32)
        good=np.array([1.000005,0.0000005,0],dtype='<f4').tobytes().hex()
        result=m.compare_output(good,ref,spec,policy)
        self.assertTrue(result['passed']);self.assertFalse(result['bitwise_equal']);self.assertEqual(result['nonfinite_count'],0)
        for values in ([1.01,0,0],[float('nan'),0,0],[1,float('inf'),0],[1,0,1],[1,0,-0.0]):
            self.assertFalse(m.compare_output(np.array(values,dtype='<f4').tobytes().hex(),ref,spec,policy)['passed'])
        with self.assertRaises(ValueError):m.compare_output('00000000',ref,spec,policy)

    def test_sample_gate_requires_repeat_determinism_and_every_reference(self):
        m=self._module();from inference_ref.contracts import TensorSpec
        spec=TensorSpec('float32',(1,),(1,));normal=np.array([1],np.float32);zero=np.array([0],np.float32)
        references={'normal':{'scalar':normal,'numpy':normal,'pc_core':normal,'pc_static':normal,'stored':normal},
                    'zero':{'scalar':zero,'numpy':zero,'pc_core':zero,'pc_static':zero}}
        fields={'T5_STATUS':0,'T5_CHECKS_MASK':8191,'T5_RUNTIME_ABI':2,'T5_POINTER_BYTES':4,
                'RUN_0_NODES':1,'RUN_1_NODES':1,'RUN_2_NODES':1,'T5_SYNC_PUBLISH':6,'T5_SYNC_ACQUIRE':6}
        rtl={'RTL_DONE':1,'RTL_EXIT':0,'RTL_CYCLES':100,'RTL_MIN_SP':64000,'RTL_STACK_STARTED':1,'RTL_STACK_VIOLATIONS':0,'RTL_TRAPS':0}
        outputs={'RUN_0_OUTPUT':'0000803f','RUN_1_OUTPUT':'00000000','RUN_2_OUTPUT':'0000803f','RECOVER_OUTPUT':'0000803f','REBIND_OUTPUT':'0000803f'}
        text='\n'.join([*(f'{k}={v:08x}' for k,v in fields.items()),*(f'{k}={v}' for k,v in rtl.items()),*(f'{k}={v}' for k,v in outputs.items())])
        policy={'mode':'abs_plus_rel','atol':1e-6,'rtol':1e-5}
        self.assertTrue(m.validate_float_run(text,0,references,spec,policy,1)['passed'])
        for bad in (text.replace('RUN_2_OUTPUT=0000803f','RUN_2_OUTPUT=0100803f'),text.replace('REBIND_OUTPUT=0000803f',''),text.replace('RUN_0_OUTPUT=0000803f','RUN_0_OUTPUT=0000807f')):
            with self.assertRaises(ValueError):m.validate_float_run(bad,0,references,spec,policy,1)
        incomplete={k:dict(v) for k,v in references.items()};del incomplete['normal']['numpy']
        with self.assertRaises(ValueError):m.validate_float_run(text,0,incomplete,spec,policy,1)
        wrong_stored={k:dict(v) for k,v in references.items()};wrong_stored['normal']['stored']=np.array([2],np.float32)
        with self.assertRaises(ValueError):m.validate_float_run(text,0,wrong_stored,spec,policy,1)

    def test_softfloat_gate_rejects_missing_helpers_and_hardware_fp_opcodes(self):
        m=self._module()
        symbols='\n'.join(f'00001000 T {s}' for s in ('__adddf3','__subdf3','__muldf3','__extendsfdf2','__truncdfsf2'))
        self.assertTrue(m.check_softfloat_symbols(symbols,'  0: 00000013 nop\n')['passed'])
        with self.assertRaises(ValueError):m.check_softfloat_symbols(symbols.replace('__muldf3','unrelated'),'')
        with self.assertRaises(ValueError):m.check_softfloat_symbols(symbols,'  10: 002080d3 fadd.s fa1,fa0,fa2\n')

    def test_fault_gate_requires_all_nonfinite_rejections_and_atomic_overflow_recovery(self):
        m=self._module()
        fields={'T5_STATUS':0,'T5_RUNTIME_ABI':2,'T5_POINTER_BYTES':4,'T6_NAN':5,'T6_POS_INF':5,'T6_NEG_INF':5,
                'T6_NONFINITE_EXEC':5,'T6_OVERFLOW':6,'T6_COMPLETED':0,'T6_INPUT_ATOMIC':1,'T6_OUTPUT_ATOMIC':1,'T6_RECOVERED':1}
        rtl={'RTL_DONE':1,'RTL_EXIT':0,'RTL_CYCLES':100,'RTL_MIN_SP':64000,'RTL_STACK_STARTED':1,'RTL_STACK_VIOLATIONS':0,'RTL_TRAPS':0}
        text='\n'.join([*(f'{k}={v:08x}' for k,v in fields.items()),*(f'{k}={v}' for k,v in rtl.items()),'RECOVER_OUTPUT=0000000000000000'])
        self.assertTrue(m.validate_float_faults(text,0)['passed'])
        for bad in (text.replace('T6_OUTPUT_ATOMIC=00000001','T6_OUTPUT_ATOMIC=00000000'),text.replace('T6_NAN=00000005','T6_NAN=00000000'),text.replace('RECOVER_OUTPUT=0000000000000000','RECOVER_OUTPUT=0000803f00000000')):
            with self.assertRaises(ValueError):m.validate_float_faults(bad,0)
