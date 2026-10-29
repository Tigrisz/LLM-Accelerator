import ctypes as ct
import importlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import unittest
from unittest import mock

import numpy as np

from inference_ref import c_backend, runtime
from inference_ref.contracts import ContractError
from inference_ref.model_package import write_package
from inference_ref.sim_device import SimDevice
from tests.package_support import chain_definition
from tests.support import Workspace

try:
    tracing = importlib.import_module("inference_ref.tracing")
except ModuleNotFoundError:
    tracing = None
ROOT = Path(__file__).resolve().parents[1]


class RecorderTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(tracing, "A7 tracing implementation is missing")

    def test_order_context_snapshot_and_export_roundtrip(self):
        recorder = tracing.TraceRecorder()
        with recorder.context(model_ref="m", session_ref="s"):
            recorder.record("custom.one", data={"count":1})
        recorder.record("custom.two", data={"count":2})
        document = recorder.snapshot()
        self.assertEqual([e["seq"] for e in document["events"]], [1,2])
        self.assertEqual(document["events"][0]["context"]["model_ref"], "m")
        self.assertNotIn("model_ref", document["events"][1]["context"])
        document["events"][0]["data"]["count"] = 99
        self.assertEqual(recorder.snapshot()["events"][0]["data"]["count"], 1)
        work = Workspace()
        self.addCleanup(work.cleanup)
        path = Path(work.name)/"export"
        recorder.export(path)
        loaded = tracing.read_export(path)
        self.assertTrue(loaded["validation"]["passed"])
        self.assertEqual(len(loaded["timeline"]["traceEvents"]), 2)
        with self.assertRaises(ContractError): recorder.export(path)
        (path/"trace.json").write_text("{}")
        with self.assertRaises(ContractError): tracing.read_export(path)

    def test_bounded_buffer_and_observation_errors_are_explicit(self):
        recorder = tracing.TraceRecorder(max_events=1)
        recorder.record("one")
        recorder.record("two")
        self.assertFalse(recorder.snapshot()["complete"])
        self.assertEqual(recorder.snapshot()["dropped_events"], 1)
        self.assertFalse(tracing.validate_trace(recorder.snapshot())["passed"])
        self.assertTrue(tracing.validate_trace(recorder.snapshot(), require_complete=False)["passed"])
        small = tracing.TraceRecorder(max_bytes=1)
        small.record("one")
        self.assertEqual(small.snapshot()["dropped_events"], 1)
        with mock.patch.object(recorder, "record", side_effect=RuntimeError("observer probe")):
            tracing.safe_record(recorder, "probe")
        self.assertEqual(recorder.snapshot()["recording_errors"], 1)
        for kwargs in ({"max_events":True},{"max_bytes":-1}):
            with self.assertRaises(ContractError): tracing.TraceRecorder(**kwargs)

    def test_malformed_event_and_sequence_are_rejected(self):
        recorder = tracing.TraceRecorder()
        with self.assertRaises(ContractError): recorder.record("bad", data={"array":np.ones(2)})
        recorder.record("one")
        document = recorder.snapshot()
        document["events"][0]["seq"] = 9
        self.assertFalse(tracing.validate_trace(document)["passed"])

        self.assertFalse(tracing.validate_trace({"events":None})["passed"])


class RuntimeTraceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not any(shutil.which(c) for c in ("cc","gcc","clang")):
            if os.environ.get("IR_REQUIRE_C") == "1": raise RuntimeError("C compiler required")
            raise unittest.SkipTest("Use WSL with IR_REQUIRE_C=1")
        cls.work = Workspace()
        cls.addClassCleanup(cls.work.cleanup)
        cls.backend = c_backend.CBackend(c_backend.build_backend(Path(cls.work.name)/"backend"))
        cls.package = Path(cls.work.name)/"package"
        write_package(cls.package, **chain_definition())

    def setUp(self):
        self.assertIsNotNone(tracing, "A7 tracing implementation is missing")

    def test_model_plan_run_nodes_and_host_clock_domains(self):
        recorder = tracing.TraceRecorder()
        model = runtime.load_model(self.package, trace=recorder)
        with runtime.create_session(model, self.backend) as session:
            result = session.run({"x":np.array([2,-3,4], np.int32)})
        np.testing.assert_array_equal(result["y"], [20,-25])
        doc = recorder.snapshot()
        self.assertTrue(tracing.validate_trace(doc)["passed"], tracing.validate_trace(doc))
        kinds = {e["kind"] for e in doc["events"]}
        self.assertTrue({"model.loaded","memory.plan","memory.placement","session.open","run.begin",
                         "run.validate","run.prepare","c.chain","c.node","run.outputs","run.end","session.close"} <= kinds)
        nodes = [e for e in doc["events"] if e["kind"] == "c.node"]
        self.assertEqual([e["data"]["index"] for e in nodes], list(range(4)))
        self.assertTrue(all(e["data"]["executed"] and e["data"]["status"]=="OK" for e in nodes))
        self.assertTrue(all(e["data"]["clock"] == "c_process_cpu" for e in nodes))
        self.assertEqual(len({e["context"]["run_ref"] for e in nodes}), 1)
        summary = recorder.summary()
        self.assertEqual(sum(x["executed"] for x in summary["operators"]), 4)
        self.assertEqual(summary["max_session_backing_bytes"], model.plan.total_bytes)

    def test_profiled_c_rejects_alias_capacity_and_preserves_outputs(self):
        self.assertTrue(self.backend.has_profiling)
        a = c_backend.Tensor(np.array([7], np.int32))
        output = c_backend.Tensor(np.array([-99], np.int32))
        call = c_backend.Call("relu", a, output=output)
        native = (c_backend.CCall*1)(call.descriptor)
        profiles = (c_backend.CProfile*1)()
        complete = ct.c_uint32(99)
        fn = self.backend.lib.ir_execute_chain_profiled
        self.assertEqual(self.backend._status(fn(native,1,ct.byref(complete),profiles,0)), "RESOURCE_LIMIT")
        for address in (a.descriptor.data, output.descriptor.data, call.descriptor.workspace,
                        ct.addressof(native), ct.addressof(a.descriptor), ct.addressof(complete)):
            status = fn(native,1,ct.byref(complete),ct.cast(address,ct.POINTER(c_backend.CProfile)),1)
            self.assertEqual(self.backend._status(status), "INVALID_ARGUMENT")
        np.testing.assert_array_equal(a.logical(), [7])
        np.testing.assert_array_equal(output.logical(), [-99])
        self.assertEqual(complete.value, 99)

    def test_numeric_failure_records_failed_and_unexecuted_nodes(self):
        recorder = tracing.TraceRecorder()
        model = runtime.load_model(self.package, trace=recorder)
        with runtime.create_session(model,self.backend) as session:
            with self.assertRaises(ContractError): session.run({"x":np.array([2**30,0,0],np.int32)})
            session.run({"x":np.zeros(3,np.int32)})
        events = recorder.snapshot()["events"]
        nodes = [e for e in events if e["kind"]=="c.node"]
        self.assertEqual(nodes[0]["data"]["status"], "NUMERIC_OVERFLOW")
        self.assertTrue(nodes[0]["data"]["executed"])
        self.assertTrue(all(not n["data"]["executed"] for n in nodes[1:4]))
        self.assertNotEqual(nodes[0]["context"]["run_ref"], nodes[4]["context"]["run_ref"])
        self.assertTrue(tracing.validate_trace(recorder.snapshot())["passed"])

    def test_corrupted_session_link_is_detected_beyond_byte_checks(self):
        recorder = tracing.TraceRecorder()
        model = runtime.load_model(self.package,trace=recorder)
        with runtime.create_session(model,self.backend) as session:
            session.run({"x":np.zeros(3,np.int32)})
        document = recorder.snapshot()
        first = next(e for e in document["events"] if e["kind"]=="c.node")
        first["context"]["session_ref"] = "wrong-session"
        document["recorded_bytes"] = sum(len(json.dumps(e,ensure_ascii=True,allow_nan=False,separators=(",",":")).encode()) for e in document["events"])
        self.assertFalse(tracing.validate_trace(document)["passed"])

    def test_device_task_run_correlation_timeout_recovery_and_release(self):
        recorder = tracing.TraceRecorder()
        model = runtime.load_model(self.package, trace=recorder)
        device = SimDevice(self.backend, trace=recorder)
        session = device.create_session(model)
        handle = session.submit({"x":np.array([2,-3,4],np.int32)},fault="lost_completion")
        self.assertEqual(device.wait(handle,timeout_ticks=1).wait_status,"TIMEOUT")
        device.wait(handle,timeout_ticks=10)
        device.recover(handle)
        device.wait(handle,timeout_ticks=10)
        device.release(handle)
        device.close()
        events = recorder.snapshot()["events"]
        nodes = [e for e in events if e["kind"]=="c.node"]
        self.assertEqual({e["context"]["task_ref"] for e in nodes},{f"{handle.device_id}:{handle.task_id}"})
        self.assertTrue(all(type(e["context"]["logical_tick"]) is int for e in nodes))
        self.assertTrue({"task.accept","task.state","task.release","device.wait","device.recover"} <= {e["kind"] for e in events})
        self.assertTrue(tracing.validate_trace(recorder.snapshot())["passed"])

    def test_observer_overflow_or_failure_does_not_change_execution_or_lease(self):
        for fail in (False, True):
            recorder = tracing.TraceRecorder(max_events=2)
            model = runtime.load_model(self.package, trace=recorder)
            device = SimDevice(self.backend, trace=recorder)
            session = device.create_session(model)
            patch = mock.patch.object(recorder,"record",side_effect=RuntimeError("probe")) if fail else mock.patch.dict({}, {})
            with patch:
                handle = session.submit({"x":np.array([2,-3,4],np.int32)})
                device.wait(handle,timeout_ticks=10)
                np.testing.assert_array_equal(device.result(handle)["y"],[20,-25])
                device.release(handle)
                self.assertEqual(device.stats()["staging_reserved_bytes"],0)
                device.close()
            self.assertFalse(recorder.snapshot()["complete"])

    def test_missing_profile_capability_is_explicit_without_numerical_fallback(self):
        recorder = tracing.TraceRecorder()
        model = runtime.load_model(self.package,trace=recorder)
        with mock.patch.object(self.backend,"has_profiling",False):
            with runtime.create_session(model,self.backend) as session:
                np.testing.assert_array_equal(session.run({"x":np.array([2,-3,4],np.int32)})["y"],[20,-25])
        self.assertFalse(recorder.snapshot()["complete"])
        self.assertTrue(any(e["kind"]=="c.chain" and not e["data"]["profiled"] for e in recorder.snapshot()["events"]))

    def test_trace_validation_cli_and_export(self):
        work = Workspace()
        self.addCleanup(work.cleanup)
        output = Path(work.name)/"validation"
        command = [sys.executable,"-m","inference_ref","verify-trace","--fixtures",str(ROOT/"fixtures/synthetic-v1"),"--output",str(output)]
        run = subprocess.run(command,capture_output=True,text=True,timeout=120)
        self.assertEqual(run.returncode,0,run.stderr)
        report = json.loads((output/"report.json").read_text())
        self.assertTrue(report["passed"])
        self.assertEqual(report["passed_count"],54)
        self.assertTrue(report["trace_validation"]["passed"])
        self.assertEqual(len(report["negative_controls"]),8)
        self.assertTrue(all(not c["passed"] for c in report["negative_controls"].values()))
        self.assertTrue(tracing.read_export(output/"trace")["validation"]["passed"])
        self.assertEqual(subprocess.run(command,capture_output=True).returncode,2)

    def test_cpu_clock_arithmetic_is_verified(self):
        recorder = tracing.TraceRecorder()
        model = runtime.load_model(self.package,trace=recorder)
        with runtime.create_session(model,self.backend) as session: session.run({"x":np.zeros(3,np.int32)})
        document = recorder.snapshot()
        first = next(e for e in document["events"] if e["kind"]=="c.node" and e["data"]["cpu_duration_ns"] is not None)
        first["data"]["cpu_duration_ns"] += 1
        document["recorded_bytes"] = sum(len(json.dumps(e,ensure_ascii=True,allow_nan=False,separators=(",",":")).encode()) for e in document["events"])
        self.assertFalse(tracing.validate_trace(document)["passed"])

    def test_missing_c_execution_and_contradictory_outcomes_are_rejected(self):
        recorder = tracing.TraceRecorder()
        model = runtime.load_model(self.package,trace=recorder)
        device = SimDevice(self.backend,trace=recorder)
        session = device.create_session(model)
        for feeds,fault in (({"x":np.zeros(3,np.int32)},None),
                            ({"x":np.array([2**30,0,0],np.int32)},None),
                            ({"x":np.zeros(3,np.int32)},"lost_completion")):
            handle = session.submit(feeds,fault=fault)
            result = device.wait(handle,timeout_ticks=10)
            if result.wait_status=="DEVICE_ERROR":
                device.recover(handle)
                device.wait(handle,timeout_ticks=10)
            device.release(handle)
        device.close()
        original = recorder.snapshot()
        self.assertTrue(tracing.validate_trace(original)["passed"])
        for mutation in ("missing_all_c","missing_end","end_count","chain_status","unsafe_success","duplicate_chain","node_order"):
            with self.subTest(mutation=mutation):
                document = json.loads(json.dumps(original))
                events = document["events"]
                if mutation in {"missing_all_c","missing_end"}:
                    removed = {"run.end"} if mutation=="missing_end" else {"c.chain","c.node"}
                    document["events"] = [e for e in events if e["kind"] not in removed]
                elif mutation=="end_count":
                    for e in events:
                        if e["kind"]=="run.end": e["data"].update(status="OK",completed_steps=987654)
                elif mutation=="chain_status":
                    for e in events:
                        if e["kind"]=="c.chain": e["data"]["status"] = "OK"
                elif mutation=="unsafe_success":
                    e = next(e for e in events if e["kind"]=="task.state" and e["data"]["state"]=="QUARANTINED")
                    e["data"].update(state="SUCCEEDED",status="OK",outputs_valid=True)
                elif mutation=="duplicate_chain":
                    index = next(i for i,e in enumerate(events) if e["kind"]=="c.chain")
                    events.insert(index,json.loads(json.dumps(events[index])))
                else:
                    rows = [e for e in events if e["kind"]=="c.node"]
                    rows[0]["data"],rows[1]["data"] = rows[1]["data"],rows[0]["data"]
                for i,e in enumerate(document["events"],1): e["seq"] = i
                document["recorded_bytes"] = sum(len(tracing._encode(e)) for e in document["events"])
                self.assertFalse(tracing.validate_trace(document)["passed"],mutation)

    def test_submit_rejection_and_sim_session_close_have_context(self):
        recorder = tracing.TraceRecorder()
        model = runtime.load_model(self.package,trace=recorder)
        device = SimDevice(self.backend,trace=recorder)
        session = device.create_session(model)
        handle = session.submit({"x":np.zeros(3,np.int32)})
        with self.assertRaises(ContractError): session.submit({"x":np.zeros(3,np.int32)})
        with self.assertRaises(ContractError): session.close()
        device.wait(handle,timeout_ticks=10)
        device.release(handle)
        device.close()
        document = recorder.snapshot()
        submits = [e for e in document["events"] if e["kind"]=="device.submit"]
        self.assertEqual([e["data"]["status"] for e in submits],["OK","BUSY"])
        self.assertTrue(all(e["context"].get("session_ref") and e["context"].get("model_ref") for e in submits))
        self.assertEqual(submits[0]["context"]["task_ref"],f"{handle.device_id}:{handle.task_id}")
        self.assertNotIn("task_ref",submits[1]["context"])
        close = [e for e in document["events"] if e["kind"]=="device.session.close"]
        self.assertEqual([e["data"]["status"] for e in close],["BUSY","OK"])
        self.assertTrue(tracing.validate_trace(document)["passed"])

    def test_valid_early_metadata_and_post_c_host_failures_are_distinguished(self):
        class FailingOutput(np.ndarray):
            def copy(self,*args,**kwargs):
                raise MemoryError("deliberate output copy failure")
        recorder = tracing.TraceRecorder()
        model = runtime.load_model(self.package,trace=recorder)
        with runtime.create_session(model,self.backend) as session:
            with self.assertRaises(ContractError): session.run({"x":np.zeros(2,np.int32)})
            original_op = session._calls[2].op
            session._calls[2].op = 999
            with self.assertRaises(ContractError): session.run({"x":np.zeros(3,np.int32)})
            session._calls[2].op = original_op
            original_view = session._views["y"]
            session._views["y"] = original_view.view(FailingOutput)
            with self.assertRaises(MemoryError): session.run({"x":np.zeros(3,np.int32)})
            session._views["y"] = original_view
            session.run({"x":np.zeros(3,np.int32)})
        document = recorder.snapshot()
        self.assertTrue(tracing.validate_trace(document)["passed"],tracing.validate_trace(document))
        ends = [e["data"] for e in document["events"] if e["kind"]=="run.end"]
        self.assertEqual([(e["status"],e["completed_steps"]) for e in ends],
                         [("INVALID_SHAPE",0),("UNSUPPORTED",0),("MemoryError",4),("OK",4)])
        chains = [e["data"]["status"] for e in document["events"] if e["kind"]=="c.chain"]
        self.assertEqual(chains,["UNSUPPORTED","OK","OK"])
