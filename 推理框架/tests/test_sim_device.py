import hashlib
import importlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import unittest
import weakref
from unittest import mock

import numpy as np

from inference_ref.c_backend import CBackend, build_backend
from inference_ref.contracts import ContractError
from inference_ref.model_package import write_package
from inference_ref.runtime import load_model
from tests.package_support import chain_definition
from tests.support import Workspace

try:
    sim = importlib.import_module("inference_ref.sim_device")
except ModuleNotFoundError:
    sim = None

ROOT = Path(__file__).resolve().parents[1]


class SimDeviceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not any(shutil.which(n) for n in ("cc", "gcc", "clang")):
            if os.environ.get("IR_REQUIRE_C") == "1":
                raise RuntimeError("C compiler required for A6")
            raise unittest.SkipTest("C compiler unavailable; use WSL with IR_REQUIRE_C=1")
        cls.work = Workspace()
        cls.addClassCleanup(cls.work.cleanup)
        cls.backend = CBackend(build_backend(Path(cls.work.name) / "backend"))
        cls.models = {}
        for dtype in ("int32", "float32"):
            path = Path(cls.work.name) / dtype
            write_package(path, **chain_definition(dtype, padded=True))
            cls.models[dtype] = load_model(path)

    def setUp(self):
        self.assertIsNotNone(sim, "A6 simulated device implementation is missing")

    def setup_device(self, **config):
        device = sim.SimDevice(self.backend, config=sim.SimConfig(**config))
        return device, device.create_session(self.models["int32"])

    def feeds(self, dtype="int32"):
        return {"x": np.array([2, -3, 4], dtype)}

    def assert_code(self, code, fn, *args, **kwargs):
        with self.assertRaises(ContractError) as caught:
            fn(*args, **kwargs)
        self.assertEqual(caught.exception.code, code)

    def test_success_visibility_snapshot_and_state_order(self):
        for dtype in ("float32", "int32"):
            device = sim.SimDevice(self.backend)
            session = device.create_session(self.models[dtype])
            self.assertTrue(device.query_support(self.models[dtype])["supported"])
            feeds = self.feeds(dtype)
            handle = session.submit(feeds)
            feeds["x"][:] = 0
            for state in ("QUEUED", "TRANSFERRING", "RUNNING", "SYNCING"):
                snapshot = device.poll(handle)
                self.assertEqual(snapshot.state, state)
                self.assertFalse(snapshot.outputs_valid)
                self.assertFalse(snapshot.quiescent)
                self.assert_code("INVALID_STATE", device.result, handle)
                device.advance()
            done = device.poll(handle)
            self.assertEqual(done.state, "SUCCEEDED")
            self.assertTrue(done.outputs_valid and done.quiescent and done.terminal)
            self.assertEqual(done.completed_steps, 4)
            actual = device.result(handle)
            np.testing.assert_array_equal(actual["y"], [20, -25])
            actual["y"][:] = 0
            np.testing.assert_array_equal(device.result(handle)["y"], [20, -25])
            self.assertEqual([e.state for e in device.events(handle)],
                             ["QUEUED", "TRANSFERRING", "RUNNING", "SYNCING", "SUCCEEDED"])
            with self.assertRaises((AttributeError, TypeError)):
                done.state = "RUNNING"
            device.release(handle)
            session.close()
            device.close()

    def test_wait_timeout_and_poll_do_not_release_or_cancel(self):
        device, session = self.setup_device(compute_ticks=5)
        handle = session.submit(self.feeds())
        before = device.stats()
        self.assertEqual(device.wait(handle, timeout_ticks=0).wait_status, "TIMEOUT")
        device.poll(handle)
        self.assertEqual(before, device.stats())
        waited = device.wait(handle, timeout_ticks=3)
        self.assertEqual(waited.wait_status, "TIMEOUT")
        self.assertEqual(waited.task.state, "RUNNING")
        self.assertFalse(waited.task.terminal)
        self.assert_code("BUSY", session.close)
        self.assert_code("BUSY", session.submit, self.feeds())
        self.assert_code("BUSY", device.release, handle)
        self.assert_code("BUSY", device.close)
        self.assertEqual(device.wait(handle, timeout_ticks=20).wait_status, "COMPLETED")
        self.assert_code("BUSY", session.close)
        device.release(handle)
        session.close()
        device.close()

    def test_cancel_requires_ack_in_every_pending_stage(self):
        for ticks in range(4):
            device, session = self.setup_device(cancel_ticks=2)
            handle = session.submit(self.feeds())
            device.advance(ticks)
            requested = device.cancel(handle)
            self.assertEqual(requested.state, "CANCEL_REQUESTED")
            self.assertFalse(requested.quiescent)
            device.advance()
            device.cancel(handle)  # Idempotent: must not restart the acknowledgement delay.
            self.assert_code("BUSY", device.release, handle)
            done = device.wait(handle, timeout_ticks=3).task
            self.assertEqual(done.state, "CANCELLED")
            self.assertTrue(done.quiescent and done.terminal)
            self.assertEqual(done.completed_steps, 4 if ticks == 3 else 0)
            self.assert_code("INVALID_STATE", device.result, handle)
            device.release(handle)
            session.close()
            device.close()

    def test_completed_task_wins_cancel_race(self):
        device, session = self.setup_device()
        handle = session.submit(self.feeds())
        device.wait(handle, timeout_ticks=10)
        self.assertEqual(device.cancel(handle).state, "SUCCEEDED")
        np.testing.assert_array_equal(device.result(handle)["y"], [20, -25])
        device.release(handle)
        device.close()

    def test_fifo_and_quiesce_keep_terminal_handles_until_release(self):
        device, one = self.setup_device()
        two = device.create_session(self.models["int32"])
        h1, h2 = one.submit(self.feeds()), two.submit(self.feeds())
        device.advance(4)
        self.assertEqual(device.poll(h1).state, "SUCCEEDED")
        self.assertEqual(device.poll(h2).state, "QUEUED")
        self.assertEqual(device.quiesce(timeout_ticks=3).wait_status, "COMPLETED")
        self.assertEqual(device.poll(h2).state, "CANCELLED")
        self.assertEqual(device.stats()["live_tasks"], 2)
        device.release(h1)
        device.release(h2)
        device.close()

    def test_numeric_error_is_quiescent_and_session_can_retry_after_release(self):
        device, session = self.setup_device()
        handle = session.submit({"x": np.array([2**30, 0, 0], np.int32)})
        done = device.wait(handle, timeout_ticks=10).task
        self.assertEqual(done.state, "FAILED")
        self.assertEqual(done.status, "NUMERIC_OVERFLOW")
        self.assertTrue(done.quiescent)
        self.assert_code("INVALID_STATE", device.result, handle)
        device.release(handle)
        second = session.submit(self.feeds())
        device.wait(second, timeout_ticks=10)
        np.testing.assert_array_equal(device.result(second)["y"], [20, -25])
        device.release(second)
        device.close()

    def test_device_error_is_not_success_or_python_fallback(self):
        device, session = self.setup_device()
        handle = session.submit(self.feeds(), fault="device_error")
        done = device.wait(handle, timeout_ticks=10).task
        self.assertEqual((done.state, done.status), ("FAILED", "DEVICE_ERROR"))
        self.assertTrue(done.quiescent)
        self.assert_code("INVALID_STATE", device.result, handle)
        device.release(handle)
        device.close()

    def test_lost_completion_quarantines_buffers_until_recovery_ack(self):
        device, session = self.setup_device(recovery_ticks=2)
        handle = session.submit(self.feeds(), fault="lost_completion")
        result = device.wait(handle, timeout_ticks=10)
        self.assertEqual(result.wait_status, "DEVICE_ERROR")
        self.assertEqual(result.task.state, "QUARANTINED")
        self.assertFalse(result.task.quiescent or result.task.terminal or result.task.outputs_valid)
        reserved = device.stats()["staging_reserved_bytes"]
        for _ in range(2):
            self.assert_code("BUSY", device.release, handle)
            self.assert_code("BUSY", session.close)
        self.assertEqual(device.quiesce(timeout_ticks=2).wait_status, "DEVICE_ERROR")
        self.assertEqual(device.stats()["staging_reserved_bytes"], reserved)
        self.assertEqual(device.recover(handle).state, "RECOVERING")
        self.assertEqual(device.wait(handle, timeout_ticks=1).wait_status, "TIMEOUT")
        self.assert_code("BUSY", device.release, handle)
        recovered = device.wait(handle, timeout_ticks=2).task
        self.assertEqual(recovered.state, "FAILED")
        self.assertTrue(recovered.quiescent)
        device.release(handle)
        self.assertEqual(device.stats()["staging_reserved_bytes"], 0)
        device.close()

    def test_cancel_ack_loss_and_unexpected_backend_exception_are_quarantined(self):
        for fault in ("stuck_cancel", "unexpected"):
            device, session = self.setup_device()
            if fault == "stuck_cancel":
                handle = session.submit(self.feeds(), fault=fault)
                device.cancel(handle)
                device.advance()
            else:
                handle = session.submit(self.feeds())
                with mock.patch.object(session._session, "run", side_effect=RuntimeError("unexpected")):
                    device.advance(3)
            self.assertEqual(device.poll(handle).state, "QUARANTINED")
            self.assert_code("BUSY", device.release, handle)
            device.recover(handle)
            device.wait(handle, timeout_ticks=10)
            device.release(handle)
            device.close()

    def test_admission_validation_and_snapshot_failure_have_no_lease_side_effects(self):
        device, session = self.setup_device()
        before = device.stats()
        for feeds in ({}, {"x": np.zeros(2, np.int32)}, {"x": np.zeros(3, np.float32)}):
            with self.assertRaises(ContractError):
                session.submit(feeds)
            self.assertEqual(before, device.stats())
        self.assert_code("INVALID_ARGUMENT", session.submit, self.feeds(), fault="unknown")
        with mock.patch.object(sim, "_copy_feeds", side_effect=MemoryError("probe")):
            self.assert_code("RESOURCE_LIMIT", session.submit, self.feeds())
        self.assertEqual(before, device.stats())
        session.close()
        device.close()

    def test_caps_and_staging_budget_include_retained_completed_tasks(self):
        device, session = self.setup_device(max_tasks=1, max_sessions=2, staging_budget=20)
        two = device.create_session(self.models["int32"])
        self.assert_code("RESOURCE_LIMIT", device.create_session, self.models["int32"])
        handle = session.submit(self.feeds())  # 12 input + 8 output bytes.
        self.assertEqual(device.stats()["staging_reserved_bytes"], 20)
        device.wait(handle, timeout_ticks=10)
        self.assert_code("RESOURCE_LIMIT", two.submit, self.feeds())
        device.release(handle)
        second = two.submit(self.feeds())
        device.wait(second, timeout_ticks=10)
        device.release(second)
        device.close()
        device, session = self.setup_device(staging_budget=19)
        self.assert_code("RESOURCE_LIMIT", session.submit, self.feeds())
        self.assertEqual(device.stats()["live_tasks"], 0)
        device.close()

    def test_stale_foreign_and_malformed_handles_are_rejected(self):
        device, session = self.setup_device()
        other = sim.SimDevice(self.backend)
        handle = session.submit(self.feeds())
        for bad in (None, 1, sim.TaskHandle(handle.device_id, True), sim.TaskHandle(handle.device_id, 999)):
            self.assert_code("INVALID_ARGUMENT", device.poll, bad)
        self.assert_code("INVALID_ARGUMENT", other.poll, handle)
        device.wait(handle, timeout_ticks=10)
        device.release(handle)
        self.assert_code("INVALID_ARGUMENT", device.poll, handle)
        self.assert_code("INVALID_ARGUMENT", device.release, handle)
        newer = session.submit(self.feeds())
        self.assertNotEqual(newer, handle)
        device.quiesce(timeout_ticks=10)
        device.release(newer)
        device.close()
        other.close()

    def test_owner_thread_and_invalid_clock_parameters(self):
        device, session = self.setup_device()
        handle = session.submit(self.feeds())
        errors = []
        def foreign_poll():
            try: device.poll(handle)
            except ContractError as exc: errors.append(exc.code)
        thread = threading.Thread(target=foreign_poll)
        thread.start()
        thread.join(timeout=2)
        self.assertFalse(thread.is_alive())
        self.assertEqual(errors, ["INVALID_STATE"])
        for bad in (True, -1, 100001, 1.5):
            self.assert_code("INVALID_ARGUMENT", device.advance, bad)
            self.assert_code("INVALID_ARGUMENT", device.wait, handle, timeout_ticks=bad)
        device.quiesce(timeout_ticks=10)
        device.release(handle)
        device.close()
        device.close()
        self.assert_code("INVALID_STATE", device.create_session, self.models["int32"])
        for options in ({"compute_ticks": 0}, {"cancel_ticks": True}, {"max_tasks": 0}, {"staging_budget": -1}):
            self.assert_code("INVALID_ARGUMENT", sim.SimConfig, **options)

    def test_repeated_submission_reuses_arenas_and_preserves_weights(self):
        device, session = self.setup_device()
        before = session.memory_info()
        model_hash = hashlib.sha256(self.models["int32"].package.weights).hexdigest()
        for i in range(12):
            feeds = self.feeds() if i % 2 == 0 else {"x": np.zeros(3, np.int32)}
            handle = session.submit(feeds)
            device.wait(handle, timeout_ticks=10)
            np.testing.assert_array_equal(device.result(handle)["y"], [20,-25] if i % 2 == 0 else [0,-5])
            device.release(handle)
            self.assertEqual(session.memory_info(), before)
        self.assertEqual(hashlib.sha256(self.models["int32"].package.weights).hexdigest(), model_hash)
        device.close()

    def test_device_validation_cli(self):
        work = Workspace()
        self.addCleanup(work.cleanup)
        output = Path(work.name) / "validation"
        command = [sys.executable, "-m", "inference_ref", "verify-device", "--fixtures",
                   str(ROOT/"fixtures/synthetic-v1"), "--output", str(output)]
        run = subprocess.run(command, capture_output=True, text=True, timeout=120)
        self.assertEqual(run.returncode, 0, run.stderr)
        report = json.loads((output/"report.json").read_text())
        self.assertTrue(report["passed"])
        self.assertEqual(report["passed_count"], 54)
        self.assertEqual(report["source"], "simulated_device_c")
        self.assertTrue(report["fixture_files_unchanged"])
        self.assertTrue(all(x["passed"] for x in report["lifecycle_scenarios"]))
        self.assertEqual(subprocess.run(command, capture_output=True).returncode, 2)

    def test_unregistered_session_cannot_bypass_task_lease(self):
        device, session = self.setup_device()
        handle = session.submit(self.feeds())
        impostor = sim.SimSession(device, session._session)
        self.assert_code("INVALID_ARGUMENT", impostor.submit, self.feeds())
        self.assert_code("INVALID_ARGUMENT", impostor.close)
        device.wait(handle, timeout_ticks=10)
        np.testing.assert_array_equal(device.result(handle)["y"], [20,-25])
        device.release(handle)
        device.close()

    def test_release_frees_private_snapshots_and_outputs(self):
        device, session = self.setup_device()
        handle = session.submit(self.feeds())
        copied_input = weakref.ref(device._tasks[handle.task_id].feeds["x"])
        device.wait(handle, timeout_ticks=10)
        staged_output = weakref.ref(device._tasks[handle.task_id].outputs["y"])
        device.release(handle)
        self.assertIsNone(copied_input())
        self.assertIsNone(staged_output())
        device.close()

    def test_unexpected_exception_keeps_current_progress_without_reusing_old_progress(self):
        device, session = self.setup_device()
        previous = session.submit(self.feeds())
        device.wait(previous, timeout_ticks=10)
        device.release(previous)
        original = session._session.run
        for after_c, error_kind in ((True, "memory"), (False, "memory"), (False, "contract")):
            handle = session.submit(self.feeds())
            def fail(feeds):
                if after_c:
                    original(feeds)  # Real C execution; then fail host-side output publication.
                if error_kind == "contract":
                    raise ContractError("BUSY", "entry probe")
                raise MemoryError("output-copy probe" if after_c else "entry probe")
            with mock.patch.object(session._session, "run", side_effect=fail):
                device.advance(3)
            snapshot = device.poll(handle)
            with self.subTest(after_c=after_c, error_kind=error_kind):
                self.assertEqual(snapshot.state, "QUARANTINED")
                self.assertFalse(snapshot.quiescent or snapshot.outputs_valid)
                self.assertEqual(snapshot.completed_steps, 4 if after_c else 0)
                self.assertEqual(snapshot.execution_status, "OK" if after_c else None)
            device.recover(handle)
            device.wait(handle, timeout_ticks=10)
            device.release(handle)
        device.close()

    def test_one_wrong_result_produces_failed_report_and_cli_one(self):
        from inference_ref import device_validation
        work = Workspace()
        self.addCleanup(work.cleanup)
        output = Path(work.name) / "negative_control"
        original = sim.SimDevice.result
        corrupted = False
        def wrong_once(device, handle):
            nonlocal corrupted
            values = original(device, handle)
            if not corrupted:
                next(iter(values.values())).flat[0] += 1
                corrupted = True
            return values
        with mock.patch.object(sim.SimDevice, "result", wrong_once):
            report = device_validation.run_device_validation(ROOT/"fixtures/synthetic-v1", output)
        self.assertFalse(report["passed"])
        self.assertEqual(report["passed_count"], 53)
        self.assertFalse(json.loads((output/"report.json").read_text())["passed"])
        cli = importlib.import_module("inference_ref.__main__")
        with mock.patch.object(device_validation, "run_device_validation", return_value=report), mock.patch.object(
                sys, "argv", ["inference_ref", "verify-device", "--fixtures", str(ROOT/"fixtures/synthetic-v1"),
                              "--output", str(Path(work.name)/"cli")]):
            self.assertEqual(cli.main(), 1)
