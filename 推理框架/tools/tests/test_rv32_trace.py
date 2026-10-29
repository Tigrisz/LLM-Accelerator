import tempfile
from pathlib import Path
import sys
import unittest
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'tools'))


class TraceEvidenceTests(unittest.TestCase):
    def test_identical_empty_or_truncated_prefix_is_not_a_full_trace(self):
        from rv32_trace import audit_trace,compare_trace
        with tempfile.TemporaryDirectory(dir=ROOT/'build') as directory:
            a=Path(directory)/'a';b=Path(directory)/'b'
            for text in ('','0 10 0 0 10637 c 10000\n'):
                a.write_text(text);b.write_text(text)
                with self.assertRaises(ValueError):audit_trace(a,533119,533119,require_full=True)
                with self.assertRaises(ValueError):compare_trace(a,b,expected_count=533119)
            a.write_text('0 10 0 0 10637 c 10000\n');b.write_bytes(a.read_bytes())
            self.assertEqual(audit_trace(a,1,1,require_full=True)['rows'],1)
            self.assertTrue(compare_trace(a,b,expected_count=1)['equal'])

    def test_trace_format_sequence_and_actual_row_count_are_checked(self):
        from rv32_trace import audit_trace
        with tempfile.TemporaryDirectory(dir=ROOT/'build') as directory:
            path=Path(directory)/'trace'
            for text in ('1 10 0 0 10637 c 10000\n','0 10 0 0 malformed c 10000\n','0 10 0 0 10637 20 10000\n','0 10 0 0\n'):
                path.write_text(text)
                with self.assertRaises(ValueError):audit_trace(path,1,1,require_full=True)

    def test_original_failure_requires_specific_completed_fault_signature(self):
        from rv32_trace import check_original_failure
        base=dict(simulator_exit=1,done=1,target_exit=3,cycles=22,retired=10,trace_rows=10,traps=[])
        rows={0x18:(0xfff60613,12,0xff97),0x1c:(0x40e60633,12,0x17),0x20:(0xffc67613,12,0xff94),0x24:(0x01464513,10,3)}
        self.assertTrue(check_original_failure('minimal',base,rows)['reproduced'])
        for bad in (dict(base,done=0,target_exit=0),dict(base,simulator_exit=-11),dict(base,traps=[(1,2,3)]),dict(base,target_exit=133)):
            with self.assertRaises(ValueError):check_original_failure('minimal',bad,rows)
        broken=dict(rows);broken[0x20]=(0xffc67613,12,0x14)
        with self.assertRaises(ValueError):check_original_failure('minimal',base,broken)
        diff={'equal':False,'index':1522,'left':'1522 1559 0 3f18 ffc67613 c 14','right':'1522 1555 1 3f18 ffc67613 c ff94'}
        full=dict(base,target_exit=133,traps=[(0x264c,5,0x10000)])
        self.assertTrue(check_original_failure('full',full,{},diff)['reproduced'])
        for bad in (dict(diff,index=1521),dict(diff,right='1522 1555 1 3f18 ffc67613 c 14')):
            with self.assertRaises(ValueError):check_original_failure('full',full,{},bad)
        with self.assertRaises(ValueError):check_original_failure('full',dict(full,traps=[(0x264c,2,0)]),{},diff)
