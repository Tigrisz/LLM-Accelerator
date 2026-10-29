"""A7 acceptance: tracing on/off against the same actual C backend."""

import hashlib
import json
from pathlib import Path

import numpy as np

from . import oracle, reference
from .c_backend import CBackend, ROOT, _new_directory, build_backend, run_native_tests
from .compare import compare_arrays
from .contracts import ContractError, require
from .device_validation import _chains, _cleanup_task, _scenarios
from .fixtures import read_fixture
from .package_validation import _hash_tree, package_fixture
from .reporting import write_json_exclusive
from .runtime import load_model
from .sim_device import SimDevice
from .suite import verify_suite
from .tracing import TraceRecorder, read_export, validate_trace


def _execute(device,model,feeds):
    session, handle = device.create_session(model), None
    try:
        handle = session.submit(feeds)
        done = device.wait(handle,timeout_ticks=10).task
        require(done.state=="SUCCEEDED",done.status,"Acceptance task failed")
        return device.result(handle)["y"]
    finally:
        if handle is not None: _cleanup_task(device,handle)
        session.close()


class _BrokenRecorder(TraceRecorder):
    def record(self,*args,**kwargs):
        raise RuntimeError("deliberate observer failure")


def _observation_probes(model,backend,directory):
    rows = []
    for name,recorder in (("overflow",TraceRecorder(max_events=1)),("observer_error",_BrokenRecorder())):
        device = SimDevice(backend,trace=recorder)
        actual = _execute(device,model,{"x":np.array([2,-3,4],np.int32)})
        stats = device.stats()
        device.close()
        correct = compare_arrays(np.array([20,-25],np.int32),actual)["passed"]
        snapshot = recorder.snapshot()
        check = validate_trace(snapshot)
        rows.append({"name":name,"execution_passed":correct,"complete":snapshot["complete"],
                     "trace_validation":check,"dropped_events":snapshot["dropped_events"],
                     "recording_errors":snapshot["recording_errors"],
                     "passed":correct and not snapshot["complete"] and not check["passed"] and
                              stats["live_tasks"]==0 and stats["staging_reserved_bytes"]==0})
        recorder.export(directory/name)
    return rows


def _negative_checks(document):
    """Damage semantic evidence, then repair syntax/accounting to test the validator."""
    results = {}
    for name in ("missing_node","missing_all_c","missing_end","end_count","chain_status",
                 "unsafe_success","duplicate_chain","node_order"):
        negative = json.loads(json.dumps(document))
        events = negative["events"]
        if name=="missing_node":
            del events[next(i for i,e in enumerate(events) if e["kind"]=="c.node")]
        elif name in {"missing_all_c","missing_end"}:
            removed = {"run.end"} if name=="missing_end" else {"c.chain","c.node"}
            negative["events"] = [e for e in events if e["kind"] not in removed]
        elif name=="end_count":
            for e in events:
                if e["kind"]=="run.end": e["data"].update(status="OK",completed_steps=987654)
        elif name=="chain_status":
            for e in events:
                if e["kind"]=="c.chain": e["data"]["status"] = "OK"
        elif name=="unsafe_success":
            e = next(e for e in events if e["kind"]=="task.state" and e["data"]["state"]=="QUARANTINED")
            e["data"].update(state="SUCCEEDED",status="OK",outputs_valid=True)
        elif name=="duplicate_chain":
            index = next(i for i,e in enumerate(events) if e["kind"]=="c.chain")
            events.insert(index,json.loads(json.dumps(events[index])))
        else:
            # The fixture cases have one node; select the first multi-node chain.
            ref = next(e["context"]["run_ref"] for e in events if e["kind"]=="c.chain" and e["data"]["node_count"]>1)
            rows = [e for e in events if e["kind"]=="c.node" and e["context"]["run_ref"]==ref]
            rows[0]["data"],rows[1]["data"] = rows[1]["data"],rows[0]["data"]
        for i,e in enumerate(negative["events"],1): e["seq"] = i
        negative["recorded_bytes"] = sum(len(json.dumps(e,ensure_ascii=True,allow_nan=False,separators=(",",":")).encode()) for e in negative["events"])
        results[name] = validate_trace(negative)
    return results


def run_trace_validation(root: Path,output: Path,compiler=None):
    root, output = Path(root).resolve(), Path(output).resolve()
    require(not output.is_relative_to(root),"INVALID_ARGUMENT","Output must be outside fixture tree")
    before, baseline = _hash_tree(root), verify_suite(root)
    directory = _new_directory(output)
    backend = CBackend(build_backend(directory/"backend",compiler))
    recorder = TraceRecorder()
    off, on = SimDevice(backend), SimDevice(backend,trace=recorder)
    results = []
    for checked in baseline["cases"]:
        name = checked["case_id"]
        if not checked["passed"]:
            results.append({"case_id":name,"passed":False,"python_validation":checked})
            continue
        try:
            fixture = read_fixture(root/name)
            path = directory/"packages"/name
            feeds = package_fixture(path,fixture)
            off_model, on_model = load_model(path), load_model(path,trace=recorder)
            unobserved, actual = _execute(off,off_model,feeds), _execute(on,on_model,feeds)
            toggle = actual.dtype==unobserved.dtype and actual.shape==unobserved.shape and actual.tobytes()==unobserved.tobytes()
            op,p = fixture.metadata["operation"]["name"],fixture.metadata["comparison"]
            comparisons = {key:compare_arrays(value,actual,p["atol"],p["rtol"]) for key,value in (
                ("stored_vs_traced",fixture.expected),("scalar_vs_traced",reference.execute(op,fixture.inputs)),
                ("numpy_vs_traced",oracle.execute(op,fixture.inputs)))}
            results.append({"case_id":name,"passed":toggle and all(c["passed"] for c in comparisons.values()),
                            "toggle_bitwise_equal":toggle,"comparisons":comparisons,
                            "fixture_manifest_sha256":checked["manifest_sha256"],
                            "model_manifest_sha256":on_model.package.manifest_sha256,
                            "weights_sha256":on_model.package.weights_sha256})
        except ContractError as exc:
            results.append({"case_id":name,"passed":False,"error":{"code":exc.code,"message":str(exc)}})
    final_stats = on.stats()
    off.close()
    on.close()
    chains = _chains(directory/"chains",backend,trace=recorder)
    model = load_model(directory/"chains/int32",trace=recorder)
    scenarios = _scenarios(model,backend,trace=recorder)
    probes = _observation_probes(model,backend,directory/"observation_probes")
    exported = recorder.export(directory/"trace")
    loaded = read_export(directory/"trace")
    trace_check = loaded["validation"]
    negatives = _negative_checks(loaded["trace"])
    native = run_native_tests(directory/"native_tests",compiler)
    unchanged = before==_hash_tree(root)
    count = sum(c["passed"] for c in results)
    files = [ROOT/"inference_ref"/n for n in ("tracing.py","trace_validation.py","runtime.py","sim_device.py",
             "model_package.py","memory.py","c_backend.py","device_validation.py","package_validation.py","__main__.py",
             'backend.py','c_execution.py','platform.py')]
    report = {"format":"inference-trace-validation-report","version":1,"source":"pc_runtime_trace",
              "execution":"simulated_device_c","scope":"phase1a_a7",
              "passed":count==len(results) and baseline["passed"] and all(c["passed"] for c in chains) and
                       all(c["passed"] for c in scenarios+probes) and trace_check["passed"] and
                       all(not c["passed"] for c in negatives.values()) and native["passed"] and unchanged and
                       final_stats["live_tasks"]==0 and final_stats["staging_reserved_bytes"]==0,
              "case_count":len(results),"passed_count":count,"cases":results,"chains":chains,
              "lifecycle_scenarios":scenarios,"observation_probes":probes,"trace_validation":trace_check,
              "negative_missing_node":negatives["missing_node"],"negative_controls":negatives,
              "trace_export":exported,"summary":loaded["summary"],
              "final_device_stats":final_stats,"native_tests":native,"build":backend.build,
              "fixture_files_unchanged":unchanged,"fixture_files_before_sha256":before,
              "suite_sha256":baseline["suite_sha256"],"environment":baseline["environment"],
              "python_reference_passed":baseline["passed"],"python_reference_source_sha256":baseline["source_sha256"],
              "source_sha256":{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in files}}
    write_json_exclusive(directory/"report.json",report)
    return report
