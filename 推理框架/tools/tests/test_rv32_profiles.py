from pathlib import Path
import sys
import unittest
import json,tempfile,subprocess,io
from contextlib import redirect_stderr
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'tools'))


class ProfileSummaryTests(unittest.TestCase):
    def test_both_profiles_generate_complete_explicit_build_arguments(self):
        from rv32_profiles import parameters,verilator_arguments,check_build_parameters
        for name,dual in [('single_issue',0),('dual_issue',1)]:
            p=parameters(name);args=verilator_arguments(p)
            self.assertEqual(p['DUAL_ISSUE'],dual);self.assertEqual(len(p),9)
            self.assertEqual(p['INIT_FILE'],'firmware.hex')
            self.assertTrue(check_build_parameters(['verilator',*args],p))
            changed=parameters(name);changed['RAM_WORDS']=1
            self.assertEqual(parameters(name)['RAM_WORDS'],16384)
        with self.assertRaises(ValueError):parameters('other')

    def test_missing_duplicate_or_mismatched_build_parameter_cannot_be_summarized(self):
        from rv32_profiles import parameters,verilator_arguments,check_build_parameters
        p=parameters('single_issue');args=verilator_arguments(p)
        for command in (args[:-1],args+['-GDUAL_ISSUE=1'],args+['-GEXTRA=1'],
                        [a.replace("-GDUAL_ISSUE=1'b0","-GDUAL_ISSUE=1'b1") for a in args]):
            with self.assertRaises(ValueError):check_build_parameters(command,p)

    def test_records_keep_failed_unknown_and_unexecuted_controls_distinct(self):
        from rv32_profiles import parameters,verilator_arguments,profile_record
        for value in (True,False,None):
            p=parameters('dual_issue');command=['verilator',*verilator_arguments(p)]
            record=profile_record('dual_issue',command,'a'*64,{'done':value},{'passed':value},None,None,None,None,'b'*64)
            self.assertIs(record['simulation_passed'],value)
            self.assertEqual(record['parameters'],p);self.assertEqual(record['normal_elf_sha256'],'a'*64)
            self.assertFalse(record['negative_controls']['wrong_expected']['tested'])
            self.assertIsNone(record['negative_controls']['wrong_expected']['validation'])
            self.assertFalse(record['board_verified']);self.assertIsNone(record['full_stack_worst_case'])
        with self.assertRaises(ValueError):profile_record('dual_issue',command,'bad',{}, {'passed':True},None,None,None,None,'b'*64)

    def test_complete_dual_profile_does_not_claim_missing_or_wrong_zero_output_passed(self):
        from rv32_profiles import complete_dual_validation
        row={'simulator_exit':0,'target_status':0,'completed':4,'values':[20,-25],'zero_values':[0,-5],
             'runtime_abi':2,'pointer_bytes':4,'min_sp':64784,'stack_violations':0,'stack_started':True,'done':True,'traps':0,
             'fields':{'NEGATIVE_CHECKS':3,'SYNC_PUBLISH':2,'SYNC_ACQUIRE':2}}
        self.assertTrue(complete_dual_validation(row,[20,-25],[0,-5])['passed'])
        self.assertIs(complete_dual_validation(dict(row,zero_values=[0,-4]),[20,-25],[0,-5])['passed'],False)
        self.assertIsNone(complete_dual_validation(dict(row,zero_values=None),[20,-25],[0,-5])['passed'])

    def test_failure_entrypoints_preserve_false_null_and_unexecuted_controls(self):
        import run_rv32,reproduce_rv32
        from rv32_profiles import parameters,verilator_arguments,profile_record,require_dual_pass
        for status in (False,None):
            with self.subTest(status=status),tempfile.TemporaryDirectory(dir=ROOT/'build') as temporary:
                directory=Path(temporary);child=directory/'child'
                p=parameters('dual_issue');record=profile_record('dual_issue',['verilator',*verilator_arguments(p)],'a'*64,
                    {'done':status is False},{'passed':status,'state':'failed' if status is False else 'unproven'},None,None,None,None,'b'*64)
                profiles={'dual_issue':record}
                def fail_run(output,toolchain,mode):
                    Path(output).mkdir();require_dual_pass(profiles)
                with patch.object(run_rv32,'run',side_effect=fail_run),redirect_stderr(io.StringIO()):
                    self.assertEqual(run_rv32.main(['--toolchain',str(directory),'--output',str(child)]),1)
                failure=json.loads((child/'failure.json').read_text())
                self.assertIs(failure['target_result'],status)
                self.assertIs(failure['rtl_profiles']['dual_issue']['simulation_passed'],status)
                self.assertFalse(failure['rtl_profiles']['dual_issue']['negative_controls']['wrong_expected']['tested'])
                (directory/'receipt.json').write_text('{}');tc=directory/'tc';tc.mkdir()
                def snapshot(source,target):Path(target).mkdir();return {}
                def failed_child(command,**kwargs):
                    target=directory/'parent/workspace/build/target';target.mkdir(parents=True)
                    (target/'failure.json').write_text(json.dumps(failure));return subprocess.CompletedProcess(command,1)
                with patch.object(reproduce_rv32,'snapshot_source',side_effect=snapshot),patch.object(reproduce_rv32,'run_command',side_effect=failed_child),redirect_stderr(io.StringIO()):
                    self.assertEqual(reproduce_rv32.main(['--toolchain',str(tc),'--output',str(directory/'parent')]),1)
                parent=json.loads((directory/'parent/failure.json').read_text())
                self.assertIs(parent['target_result'],status)
                self.assertEqual(parent['rtl_profiles'],failure['rtl_profiles'])
                self.assertNotEqual(parent.get('error'),'FileNotFoundError')
