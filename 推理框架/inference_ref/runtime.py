"""PC model loading and static arena session; all operator arithmetic is C."""

from dataclasses import dataclass,field,replace
from math import prod
from pathlib import Path

import numpy as np
import weakref

from .backend import BoundChain,ChainResult,STATUSES,configure,requirements_for
from .contracts import ContractError, require
from .memory import DEFAULT_BUDGET, MemoryPlan, plan_memory,validate_plan_addressing
from .model_package import ModelPackage, read_package
from .tracing import TraceRecorder, host_start, mark_incomplete, observed, phase, safe_record, trace_context, trace_id
from .platform import resolve_platform
from .resources import prepare_resources


class Arena:
    def __init__(self, size: int, alignment: int,*,platform=None,trace=None):
        self._platform=resolve_platform(platform)
        self._trace=trace
        self._block=self._platform.allocate(size,alignment,trace=trace)

    @property
    def backing(self): return self._block.backing

    @property
    def data(self): return self._block.data

    @property
    def address(self):
        return self._block.address

    def close(self):
        if not self._block.released:
            with phase(self._trace,'platform.release'): self._block.close()


class _ModelLifetime:
    def __init__(self): self.sessions,self.closed,self.closing=weakref.WeakSet(),False,False


@dataclass(frozen=True)
class LoadedModel:
    package: ModelPackage
    plan: MemoryPlan
    _weights: Arena
    trace: TraceRecorder | None = None
    trace_model_id: str | None = None
    platform: object = None
    _lifetime: object = field(default_factory=_ModelLifetime,compare=False,repr=False)

    def close(self):
        if self._lifetime.closed: return
        require(not self._lifetime.sessions,'BUSY','Sessions still borrow model weights')
        self._lifetime.closing=True
        self._weights.close()
        self._lifetime.closed,self._lifetime.closing=True,False
        safe_record(self.trace,'model.close',context={'model_ref':self.trace_model_id},data={'status':'OK'})


def _summary(package: ModelPackage, plan: MemoryPlan) -> dict:
    return {"format": "inference-model-inspection", "version": 1,
            "model_id": package.model_id, "tensor_count": len(package.tensors),
            "node_count": len(package.nodes), "inputs": list(package.inputs), "outputs": list(package.outputs),
            "manifest_sha256": package.manifest_sha256, "weights_sha256": package.weights_sha256,
            "memory_plan": plan.to_dict()}


def inspect_model(path: Path, *, memory_budget=DEFAULT_BUDGET,platform=None) -> dict:
    package = read_package(path,platform=platform)
    return _summary(package, plan_memory(package, memory_budget=memory_budget))


def _load_model(path: Path, *, memory_budget=DEFAULT_BUDGET,platform=None,trace=None) -> LoadedModel:
    platform=resolve_platform(platform)
    package = read_package(path,platform=platform,trace=trace)
    plan = plan_memory(package, memory_budget=memory_budget)
    validate_plan_addressing(plan,address_bits=platform.allocator.pointer_bits)
    weights = Arena(plan.weight_bytes, plan.alignment,platform=platform,trace=trace)
    try:
        for t in package.tensors:
            if t.role == "constant":
                p = plan.placement(t.id)
                storage = np.ndarray(t.spec.storage_shape, dtype=t.spec.dtype, buffer=weights.data, offset=p.offset)
                storage[:] = package.constant_array(t.id)
        weights.data.flags.writeable = False
        weights.backing.flags.writeable = False
        return LoadedModel(package,plan,weights,platform=platform)
    except BaseException:
        weights.close()
        raise


def _observe_model(model, recorder, ref):
    if recorder is None: return
    try:
        context = {"model_ref":ref}
        package, plan = model.package, model.plan
        safe_record(recorder,"model.loaded",context=context,data={"model_id":package.model_id,
            "manifest_sha256":package.manifest_sha256,"weights_sha256":package.weights_sha256,
            "inputs":list(package.inputs),"outputs":list(package.outputs),"node_count":len(package.nodes),
            'platform_id':model.platform.platform_id if model.platform is not None else None})
        safe_record(recorder,"memory.plan",context=context,data={k:v for k,v in plan.to_dict().items() if k!="placements"})
        for t in package.tensors:
            safe_record(recorder,"model.tensor",context=context,data={"tensor_id":t.id,"role":t.role,
                "dtype":t.spec.dtype,"shape":list(t.spec.shape),"storage_shape":list(t.spec.storage_shape),
                "byte_length":t.spec.byte_length,"layout":t.spec.layout})
        for p in plan.placements:
            safe_record(recorder,"memory.placement",context=context,data=dict(vars(p)))
        for index,n in enumerate(package.nodes):
            safe_record(recorder,"model.node",context=context,data={"index":index,"node_id":n.id,
                "op":n.op,"inputs":dict(n.inputs),"output":n.output})
    except Exception: mark_incomplete(recorder)


def load_model(path: Path, *, memory_budget=DEFAULT_BUDGET, trace=None,platform=None) -> LoadedModel:
    require(trace is None or isinstance(trace,TraceRecorder),"INVALID_ARGUMENT","TraceRecorder required")
    ref, start = trace_id(trace,"model"), host_start(trace)
    safe_record(trace,"model.load.begin",context={"model_ref":ref})
    status = "OK"
    try:
        with trace_context(trace,model_ref=ref):
            model = _load_model(path,memory_budget=memory_budget,platform=platform,trace=trace)
            model = replace(model,trace=trace,trace_model_id=ref)
            _observe_model(model,trace,ref)
            return model
    except BaseException as exc:
        status = getattr(exc,"code",type(exc).__name__)
        raise
    finally:
        safe_record(trace,"model.load.end",context={"model_ref":ref},data={"status":status},start_ns=start)


def validate_feeds(package: ModelPackage, feeds: dict[str, np.ndarray]) -> None:
    """No writes/ownership changes; shared admission check for A5 and A6."""
    require(isinstance(feeds, dict) and set(feeds) == set(package.inputs),
            "INVALID_ARGUMENT", "Input bindings mismatch")
    for name in package.inputs:
        spec, value = package.tensor(name).spec, feeds[name]
        require(isinstance(value, np.ndarray) and value.dtype == np.dtype(spec.dtype),
                "INVALID_ARGUMENT", f"{name}: exact native dtype required")
        require(value.shape == spec.shape, "INVALID_SHAPE", f"{name}: input shape mismatch")
        require(bool(np.isfinite(value).all()), "NONFINITE", f"{name}: nonfinite input")


class Session:
    """Synchronous reusable buffers; no token/cache semantics or device state."""
    def __init__(self, model: LoadedModel, backend=None, *, registry=None, policy=None, memory_budget=DEFAULT_BUDGET, trace=None,platform=None):
        require(isinstance(model,LoadedModel),'INVALID_ARGUMENT','LoadedModel required')
        require(not model._lifetime.closed and not model._lifetime.closing,'INVALID_STATE','Model is closed or closing')
        self._platform=resolve_platform(model.platform if platform is None else platform)
        require(type(memory_budget) is int and 0 <= memory_budget <= 2**63-1,
                "INVALID_ARGUMENT", "Invalid session budget")
        require(model.plan.total_bytes <= memory_budget, "RESOURCE_LIMIT", "Session arena budget exceeded")
        require(trace is None or isinstance(trace,TraceRecorder),"INVALID_ARGUMENT","TraceRecorder required")
        self._trace = model.trace if trace is None else trace
        self._trace_model_ref = model.trace_model_id if self._trace is model.trace else trace_id(self._trace,"model")
        if self._trace is not model.trace: _observe_model(model,self._trace,self._trace_model_ref)
        self._trace_session_ref = trace_id(self._trace,"session")
        with trace_context(self._trace,model_ref=self._trace_model_ref,session_ref=self._trace_session_ref),phase(self._trace,'backend.select'):
            registry,policy=configure(backend,registry,policy)
            self.selection=registry.select(requirements_for(model.package,model.plan),policy)
        if self._trace is not None:
            try:
                safe_record(self._trace,'backend.selection',context={'model_ref':self._trace_model_ref,'session_ref':self._trace_session_ref},
                            data={**self.selection.to_dict(),'allow_fallback':policy.allow_fallback,'fallbacks':list(policy.fallbacks)})
            except Exception: mark_incomplete(self._trace)
        require(self.selection.supported,'UNSUPPORTED','No permitted backend supports the complete static chain')
        self._model,self._backend=model,self.selection.backend
        validate_plan_addressing(model.plan,address_bits=self._platform.allocator.pointer_bits)
        self._closed, self._running,self._execution_unknown,self._closing = False, False,False,False
        self._backend_unknown,self._sync_unknown=False,False
        self._binding_closed=False
        self._execution_id = 0
        self._last_result = {"status": "NOT_RUN", "completed_steps": 0}
        self._views = {}
        self._activation=self._workspace=self._binding=None
        self._resource_record=None
        try:
            self._resource_record=self._platform.ledger.reserve('session_records',0,label='session')
            self._activation=Arena(model.plan.activation_bytes,model.plan.alignment,platform=self._platform,trace=self._trace)
            self._workspace=Arena(model.plan.workspace_bytes,model.plan.alignment,platform=self._platform,trace=self._trace)
            for t in model.package.tensors:
                p = model.plan.placement(t.id)
                arena = model._weights if p.arena == "weights" else self._activation
                view = np.ndarray(t.spec.storage_shape, dtype=t.spec.dtype, buffer=arena.data, offset=p.offset)
                if t.role == "constant": view.flags.writeable = False
                self._views[t.id] = view
            with prepare_resources(self._platform.ledger):
                self._binding=self._backend.prepare(model.package,model.plan,self._views,self._workspace.data,profile=self._trace is not None)
            require(isinstance(self._binding,BoundChain),'INVALID_ARGUMENT','Backend returned invalid binding')
        except BaseException:
            if isinstance(self._binding,BoundChain): self._binding.close()
            self._views.clear()
            for arena in (self._activation,self._workspace):
                if arena is not None: arena.close()
            if self._resource_record is not None:self._resource_record.close()
            raise
        model._lifetime.sessions.add(self)
        # Compatibility for existing C ABI fault-injection probes, never used for dispatch.
        self._calls=getattr(self._binding,'calls',None)
        if self._trace is not None and not self._binding.profiled: mark_incomplete(self._trace)
        safe_record(self._trace,"session.open",context={"model_ref":self._trace_model_ref,"session_ref":self._trace_session_ref},
            data={"actual_backing_bytes":model.plan.total_bytes,"profiled":self._binding.profiled,
                  "profile_records_bytes":self._binding.profile_records_bytes,
                  'selected_backend':self._backend.backend_id,'execution':self._backend.execution_kind,'trace_kind':self._backend.trace_kind,
                  'platform_api':1,'platform_id':self._platform.platform_id,'pointer_bits':self._platform.allocator.pointer_bits})

    def _synchronize(self,direction):
        with phase(self._trace,'platform.sync.'+direction):
            blocks=(self._model._weights._block,self._activation._block,self._workspace._block)
            try:
                method=self._platform.synchronizer.for_device if direction=='to_backend' else self._platform.synchronizer.for_cpu
                require(method(blocks) is True,'DEVICE_ERROR','Synchronization not confirmed')
            except BaseException as exc:
                self._execution_unknown,self._sync_unknown=True,True
                self._hold_resources('synchronization_unknown')
                self._last_result['status']='DEVICE_ERROR'
                if isinstance(exc,Exception): raise RuntimeError('Platform synchronization state is unknown') from exc
                raise

    @property
    def platform(self): return self._platform

    def _hold_resources(self,reason):
        self._platform._retain_resources(self,reason)
        safe_record(self._trace,'platform.retention',context={'session_ref':self._trace_session_ref,'model_ref':self._trace_model_ref},
                    data={'status':'OK','action':'hold','reason':reason,'platform_id':self._platform.platform_id})

    def _release_hold(self):
        self._platform._release_retained_resources(self)
        safe_record(self._trace,'platform.retention',context={'session_ref':self._trace_session_ref,'model_ref':self._trace_model_ref},
                    data={'status':'OK','action':'release','platform_id':self._platform.platform_id})

    def _observe_profiles(self):
        if not self._binding.profiled: return
        try:
            rows=self._binding.observe_nodes()
            if len(rows)!=len(self._model.package.nodes): mark_incomplete(self._trace)
            for row in rows:
                safe_record(self._trace,self._backend.trace_kind+'.node',data={**row,'selected_backend':self._backend.backend_id})
        except Exception: mark_incomplete(self._trace)

    @property
    def last_result(self):
        return dict(self._last_result)

    @property
    def execution_id(self):
        """Changes only when a new run actually enters this session."""
        return self._execution_id

    def memory_info(self) -> dict:
        require(not self._closed, "INVALID_STATE", "Session is closed")
        require(not self._closing,'BUSY','Session close is incomplete')
        return {"arena_addresses": {"weights": self._model._weights.address,
                                   "activations": self._activation.address,
                                   "workspace": self._workspace.address},
                "total_backing_bytes": self._model._weights.backing.nbytes +
                                       self._activation.backing.nbytes + self._workspace.backing.nbytes}

    def resource_info(self):
        return {'ledger':self._platform.ledger.snapshot(),'c_metadata_tracking':getattr(self._backend,'resource_tracking','external_not_declared'),
                'closed':self._closed,'closing':self._closing,'execution_unknown':self._execution_unknown}

    def run(self, feeds: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
        require(not self._closed, "INVALID_STATE", "Session is closed")
        require(not self._closing,'BUSY','Session close is incomplete')
        require(not self._running, "BUSY", "Session is already running")
        require(not self._execution_unknown,'BUSY','Backend must confirm quiescence before reuse')
        self._running = True
        try:
            self._last_result = {"status": "INVALID_ARGUMENT", "completed_steps": 0}
            self._execution_id += 1
            with trace_context(self._trace,model_ref=self._trace_model_ref,session_ref=self._trace_session_ref,
                               run_ref=f"{self._trace_session_ref}:{self._execution_id}",selected_backend=self._backend.backend_id,
                               platform_id=self._platform.platform_id):
                start, outcome = host_start(self._trace), "OK"
                safe_record(self._trace,"run.begin",data={"execution_id":self._execution_id,"node_count":len(self._model.package.nodes)})
                try:
                    package = self._model.package
                    with phase(self._trace,"run.validate"):
                        validate_feeds(package, feeds)
                    with phase(self._trace,"run.prepare"):
                        self._activation.data.fill(0)
                        for name in package.inputs:
                            spec = package.tensor(name).spec
                            self._views[name][tuple(slice(0, d) for d in spec.shape)] = feeds[name]
                    self._synchronize('to_backend')
                    chain_start = host_start(self._trace)
                    try:
                        result=self._binding.execute()
                        if not (isinstance(result,ChainResult) and type(result.status) is str and result.status in STATUSES and
                                type(result.completed_steps) is int and 0<=result.completed_steps<=len(package.nodes) and
                                result.quiescent is True and (result.status!='OK' or result.completed_steps==len(package.nodes))):
                            raise RuntimeError('Malformed or non-quiescent backend result')
                    except BaseException as exc:
                        self._execution_unknown=True
                        self._backend_unknown=True
                        self._hold_resources('backend_execution_unknown')
                        self._last_result={'status':'DEVICE_ERROR','completed_steps':0}
                        mark_incomplete(self._trace)
                        safe_record(self._trace,'backend.error',data={'status':'DEVICE_ERROR','selected_backend':self._backend.backend_id})
                        if isinstance(exc,Exception): raise RuntimeError('Backend execution state is unknown') from exc
                        raise
                    status=result.status
                    self._last_result = {"status":status,"completed_steps":result.completed_steps}
                    safe_record(self._trace,self._backend.trace_kind+'.chain',data={"status":status,"completed_steps":result.completed_steps,
                        "node_count":len(package.nodes),"profiled":self._binding.profiled,'selected_backend':self._backend.backend_id},start_ns=chain_start)
                    self._observe_profiles()
                    require(status=="OK",status,f"Backend chain failed after {result.completed_steps} nodes: {status}")
                    self._synchronize('to_cpu')
                    with phase(self._trace,"run.outputs"):
                        outputs = {name:self._views[name][tuple(slice(0,d) for d in package.tensor(name).spec.shape)].copy()
                                   for name in package.outputs}
                    return outputs
                except BaseException as exc:
                    outcome = getattr(exc,"code",type(exc).__name__)
                    raise
                finally:
                    safe_record(self._trace,"run.end",data={"status":outcome,"completed_steps":self._last_result["completed_steps"]},start_ns=start)
        except ContractError as exc:
            self._last_result["status"] = exc.code
            raise
        finally:
            self._running = False

    @observed("session.close")
    def close(self):
        require(not self._running, "BUSY", "Cannot close running session")
        require(not self._execution_unknown,'BUSY','Cannot release arenas with unknown backend execution')
        if not self._closed:
            self._closing=True
            self._hold_resources('close_incomplete')
            self._calls=None
            if not self._binding_closed:
                self._binding.close()
                self._binding_closed=True
            self._calls = None
            self._views.clear()
            self._activation.close(); self._workspace.close()
            self._model._lifetime.sessions.discard(self)
            self._binding=None
            self._activation = self._workspace = None
            self._model = self._backend = None
            self._closed = True
            self._resource_record.close()
            self._release_hold()

    @observed('session.recover')
    def recover(self):
        require(not self._closed and not self._running,'INVALID_STATE','Recovery needs an idle open session')
        if self._execution_unknown:
            if self._backend_unknown:
                require(self._binding.recover() is True,'DEVICE_ERROR','Backend did not confirm quiescence')
            if self._sync_unknown:
                require(self._platform.synchronizer.recover() is True,'DEVICE_ERROR','Platform synchronization not quiescent')
            self._execution_unknown=False
            self._backend_unknown=self._sync_unknown=False
            if not self._closing: self._release_hold()

    def __enter__(self):
        require(not self._closed, "INVALID_STATE", "Session is closed")
        return self

    def __exit__(self, *_):
        self.close()


def create_session(model: LoadedModel, backend=None, *, registry=None,policy=None,memory_budget=DEFAULT_BUDGET, trace=None,platform=None) -> Session:
    return Session(model,backend,registry=registry,policy=policy,memory_budget=memory_budget,trace=trace,platform=platform)
