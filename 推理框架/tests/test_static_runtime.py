"""S4 export and actual standalone C runtime acceptance."""
import json
from pathlib import Path
import tempfile
import unittest
import shutil
import subprocess
import struct
import zlib
import numpy as np

from inference_ref.model_package import write_package,read_package
from inference_ref.package_validation import chain_definition
from inference_ref.c_backend import ROOT


class StaticExportTests(unittest.TestCase):
    def test_export_descriptor_and_repacked_weights(self):
        from inference_ref.static_export import export_static,HEADER,TENSOR,NODE
        with tempfile.TemporaryDirectory(dir=ROOT/'build') as tmp:
            root=Path(tmp)
            write_package(root/'model',**chain_definition('int32'))
            report=export_static(root/'model',root/'export')
            self.assertEqual((HEADER.size,TENSOR.size,NODE.size),(64,96,24))
            self.assertEqual(report['node_count'],4)
            self.assertEqual((root/'export/execution.bin').read_bytes()[:8],b'IRS4BIN1')
            self.assertEqual(len((root/'export/weights.bin').read_bytes()),report['arenas']['weights'])
            with self.assertRaises(Exception): export_static(root/'model',root/'export')

    def test_corrupt_package_not_exported(self):
        from inference_ref.static_export import export_static
        with tempfile.TemporaryDirectory(dir=ROOT/'build') as tmp:
            root=Path(tmp)
            write_package(root/'model',**chain_definition('float32'))
            (root/'model/weights.bin').write_bytes(b'bad')
            with self.assertRaises(Exception): export_static(root/'model',root/'export')
            self.assertFalse((root/'export').exists())

    def test_c_trace_rejects_missing_sync_and_node(self):
        from inference_ref.static_validation import validate_c_trace
        self.assertFalse(validate_c_trace({'format':'inference-c-static-trace','version':1,'status':0,'complete':True,
            'events':[],'nodes':[],'node_count':4,'live_allocations':0,'live_backing_bytes':0})['passed'])


@unittest.skipUnless(shutil.which('gcc'),'C compiler required')
class StaticExecutionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from inference_ref.static_backend import build_static
        cls.tmp=tempfile.TemporaryDirectory(dir=ROOT/'build')
        cls.directory=Path(cls.tmp.name)
        cls.build=build_static(cls.directory/'build')

    @classmethod
    def tearDownClass(cls): cls.tmp.cleanup()

    def test_native_fault_contracts(self):
        for executable in self.build['tests']:
            with self.subTest(executable=executable):
                run=subprocess.run([executable],capture_output=True,text=True)
                self.assertEqual(run.returncode,0,run.stdout+run.stderr)

    def test_standalone_chain_and_no_python_path(self):
        from inference_ref.static_export import export_static
        with tempfile.TemporaryDirectory(dir=self.directory) as tmp:
            root=Path(tmp);write_package(root/'model',**chain_definition('int32'))
            export_static(root/'model',root/'export')
            (root/'input.bin').write_bytes(np.array([2,-3,4],'<i4').tobytes())
            run=subprocess.run([self.build['host'],str(root/'export/execution.bin'),str(root/'export/weights.bin'),
                str(root/'input.bin'),str(root/'output.bin'),str(root/'trace.json')],env={'PATH':'/no-python'},capture_output=True,text=True)
            self.assertEqual(run.returncode,0,run.stdout+run.stderr)
            np.testing.assert_array_equal(np.frombuffer((root/'output.bin').read_bytes(),'<i4'),[20,-25])
            trace=json.loads((root/'trace.json').read_text())
            self.assertTrue(trace['complete']);self.assertEqual(trace['live_allocations'],0)

    def test_existing_runtime_backend_sim_and_trace(self):
        from inference_ref.static_backend import CStaticRuntimeBackend
        from inference_ref.runtime import load_model,create_session
        from inference_ref.tracing import TraceRecorder,validate_trace
        with tempfile.TemporaryDirectory(dir=self.directory) as tmp:
            root=Path(tmp);write_package(root/'model',**chain_definition('float32'))
            trace=TraceRecorder();model=load_model(root/'model',trace=trace)
            backend=CStaticRuntimeBackend(self.build['library'])
            with create_session(model,backend,trace=trace) as session:
                np.testing.assert_array_equal(session.run({'x':np.array([2,-3,4],'float32')})['y'],[20,-25])
                np.testing.assert_array_equal(session.run({'x':np.zeros(3,'float32')})['y'],[0,-5])
            model.close()
            self.assertTrue(validate_trace(trace.snapshot())['passed'])

    def test_numeric_failures_keep_prefix_and_do_not_publish(self):
        from inference_ref.static_export import export_static
        with tempfile.TemporaryDirectory(dir=self.directory) as tmp:
            root=Path(tmp);definition=chain_definition('int32')
            definition['constants']['w2'][:]=np.iinfo(np.int32).max
            write_package(root/'model',**definition);export_static(root/'model',root/'export')
            for name,values,done in [('late',[2,-3,4],3),('early',[2147483647,2147483647,2147483647],0)]:
                (root/(name+'.bin')).write_bytes(np.array(values,'<i4').tobytes())
                run=subprocess.run([self.build['host'],str(root/'export/execution.bin'),str(root/'export/weights.bin'),
                    str(root/(name+'.bin')),str(root/(name+'.out')),str(root/(name+'.json'))],capture_output=True,text=True)
                self.assertEqual(run.returncode,1,run.stderr)
                self.assertFalse((root/(name+'.out')).exists())
                trace=json.loads((root/(name+'.json')).read_text())
                self.assertEqual(trace['status'],6);self.assertEqual(trace['events'][-1]['completed_steps'],done)
                self.assertEqual(trace['live_allocations'],0)

    def test_corrupt_images_weights_and_short_inputs_rejected(self):
        from inference_ref.static_export import export_static
        with tempfile.TemporaryDirectory(dir=self.directory) as tmp:
            root=Path(tmp);write_package(root/'model',**chain_definition('int32'));export_static(root/'model',root/'export')
            original=(root/'export/execution.bin').read_bytes();weights=(root/'export/weights.bin').read_bytes()
            normal_input=np.array([2,-3,4],'<i4').tobytes()
            changes={'crc':lambda b:b.__setitem__(100,b[100]^1),
                'rank':lambda b:struct.pack_into('<I',b,68,0),
                'too_many':lambda b:struct.pack_into('<I',b,16,4097),
                'workspace':lambda b:struct.pack_into('<Q',b,48,4),
                'forward':lambda b:struct.pack_into('<I',b,64+9*96+4,8),
                'alias':lambda b:struct.pack_into('<Q',b,64+5*96+16,0),
                'trailing':lambda b:b.extend(b'X'),
                'weights':lambda b:None,'short_input':lambda b:None}
            for name,change in changes.items():
                with self.subTest(name=name):
                    case=root/name;case.mkdir();blob=bytearray(original);change(blob)
                    if name!='crc':struct.pack_into('<I',blob,56,zlib.crc32(blob[:56]+blob[64:]))
                    (case/'execution.bin').write_bytes(blob)
                    (case/'weights.bin').write_bytes((bytes([weights[0]^1])+weights[1:]) if name=='weights' else weights)
                    (case/'input.bin').write_bytes(normal_input[:-1] if name=='short_input' else normal_input)
                    run=subprocess.run([self.build['host'],str(case/'execution.bin'),str(case/'weights.bin'),str(case/'input.bin'),str(case/'out.bin'),str(case/'trace.json')],capture_output=True,text=True)
                    self.assertEqual(run.returncode,1,run.stderr);self.assertFalse((case/'out.bin').exists())
                    trace=json.loads((case/'trace.json').read_text());self.assertNotEqual(trace['status'],0);self.assertEqual(trace['live_allocations'],0)

    @unittest.skipUnless(__import__('os').name=='posix','POSIX file-size fault injection')
    def test_write_failure_removes_partial_output(self):
        import resource,signal
        from inference_ref.static_export import export_static
        def limited():
            signal.signal(signal.SIGXFSZ,signal.SIG_IGN)
            resource.setrlimit(resource.RLIMIT_FSIZE,(4,4))
        with tempfile.TemporaryDirectory(dir=self.directory) as tmp:
            root=Path(tmp);write_package(root/'model',**chain_definition('int32'));export_static(root/'model',root/'export')
            (root/'input.bin').write_bytes(np.array([2,-3,4],'<i4').tobytes())
            run=subprocess.run([self.build['host'],str(root/'export/execution.bin'),str(root/'export/weights.bin'),
                str(root/'input.bin'),str(root/'output.bin'),str(root/'trace.json')],preexec_fn=limited,capture_output=True,text=True)
            self.assertEqual(run.returncode,1,run.stderr);self.assertEqual(json.loads(run.stdout)['status'],7)
            self.assertFalse((root/'output.bin').exists())


if __name__=='__main__': unittest.main()
