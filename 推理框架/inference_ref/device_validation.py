"""A6 acceptance: packages and planned arenas through task lifecycle and real C."""

from dataclasses import asdict
import hashlib
from pathlib import Path

import numpy as np

from . import oracle, reference
from .c_backend import CBackend, ROOT, _new_directory, build_backend, run_native_tests
from .compare import compare_arrays
from .contracts import ContractError, require
from .fixtures import read_fixture
from .model_package import write_package
from .package_validation import _evaluate, _hash_tree, chain_definition, package_fixture
from .reporting import write_json_exclusive
from .runtime import load_model
from .sim_device import SimConfig, SimDevice
from .suite import verify_suite


def _cleanup_task(device, handle):
    snapshot = device.poll(handle)
    if snapshot.state == "QUARANTINED":
        device.recover(handle)
    elif not snapshot.terminal and snapshot.state != "RECOVERING":
        device.cancel(handle)
    result = device.wait(handle, timeout_ticks=100)
    if result.task.state == "QUARANTINED":
        device.recover(handle)
        result = device.wait(handle, timeout_ticks=100)
    require(result.task.terminal and result.task.quiescent, "DEVICE_ERROR", "Validation cleanup could not quiesce")
    device.release(handle)


def _blocked(code, operation, *args):
    try:
        operation(*args)
    except ContractError as exc:
        require(exc.code == code, "VALIDATION_FAILED", f"Expected {code}, got {exc.code}")
    else:
        raise ContractError("VALIDATION_FAILED", f"Expected rejection {code}")


def _scenarios(model, backend, trace=None):
    results = []
    for name in ("visibility_and_snapshot", "timeout_cancel_ack", "lost_completion_recovery",
                 "numeric_failure_retry", "acknowledged_device_error", "cancel_ack_loss",
                 "fifo_quiesce", "staging_cap_and_stale_handle"):
        config = (SimConfig(compute_ticks=4, cancel_ticks=2) if name == "timeout_cancel_ack" else
                  SimConfig(max_tasks=1, staging_budget=20) if name == "staging_cap_and_stale_handle" else SimConfig())
        device = SimDevice(backend, config=config, trace=trace)
        session = device.create_session(model)
        handles, observations = [], {}
        feeds = {"x":np.array([2,-3,4], np.int32)}
        record = {"name": name, "passed": False, "config": asdict(config)}
        try:
            fault = {"lost_completion_recovery": "lost_completion", "acknowledged_device_error": "device_error",
                     "cancel_ack_loss": "stuck_cancel"}.get(name)
            if name == "numeric_failure_retry":
                feeds = {"x":np.array([0,0,400000000], np.int32)}
            handle = session.submit(feeds, fault=fault)
            handles.append(handle)
            if name == "visibility_and_snapshot":
                feeds["x"][:] = 0
                _blocked("INVALID_STATE", device.result, handle)
                device.advance(3)
                require(device.poll(handle).state == "SYNCING", "VALIDATION_FAILED", "Missing sync stage")
                _blocked("INVALID_STATE", device.result, handle)
                done = device.wait(handle, timeout_ticks=2).task
                require(done.outputs_valid and done.quiescent, "VALIDATION_FAILED", "Output visibility missing")
                require(compare_arrays(np.array([20,-25], np.int32), device.result(handle)["y"])["passed"],
                        "VALIDATION_FAILED", "Input snapshot changed")
            elif name == "timeout_cancel_ack":
                waited = device.wait(handle, timeout_ticks=3)
                require(waited.wait_status == "TIMEOUT" and not waited.task.terminal,
                        "VALIDATION_FAILED", "Wait timeout became terminal")
                observations["timeout"] = waited.task.to_dict()
                _blocked("BUSY", device.release, handle)
                _blocked("BUSY", session.close)
                device.cancel(handle)
                require(device.wait(handle, timeout_ticks=1).wait_status == "TIMEOUT", "VALIDATION_FAILED", "Early cancel ack")
                require(device.wait(handle, timeout_ticks=2).task.state == "CANCELLED", "VALIDATION_FAILED", "Cancel not acknowledged")
            elif name in {"lost_completion_recovery", "cancel_ack_loss"}:
                if name == "cancel_ack_loss":
                    device.cancel(handle)
                waited = device.wait(handle, timeout_ticks=10)
                require(waited.wait_status == "DEVICE_ERROR" and not waited.task.quiescent,
                        "VALIDATION_FAILED", "Unconfirmed task was released")
                observations["quarantined"] = waited.task.to_dict()
                _blocked("BUSY", device.release, handle)
                _blocked("BUSY", session.close)
                device.recover(handle)
                done = device.wait(handle, timeout_ticks=10).task
                require(done.state == "FAILED" and done.quiescent, "VALIDATION_FAILED", "Recovery lacks confirmation")
            elif name == "numeric_failure_retry":
                done = device.wait(handle, timeout_ticks=10).task
                require(done.status == "NUMERIC_OVERFLOW" and done.completed_steps == 3 and done.quiescent,
                        "VALIDATION_FAILED", "Numeric failure completion mismatch")
                observations["numeric_failure"] = done.to_dict()
                device.release(handle)
                handles.remove(handle)
                handle = session.submit({"x":np.zeros(3, np.int32)})
                handles.append(handle)
                device.wait(handle, timeout_ticks=10)
                require(compare_arrays(np.array([0,-5], np.int32), device.result(handle)["y"])["passed"],
                        "VALIDATION_FAILED", "Retry failed")
            elif name == "acknowledged_device_error":
                done = device.wait(handle, timeout_ticks=10).task
                require(done.state == "FAILED" and done.status == "DEVICE_ERROR" and done.quiescent,
                        "VALIDATION_FAILED", "Device error became successful")
                _blocked("INVALID_STATE", device.result, handle)
            elif name == "fifo_quiesce":
                second = device.create_session(model)
                other = second.submit(feeds)
                handles.append(other)
                device.advance(4)
                require(device.poll(handle).state == "SUCCEEDED" and device.poll(other).state == "QUEUED",
                        "VALIDATION_FAILED", "FIFO mismatch")
                require(device.quiesce(timeout_ticks=10).wait_status == "COMPLETED" and
                        device.poll(other).state == "CANCELLED", "VALIDATION_FAILED", "Quiesce failed")
            elif name == "staging_cap_and_stale_handle":
                require(device.stats()["staging_reserved_bytes"] == 20, "VALIDATION_FAILED", "Bad staging accounting")
                device.wait(handle, timeout_ticks=10)
                second = device.create_session(model)
                _blocked("RESOURCE_LIMIT", second.submit, feeds)
                device.release(handle)
                handles.remove(handle)
                _blocked("INVALID_ARGUMENT", device.poll, handle)
                require(device.stats()["staging_reserved_bytes"] == 0, "VALIDATION_FAILED", "Staging leaked")
                handle = second.submit(feeds)
                handles.append(handle)
                require(device.wait(handle, timeout_ticks=10).task.state == "SUCCEEDED",
                        "VALIDATION_FAILED", "Released staging was not reusable")
            record["tasks"] = [device.poll(h).to_dict() for h in handles]
            record["events"] = [[asdict(e) for e in device.events(h)] for h in handles]
            record["observations"] = observations
            record["passed"] = True
        except ContractError as exc:
            record["error"] = {"code": exc.code, "message": str(exc)}
        finally:
            for handle in handles:
                _cleanup_task(device, handle)
            record["final_live_tasks"] = device.stats()["live_tasks"]
            record["final_staging_bytes"] = device.stats()["staging_reserved_bytes"]
            device.close()
        results.append(record)
    return results


def _chains(directory, backend, trace=None):
    results = []
    for dtype in ("int32", "float32"):
        path = directory / dtype
        write_package(path, **chain_definition(dtype))
        model = load_model(path,trace=trace)
        device = SimDevice(backend,trace=trace)
        session = device.create_session(model)
        feeds = {"x":np.array([2,-3,4], dtype)}
        handle = session.submit(feeds)
        record = {"dtype": dtype, "passed": False, "memory_plan": model.plan.to_dict()}
        try:
            waited = device.wait(handle, timeout_ticks=10)
            require(waited.task.state == "SUCCEEDED", waited.task.status, "Chain not completed")
            actual = device.result(handle)["y"]
            comparisons = {key:compare_arrays(expected, actual) for key,expected in (
                ("scalar_vs_device", _evaluate(model.package, feeds, reference.execute)["y"]),
                ("numpy_vs_device", _evaluate(model.package, feeds, oracle.execute)["y"]),
                ("manual_final", np.array([20,-25], dtype)))}
            record.update(task=waited.task.to_dict(), comparisons=comparisons,
                          events=[asdict(e) for e in device.events(handle)])
            record["passed"] = all(x["passed"] for x in comparisons.values())
        except ContractError as exc:
            record["error"] = {"code":exc.code, "message":str(exc)}
        finally:
            _cleanup_task(device, handle)
            device.close()
        results.append(record)
    return results


def run_device_validation(root: Path, output: Path, compiler=None) -> dict:
    root, output = Path(root).resolve(), Path(output).resolve()
    require(not output.is_relative_to(root), "INVALID_ARGUMENT", "Output must be outside fixture tree")
    before, baseline = _hash_tree(root), verify_suite(root)
    directory = _new_directory(output)
    backend = CBackend(build_backend(directory / "backend", compiler))
    device = SimDevice(backend)
    results = []
    for checked in baseline["cases"]:
        name = checked["case_id"]
        if not checked["passed"]:
            results.append({"case_id":name, "passed":False, "python_validation":checked})
            continue
        handle, session = None, None
        try:
            fixture = read_fixture(root / name)
            feeds = package_fixture(directory / "packages" / name, fixture)
            model = load_model(directory / "packages" / name)
            session = device.create_session(model)
            handle = session.submit(feeds)
            waited = device.wait(handle, timeout_ticks=10)
            require(waited.wait_status == "COMPLETED" and waited.task.state == "SUCCEEDED",
                    waited.task.status, "Device task did not succeed")
            actual = device.result(handle)["y"]
            op, p = fixture.metadata["operation"]["name"], fixture.metadata["comparison"]
            comparisons = {key:compare_arrays(expected, actual, p["atol"], p["rtol"]) for key,expected in (
                ("stored_vs_device", fixture.expected),
                ("scalar_vs_device", reference.execute(op, fixture.inputs)),
                ("numpy_vs_device", oracle.execute(op, fixture.inputs)))}
            results.append({"case_id":name, "passed":all(x["passed"] for x in comparisons.values()),
                            "comparisons":comparisons, "task":waited.task.to_dict(),
                            "events":[asdict(e) for e in device.events(handle)],
                            "memory_plan":model.plan.to_dict(),
                            "actual_backing_bytes":session.memory_info()["total_backing_bytes"],
                            "manifest_sha256":model.package.manifest_sha256,
                            "weights_sha256":model.package.weights_sha256,
                            "fixture_manifest_sha256":checked["manifest_sha256"]})
        except ContractError as exc:
            results.append({"case_id":name, "passed":False, "error":{"code":exc.code,"message":str(exc)}})
        finally:
            if handle is not None:
                _cleanup_task(device, handle)
            if session is not None:
                session.close()
    stats = device.stats()
    device.close()
    chains = _chains(directory / "chains", backend)
    scenario_model = load_model(directory / "chains/int32")
    scenarios = _scenarios(scenario_model, backend)
    native = run_native_tests(directory / "native_tests", compiler)
    unchanged = before == _hash_tree(root)
    count = sum(c["passed"] for c in results)
    files = [ROOT / "inference_ref" / n for n in ("sim_device.py", "device_validation.py", "runtime.py",
             "model_package.py", "memory.py", "c_backend.py", "package_validation.py", "__main__.py")]
    report = {"format":"inference-device-report", "version":1, "source":"simulated_device_c",
              "scope":"phase1a_a6", "clock":"deterministic_logical_ticks", "config":asdict(SimConfig()),
              "passed":count == len(results) and baseline["passed"] and all(c["passed"] for c in chains) and
                       all(c["passed"] for c in scenarios) and native["passed"] and unchanged and
                       stats["live_tasks"] == 0 and stats["staging_reserved_bytes"] == 0,
              "case_count":len(results), "passed_count":count, "cases":results, "chains":chains,
              "lifecycle_scenarios":scenarios, "final_device_stats":stats, "native_tests":native,
              "fixture_files_unchanged":unchanged, "fixture_files_before_sha256":before,
              "suite_sha256":baseline["suite_sha256"], "python_reference_passed":baseline["passed"],
              "python_reference_source_sha256":baseline["source_sha256"], "environment":baseline["environment"],
              "source_sha256":{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in files},
              "build":backend.build}
    write_json_exclusive(directory / "report.json", report)
    return report
