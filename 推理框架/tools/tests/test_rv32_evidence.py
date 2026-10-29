"""T4 evidence rejection gates; no network/compiler/simulator is hidden here."""
import copy
from pathlib import Path
import struct
import sys
import unittest

ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'tools'))
from rv32_evidence import check_elf,check_simulation,check_macros,check_attributes,classify_simulation


def sample_elf():
    blob=bytearray(88);blob[:7]=b'\x7fELF\x01\x01\x01'
    struct.pack_into('<HHIIIIIHHHHHH',blob,16,2,243,1,0,52,0,0,52,32,1,40,0,0)
    struct.pack_into('<IIIIIIII',blob,52,1,84,0,0,4,4,5,4)
    return blob


class RV32EvidenceTests(unittest.TestCase):
    def test_elf_identity_ranges_and_unsupported_abi_rejected(self):
        self.assertTrue(check_elf(sample_elf())['passed'])
        for change in (lambda b:b.__setitem__(4,2),lambda b:b.__setitem__(5,2),
                       lambda b:struct.pack_into('<H',b,18,62),lambda b:struct.pack_into('<I',b,36,1),
                       lambda b:struct.pack_into('<I',b,36,4),lambda b:struct.pack_into('<I',b,68,65537),
                       lambda b:struct.pack_into('<I',b,28,999999)):
            bad=sample_elf();change(bad)
            with self.assertRaises(ValueError):check_elf(bad)

    def test_sim_result_requires_actual_completion_values_and_stack(self):
        row={'simulator_exit':0,'target_status':0,'completed':4,'values':[20,-25],
             'runtime_abi':2,'pointer_bytes':4,'min_sp':65024,'stack_violations':0,'stack_started':True,'done':True,'traps':0}
        self.assertTrue(check_simulation(row,[20,-25])['passed'])
        for key,value in [('simulator_exit',1),('target_status',6),('completed',3),('values',[21,-25]),
                          ('pointer_bytes',8),('runtime_abi',1),('min_sp',0xDFFC),('min_sp',65025),('stack_violations',1),('stack_started',False),('done',False),('traps',1)]:
            bad=copy.deepcopy(row);bad[key]=value
            with self.assertRaises(ValueError):check_simulation(bad,[20,-25])
        bad=dict(row);bad.pop('done')
        with self.assertRaises(ValueError):check_simulation(bad,[20,-25])

    def test_macros_are_measured_rv32_soft_float(self):
        macros={'__riscv_xlen':'32','__SIZEOF_POINTER__':'4','__SIZEOF_SIZE_T__':'4','__BYTE_ORDER__':'__ORDER_LITTLE_ENDIAN__','__riscv_float_abi_soft':'1'}
        self.assertTrue(check_macros(macros)['passed'])
        for key,value in [('__riscv_xlen','64'),('__SIZEOF_POINTER__','8'),('__BYTE_ORDER__','__ORDER_BIG_ENDIAN__'),('__riscv_compressed','1'),('__riscv_flen','32')]:
            bad=dict(macros);bad[key]=value
            with self.assertRaises(ValueError):check_macros(bad)

    def test_linked_attributes_reject_extra_isa_and_stack_alignment(self):
        text='Tag_RISCV_stack_align: 16-bytes\nTag_RISCV_arch: "rv32i2p1_m2p0_zicsr2p0_zifencei2p0_zmmul1p0"\n'
        self.assertTrue(check_attributes(text)['passed'])
        for bad in (text.replace('16-bytes','4-bytes'),text.replace('rv32','rv64'),text.replace('_m2p0','_m2p0_c2p0'),text.replace('_m2p0','_m2p0_f2p2'),text.replace('_m2p0','_m2p0_a2p1')):
            with self.assertRaises(ValueError):check_attributes(bad)

    def test_toolchain_archive_mismatch_and_existing_output_rejected(self):
        from prepare_rv32_toolchain import prepare
        import tempfile
        with tempfile.TemporaryDirectory(dir=ROOT/'build') as tmp:
            root=Path(tmp);archive=root/'bad.tar.gz';archive.write_bytes(b'bad')
            with self.assertRaises(ValueError):prepare(archive,root/'install')
            self.assertFalse((root/'install').exists())
            (root/'install').mkdir();(root/'install/keep').write_text('keep')
            with self.assertRaises(ValueError):prepare(archive,root/'install')
            self.assertEqual((root/'install/keep').read_text(),'keep')

    def test_unproven_is_not_a_confirmed_target_failure(self):
        timeout={'simulator_exit':1,'done':False,'target_status':None,'traps':0}
        self.assertIsNone(classify_simulation(timeout,[20,-25])['passed'])
        mismatch={'simulator_exit':1,'done':True,'target_status':10,'traps':0}
        self.assertIs(classify_simulation(mismatch,[20,-25])['passed'],False)
        self.assertTrue(classify_simulation(mismatch,[20,-25])['failure_confirmed'])
        for row in ({'simulator_exit':1,'done':False,'traps':1},
                    {'simulator_exit':1,'done':False,'stack_violations':1}):
            self.assertIs(classify_simulation(row,[20,-25])['passed'],False)

    def test_negative_controls_reject_crashes_traps_and_missing_summaries(self):
        from rv32_evidence import check_wrong_expected,check_watchdog
        base={'simulator_exit':1,'target_status':10,'done':True,'traps':0,'min_sp':64784,
              'stack_started':True,'stack_violations':0,'fields':{'RTL_DONE':1,'RTL_EXIT':10,'RTL_CYCLES':583077,
              'RTL_MIN_SP':64784,'RTL_STACK_VIOLATIONS':0,'RTL_TRAPS':0,'RTL_STACK_STARTED':1}}
        self.assertTrue(check_wrong_expected(base)['rejected'])
        for change in (lambda b:b.update(simulator_exit=-11),lambda b:b.update(traps=1),
                       lambda b:b['fields'].update(RTL_EXIT=133),lambda b:b['fields'].pop('RTL_CYCLES'),
                       lambda b:b.update(stack_violations=1)):
            bad=copy.deepcopy(base);change(bad)
            with self.assertRaises(ValueError):check_wrong_expected(bad)
        watchdog={'simulator_exit':1,'done':False,'traps':0,'stack_violations':0,'fields':{
            'RTL_DONE':0,'RTL_EXIT':0,'RTL_CYCLES':10,'RTL_MIN_SP':65536,'RTL_STACK_VIOLATIONS':0,'RTL_TRAPS':0,'RTL_STACK_STARTED':0}}
        self.assertTrue(check_watchdog(watchdog,10)['rejected'])
        for bad in ({'simulator_exit':-11,'done':False},dict(watchdog,simulator_exit=-11),
                    dict(watchdog,traps=1),dict(watchdog,fields={}),
                    dict(watchdog,fields=dict(watchdog['fields'],RTL_CYCLES=9))):
            with self.assertRaises(ValueError):check_watchdog(bad,10)

    def test_reused_toolchain_is_checked_against_archive_not_only_driver(self):
        from toolchain_integrity import verify_archive_install
        import hashlib,io,tarfile,tempfile
        with tempfile.TemporaryDirectory(dir=ROOT/'build') as tmp:
            directory=Path(tmp);root=directory/'test-toolchain';root.mkdir()
            contents={'bin/gcc':b'driver','libexec/cc1':b'compiler','bin/ld':b'linker',
                      'include/stdint.h':b'header','lib/specs':b'options'}
            archive=directory/'archive.tar.gz'
            with tarfile.open(archive,'w:gz') as tar:
                for name,data in contents.items():
                    member=tarfile.TarInfo('test-toolchain/'+name);member.size=len(data);tar.addfile(member,io.BytesIO(data))
                    path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
            lock={'directory':'test-toolchain','archive_bytes':archive.stat().st_size,
                  'archive_sha256':hashlib.sha256(archive.read_bytes()).hexdigest()}
            self.assertTrue(verify_archive_install(archive,root,lock)['passed'])
            for name in ('libexec/cc1','bin/ld','include/stdint.h','lib/specs'):
                (root/name).write_bytes(b'replaced')
                with self.assertRaises(ValueError):verify_archive_install(archive,root,lock)
                (root/name).write_bytes(contents[name])
            (root/'include/unexpected.h').write_bytes(b'extra')
            with self.assertRaises(ValueError):verify_archive_install(archive,root,lock)


if __name__=='__main__':unittest.main()
