import copy,importlib.util,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'tools'))

class TotalAcceptanceTests(unittest.TestCase):
    def module(self):
        self.assertIsNotNone(importlib.util.find_spec('total_acceptance'),'Total acceptance gates missing')
        import total_acceptance
        return total_acceptance

    @staticmethod
    def case(name,status='passed'):
        row={'case_id':name,'status':status,'passed':True if status=='passed' else False if status=='failed' else None}
        if status=='passed':
            row['elf_sha256']='a'*64
            row['profiles']={n:{'status':'passed','simulator_exit':0,'elf_sha256':'a'*64,'result':{'passed':True,'outputs':{'RUN_0_OUTPUT':'00000000'}}} for n in ('single_issue','dual_issue')}
        return row

    def test_missing_duplicate_extra_and_empty_coverage_cannot_pass(self):
        m=self.module();rows=[self.case('a'),self.case('b')]
        self.assertEqual(m.aggregate_cases(rows,{'a','b'})['status'],'passed')
        for bad in ([],rows[:1],rows+[self.case('b')],rows+[self.case('c')]):
            with self.assertRaises(ValueError):m.aggregate_cases(bad,{'a','b'})

    def test_capacity_and_unknown_are_not_numerical_passes(self):
        m=self.module()
        for state in ('blocked_tcm','unproven','tool_error'):
            result=m.aggregate_cases([self.case('a'),self.case('b',state)],{'a','b'})
            self.assertEqual(result['status'],state);self.assertIsNone(result['passed']);self.assertFalse(result['all_selected_rv32_validated'])
            self.assertEqual(result['counts']['passed'],1)
        self.assertIs(m.aggregate_cases([self.case('a','failed')],{'a'})['passed'],False)

    def test_passed_case_requires_both_profiles_same_elf_and_complete_outputs(self):
        m=self.module()
        for change in (lambda r:r['profiles'].pop('dual_issue'),lambda r:r['profiles']['dual_issue'].__setitem__('elf_sha256','b'*64),
                       lambda r:r['profiles']['dual_issue']['result'].__setitem__('outputs',{}),lambda r:r.__setitem__('passed',None)):
            row=self.case('a');change(row)
            with self.assertRaises(ValueError):m.aggregate_cases([row],{'a'})

    def test_pc_gate_requires_full_tests_pressure_and_no_skips(self):
        m=self.module()
        tests=lambda n:dict(passed=True,tests_run=n,skipped=0,failures=0,errors=0)
        row={'passed':True,'framework_tests':tests(174),'tool_tests':tests(61),'resource_acceptance':dict(cases=54,chains=4,resource_probes=24,native_runs=6,sanitizer_runs=3,iterations=200)}
        self.assertTrue(m.validate_pc(row,200)['passed'])
        for change in (lambda r:r['framework_tests'].__setitem__('tests_run',173),lambda r:r['tool_tests'].__setitem__('skipped',1),lambda r:r['resource_acceptance'].__setitem__('resource_probes',23)):
            bad=copy.deepcopy(row);change(bad)
            with self.assertRaises(ValueError):m.validate_pc(bad,200)

    def test_overall_status_preserves_false_null_and_missing_stage(self):
        m=self.module()
        self.assertEqual(m.combine_status(['passed','passed']),'passed')
        for state in ('blocked_tcm','failed','unproven','tool_error'):
            self.assertEqual(m.combine_status(['passed',state]),state)
        with self.assertRaises(ValueError):m.combine_status([])
        with self.assertRaises(ValueError):m.combine_status(['passed',None])

    def test_existing_output_is_rejected_without_mutation(self):
        self.assertIsNotNone(importlib.util.find_spec('reproduce_total'),'Unified reproduction entry missing')
        from reproduce_total import main
        with tempfile.TemporaryDirectory(dir=ROOT/'build') as tmp:
            out=Path(tmp)/'existing';out.mkdir();(out/'marker').write_text('keep')
            self.assertNotEqual(main(['--output',str(out),'--toolchain',str(Path(tmp)/'absent')]),0)
            self.assertEqual([p.name for p in out.iterdir()],['marker']);self.assertEqual((out/'marker').read_text(),'keep')

    def test_exact_mismatch_requires_complete_lifecycle_before_failed(self):
        m=self.module()
        fields={'T5_STATUS':0,'T5_CHECKS_MASK':8191,'T5_RUNTIME_ABI':2,'T5_POINTER_BYTES':4,'RUN_0_NODES':1,'RUN_1_NODES':1,'RUN_2_NODES':1,'T5_SYNC_PUBLISH':6,'T5_SYNC_ACQUIRE':6}
        rtl={'RTL_DONE':1,'RTL_EXIT':0,'RTL_CYCLES':100,'RTL_MIN_SP':64000,'RTL_STACK_STARTED':1,'RTL_STACK_VIOLATIONS':0,'RTL_TRAPS':0}
        expected={k:'00000000' for k in ('RUN_0_OUTPUT','RUN_1_OUTPUT','RUN_2_OUTPUT','RECOVER_OUTPUT','REBIND_OUTPUT')}
        text='\n'.join([*(f'{k}={v:08x}' for k,v in fields.items()),*(f'{k}={v}' for k,v in rtl.items()),*(f'{k}={v}' for k,v in expected.items())])
        gate=lambda t,c:m.validate_exact_run(t,c,expected,1)
        self.assertEqual(m.observe(text,0,gate)['status'],'passed')
        wrong=text.replace('RUN_0_OUTPUT=00000000','RUN_0_OUTPUT=01000000')
        self.assertEqual(m.observe(wrong,0,gate)['status'],'failed')
        for bad,code in [(wrong.replace('RTL_TRAPS=0',''),0),(wrong,2),(wrong.replace('T5_CHECKS_MASK=00001fff',''),0)]:
            self.assertEqual(m.observe(bad,code,gate)['status'],'unproven')

    def test_counts_come_from_actual_phases_including_blocked_fault(self):
        m=self.module();positive={'status':'passed','validation':{'outputs':{str(i):'00' for i in range(5)}}}
        matrix=[{'phases':{'chain_int32':{'profiles':{'single_issue':positive,'dual_issue':positive}},'chain_int32_fault':{'status':'blocked_tcm'}}}]
        self.assertEqual(m.execution_counts(matrix),dict(positive_profile_executions=2,valid_positive_output_records=10,partial_failure_profile_executions=0,valid_recovery_output_records=0,validated_sync_unknown_runs=2))

    def test_chain_recovery_mismatch_is_failed_but_missing_control_unknown(self):
        m=self.module();from rv32_chains import validate_chain_fault
        text='\n'.join(['T5_STATUS=00000000','T5_RUNTIME_ABI=00000002','T5_POINTER_BYTES=00000004','T7_FAILURE=00000006','T7_COMPLETED=00000002','T7_OUTPUT_INVALID=00000001','T7_RECOVERED_NODES=00000004','T7_ZERO_NODES=00000004','T7_CLOSED=00000001','RTL_DONE=1','RTL_EXIT=0','RTL_CYCLES=100','RTL_MIN_SP=64000','RTL_STACK_STARTED=1','RTL_STACK_VIOLATIONS=0','RTL_TRAPS=0','RECOVER_OUTPUT=0000000000000000','ZERO_OUTPUT=00000000fbffffff'])
        gate=lambda t,c:validate_chain_fault(t,c,'int32')
        self.assertEqual(m.observe(text,0,gate)['status'],'failed')
        self.assertEqual(m.observe(text.replace('T7_CLOSED=00000001',''),0,gate)['status'],'unproven')

    def test_integer_oracle_is_rebuilt_and_requires_five_output_identities(self):
        import numpy as np
        from inference_ref.contracts import TensorSpec
        m=self.module();expected=m.reference_outputs(np.array([1,2],np.int32),np.array([0,0],np.int32),TensorSpec('int32',(2,),(3,)))
        self.assertEqual(len(expected),5);self.assertEqual(expected['RUN_0_OUTPUT'],'010000000200000000000000')
        with self.assertRaises(ValueError):m.validate_exact_run('',0,{'RUN_0_OUTPUT':'deadbeef'},1)
        self.assertTrue(hasattr(m,'check_expected_outputs'))
        with self.assertRaises(ValueError):m.check_expected_outputs({'RUN_0_OUTPUT':'deadbeef'},expected)

    def test_pc_logs_trace_and_auxiliary_elf_are_required(self):
        m=self.module();self.assertTrue(hasattr(m,'verify_pc_artifacts'));self.assertTrue(hasattr(m,'verify_image'))
        with tempfile.TemporaryDirectory(dir=ROOT/'build') as tmp:
            with self.assertRaises((ValueError,OSError)):m.verify_pc_artifacts(Path(tmp),'normal',{'exit_code':0,'trace_validation':{'passed':True}},1,4)
            with self.assertRaises((ValueError,OSError)):m.verify_image({'elf_sha256':'a'*64},'probe',Path(tmp),'int32')

    def test_chain_label_cannot_substitute_other_dtype(self):
        m=self.module();self.assertTrue(hasattr(m,'check_chain_record'))
        with self.assertRaises(ValueError):m.check_chain_record('chain_int32',{'dtype':'float32'},{},None,None)

    def test_cross_profile_numerical_failure_is_preserved(self):
        m=self.module();profiles={name:{'status':'passed','passed':True,'validation':{'passed':True,'outputs':{'RUN_0_OUTPUT':value}}} for name,value in [('single_issue','00000000'),('dual_issue','01000000')]}
        actual=m.reconcile_profiles(profiles)
        self.assertEqual(actual['dual_issue']['status'],'failed');self.assertIs(actual['dual_issue']['passed'],False)

    def test_overflow_wrong_recovery_is_failed_only_after_complete_control(self):
        m=self.module();from rv32_samples import validate_overflow_run
        fields={'T5_STATUS':0,'T5_RUNTIME_ABI':2,'T5_POINTER_BYTES':4,'T5_OVERFLOW_STATUS':6,'T5_OVERFLOW_NODES':0,'T5_ATOMIC':1,'T5_REPAIRED':1}
        rtl={'RTL_DONE':1,'RTL_EXIT':0,'RTL_CYCLES':100,'RTL_MIN_SP':64000,'RTL_STACK_STARTED':1,'RTL_STACK_VIOLATIONS':0,'RTL_TRAPS':0}
        text='\n'.join([*(f'{k}={v:08x}' for k,v in fields.items()),*(f'{k}={v}' for k,v in rtl.items()),'RECOVER_OUTPUT=01000000'])
        gate=lambda t,c:validate_overflow_run(t,c,'00000000')
        self.assertEqual(m.observe(text,0,gate)['status'],'failed');self.assertEqual(m.observe(text.replace('T5_ATOMIC=00000001',''),0,gate)['status'],'unproven')

    def test_new_all_workload_does_not_pass_capacity_block(self):
        from run_rv32_samples import all_workload_result
        result=all_workload_result([{'status':'passed'},{'status':'blocked_tcm'}],True)
        self.assertEqual(result['status'],'blocked_tcm');self.assertIsNone(result['passed']);self.assertFalse(result['all_selected_rv32_validated'])

    def test_fp_fault_wrong_recovery_requires_complete_controls(self):
        m=self.module();from rv32_fp32 import validate_float_faults
        fields={'T5_STATUS':0,'T5_RUNTIME_ABI':2,'T5_POINTER_BYTES':4,'T6_NAN':5,'T6_POS_INF':5,'T6_NEG_INF':5,'T6_NONFINITE_EXEC':5,'T6_OVERFLOW':6,'T6_COMPLETED':0,'T6_INPUT_ATOMIC':1,'T6_OUTPUT_ATOMIC':1,'T6_RECOVERED':1}
        rtl={'RTL_DONE':1,'RTL_EXIT':0,'RTL_CYCLES':100,'RTL_MIN_SP':64000,'RTL_STACK_STARTED':1,'RTL_STACK_VIOLATIONS':0,'RTL_TRAPS':0}
        text='\n'.join([*(f'{k}={v:08x}' for k,v in fields.items()),*(f'{k}={v}' for k,v in rtl.items()),'RECOVER_OUTPUT=0100000000000000'])
        gate=lambda t,c:m.validate_recovery_run(t,c,validate_float_faults,{'RECOVER_OUTPUT':'0000000000000000'})
        self.assertEqual(m.observe(text,0,gate)['status'],'failed');self.assertEqual(m.observe(text.replace('T6_INPUT_ATOMIC=00000001',''),0,gate)['status'],'unproven')

    def test_boundary_replay_constructs_explicit_storage_shape(self):
        m=self.module();outputs=m.boundary_outputs()
        self.assertEqual(len(outputs),5);self.assertEqual(outputs['RUN_1_OUTPUT'],'00'*24)
        self.assertEqual(outputs['RUN_0_OUTPUT'],'0000803f0200803f0200000000000000ffff7f7f00000000')
