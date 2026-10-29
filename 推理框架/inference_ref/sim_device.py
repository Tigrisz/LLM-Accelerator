"""Deterministic PC device simulation. Logical ticks, actual A5/A4 C arithmetic."""

from dataclasses import asdict, dataclass, field
from math import prod
import threading
import uuid

import numpy as np

from .backend import configure,requirements_for
from .contracts import ContractError, require
from .memory import DEFAULT_BUDGET
from .runtime import LoadedModel, create_session, validate_feeds
from .tracing import TraceRecorder, mark_incomplete, observed, safe_record, trace_context, trace_id
from .platform import resolve_platform

MAX_TICKS = 100_000
TERMINAL = frozenset({"SUCCEEDED", "FAILED", "CANCELLED"})
FAULTS = frozenset({"device_error", "lost_completion", "stuck_cancel"})


def _ticks(value):
    require(type(value) is int and 0 <= value <= MAX_TICKS,
            "INVALID_ARGUMENT", "Tick count must be integer in 0..100000")


@dataclass(frozen=True)
class SimConfig:
    transfer_ticks: int = 1
    compute_ticks: int = 1
    sync_ticks: int = 1
    cancel_ticks: int = 1
    recovery_ticks: int = 1
    max_tasks: int = 16
    max_sessions: int = 16
    staging_budget: int = DEFAULT_BUDGET
    max_task_events: int = 128

    def __post_init__(self):
        for name in ("transfer_ticks", "compute_ticks", "sync_ticks", "cancel_ticks", "recovery_ticks"):
            value = getattr(self, name)
            require(type(value) is int and 1 <= value <= MAX_TICKS, "INVALID_ARGUMENT", f"Invalid {name}")
        for value in (self.max_tasks, self.max_sessions):
            require(type(value) is int and 1 <= value <= 1024, "INVALID_ARGUMENT", "Invalid record cap")
        require(type(self.staging_budget) is int and 0 <= self.staging_budget <= 2**63-1,
                "INVALID_ARGUMENT", "Invalid staging budget")
        require(type(self.max_task_events) is int and 1<=self.max_task_events<=4096,'INVALID_ARGUMENT','Invalid task history cap')


@dataclass(frozen=True)
class TaskHandle:
    device_id: str
    task_id: int


@dataclass(frozen=True)
class TaskSnapshot:
    handle: TaskHandle
    state: str
    status: str
    completed_steps: int
    quiescent: bool
    outputs_valid: bool
    terminal: bool
    execution_status: str | None
    error: str | None

    def to_dict(self):
        return asdict(self)


@dataclass(frozen=True)
class TaskEvent:
    tick: int
    state: str
    status: str
    completed_steps: int
    quiescent: bool


@dataclass(frozen=True)
class WaitResult:
    wait_status: str
    task: TaskSnapshot


@dataclass(frozen=True)
class DrainResult:
    wait_status: str
    tasks: tuple[TaskSnapshot, ...]


@dataclass
class _Task:
    handle: TaskHandle
    session: "SimSession"
    feeds: dict
    reserved_bytes: int
    fault: str | None
    state: str = "QUEUED"
    status: str = "PENDING"
    completed_steps: int = 0
    quiescent: bool = False
    outputs_valid: bool = False
    remaining: int = 0
    outputs: dict | None = None
    execution_status: str | None = None
    error: str | None = None
    events: list[TaskEvent] = field(default_factory=list)
    resource_tokens: tuple = ()
    event_token: object = None
    dropped_events: int = 0


def _copy_feeds(feeds):
    return {name: np.array(value, copy=True, order="C") for name, value in feeds.items()}


class SimSession:
    def __init__(self, device, session):
        self._device, self._session = device, session
        self._trace = session._trace
        self._trace_session_ref, self._trace_model_ref = session._trace_session_ref, session._trace_model_ref
        self._trace_device_ref = device._trace_device_ref
        self._lease = None
        self._closed = False

    def _check(self):
        self._device._check()
        require(not self._closed, "INVALID_STATE", "Session is closed")
        require(self._device._sessions.get(id(self)) is self,
                "INVALID_ARGUMENT", "Session was not registered by device")

    def submit(self, feeds, *, fault=None):
        return self._device.submit(self, feeds, fault=fault)

    def memory_info(self):
        self._check()
        return self._session.memory_info()

    def resource_info(self):return self._session.resource_info()

    @observed("device.session.close")
    def close(self):
        self._device._owner_check()
        if self._closed:
            return
        self._check()
        require(self._lease is None, "BUSY", "Task still owns session; release after quiescence")
        self._session.close()
        self._device._sessions.pop(id(self))
        self._session = None
        self._closed = True

    def __enter__(self):
        self._check()
        return self

    def __exit__(self, *_):
        self.close()


class SimDevice:
    def __init__(self, backend=None, *, registry=None,policy=None,config: SimConfig | None = None, trace=None,platform=None):
        self._platform=resolve_platform(platform) if platform is not None else None
        self._registry,self._policy=configure(backend,registry,policy)
        require(config is None or isinstance(config, SimConfig), "INVALID_ARGUMENT", "SimConfig required")
        require(trace is None or isinstance(trace,TraceRecorder),"INVALID_ARGUMENT","TraceRecorder required")
        self._trace = trace
        self._trace_device_ref = trace_id(trace,"device")
        self.backend, self.config = backend, SimConfig() if config is None else config
        self._owner = threading.get_ident()
        self._device_id = uuid.uuid4().hex
        self._next_id, self._tick, self._reserved = 1, 0, 0
        self._tasks, self._sessions = {}, {}
        self._active = None
        self._closed = False
        self._retained_platforms={}
        safe_record(trace,"device.open",context={"device_ref":self._trace_device_ref},data={"config":asdict(self.config),"execution":"selected_static_backend"})

    def _trace_task(self,task,kind):
        if self._trace is None: return
        try: self._trace_task_inner(task,kind)
        except Exception: mark_incomplete(self._trace)

    def _trace_task_inner(self,task,kind):
        inner = task.session._session
        safe_record(self._trace,kind,context={"device_ref":self._trace_device_ref,
            "session_ref":inner._trace_session_ref,"model_ref":inner._trace_model_ref,
            "task_ref":f"{task.handle.device_id}:{task.handle.task_id}","logical_tick":self._tick},
            data={"state":task.state,"status":task.status,"completed_steps":task.completed_steps,
                  "execution_status":task.execution_status,"quiescent":task.quiescent,"outputs_valid":task.outputs_valid,
                  'selected_backend':inner.selection.backend.backend_id,
                  "fault":task.fault,"reserved_bytes":task.reserved_bytes,"staging_reserved_bytes":self._reserved})

    def _owner_check(self):
        require(threading.get_ident() == self._owner, "INVALID_STATE", "Use device only from its owner thread")

    def _check(self):
        self._owner_check()
        require(not self._closed, "INVALID_STATE", "Device is closed")

    def _get(self, handle):
        self._check()
        require(isinstance(handle, TaskHandle) and handle.device_id == self._device_id and
                type(handle.task_id) is int and handle.task_id in self._tasks,
                "INVALID_ARGUMENT", "Stale, foreign or malformed task handle")
        return self._tasks[handle.task_id]

    def _event(self, task):
        if len(task.events)>=self.config.max_task_events or task.event_token is None:task.dropped_events+=1
        else:
            try:
                task.event_token.resize(0,count=len(task.events)+1)
                task.events.append(TaskEvent(self._tick,task.state,task.status,task.completed_steps,task.quiescent))
            except (ContractError,MemoryError):
                task.event_token.resize(0,count=len(task.events));task.dropped_events+=1
        if task.handle.task_id in self._tasks: self._trace_task(task,"task.state")

    def _state(self, task, state, *, status="PENDING", remaining=0):
        task.state, task.status, task.remaining = state, status, remaining
        self._event(task)

    def _finish(self, task, state, status):
        task.quiescent = True
        task.outputs_valid = state == "SUCCEEDED"
        if not task.outputs_valid:
            task.outputs = None
        self._resident(task)
        self._state(task, state, status=status)
        self._active = None
        self._release_unknown_hold()

    def _resident(self,task):
        task.resource_tokens[1].resize(task.reserved_bytes,resident_bytes=sum(v.nbytes for v in task.feeds.values())+
            sum(v.nbytes for v in (task.outputs or {}).values()))

    def _release_unknown_hold(self):
        if any(t.state in {'QUARANTINED','RECOVERING'} for t in self._tasks.values()):return
        for platform in self._retained_platforms.values():platform._release_retained_resources(self)
        self._retained_platforms.clear()

    def _quarantine(self, task, message):
        task.quiescent, task.outputs_valid, task.outputs = False, False, None
        task.error = message
        self._resident(task)
        platform=task.session._session.platform
        self._retained_platforms[platform.platform_id]=platform
        platform._retain_resources(self,'device_task_unknown')
        self._state(task, "QUARANTINED", status="DEVICE_ERROR")

    @observed("device.query")
    def query_support(self, model):
        self._check()
        require(isinstance(model, LoadedModel), "INVALID_ARGUMENT", "LoadedModel required")
        selected=self._registry.select(requirements_for(model.package,model.plan),self._policy)
        return {**selected.to_dict(),'backend':'simulated_device','operators':sorted({n.op for n in model.package.nodes})}

    @observed("device.create_session")
    def create_session(self, model, *, memory_budget=DEFAULT_BUDGET):
        self._check()
        require(len(self._sessions) < self.config.max_sessions, "RESOURCE_LIMIT", "Session cap reached")
        inner = create_session(model,registry=self._registry,policy=self._policy,memory_budget=memory_budget,trace=self._trace,platform=self._platform)
        session = SimSession(self, inner)
        self._sessions[id(session)] = session
        return session

    @observed("device.submit")
    def submit(self, session, feeds, *, fault=None):
        self._check()
        require(isinstance(session, SimSession) and session._device is self,
                "INVALID_ARGUMENT", "Foreign session")
        session._check()
        require(session._lease is None, "BUSY", "Session has an unreleased task")
        require(fault is None or isinstance(fault, str) and fault in FAULTS,
                "INVALID_ARGUMENT", "Unknown fault injection")
        package = session._session._model.package
        validate_feeds(package, feeds)
        reserve = sum(value.nbytes for value in feeds.values()) + sum(
            prod(package.tensor(name).spec.shape)*4 for name in package.outputs)
        require(len(self._tasks) < self.config.max_tasks and self._reserved + reserve <= self.config.staging_budget,
                "RESOURCE_LIMIT", "Task cap or staging budget exceeded")
        require(self._next_id < 2**64, "RESOURCE_LIMIT", "Task identifiers exhausted")
        tokens=[];event_token=None
        try:
            ledger=session._session.platform.ledger
            tokens.append(ledger.reserve('task_records',0,label='task_record'))
            tokens.append(ledger.reserve('task_staging',reserve,label='task_input_output'))
            try:event_token=ledger.reserve('task_events',0,count=0,label='task_history')
            except ContractError:pass
            snapshot = _copy_feeds(feeds)
            tokens[1].resize(reserve,resident_bytes=sum(v.nbytes for v in snapshot.values()))
            handle = TaskHandle(self._device_id, self._next_id)
            task = _Task(handle, session, snapshot, reserve, fault,resource_tokens=tuple(tokens),event_token=event_token)
            self._event(task)
            self._tasks[handle.task_id] = task
        except BaseException as exc:
            for token in tokens:token.close()
            if event_token is not None:event_token.close()
            if isinstance(exc,MemoryError):raise ContractError("RESOURCE_LIMIT", "Task snapshot/record allocation failed") from exc
            raise
        session._lease = handle.task_id
        self._reserved += reserve
        self._next_id += 1
        self._trace_task(task,"task.accept")
        return handle

    @observed("device.poll")
    def poll(self, handle):
        t = self._get(handle)
        return TaskSnapshot(t.handle, t.state, t.status, t.completed_steps, t.quiescent,
                            t.outputs_valid, t.state in TERMINAL, t.execution_status, t.error)

    def events(self, handle):
        return tuple(self._get(handle).events)

    @observed("device.result")
    def result(self, handle):
        t = self._get(handle)
        require(t.state == "SUCCEEDED" and t.quiescent and t.outputs_valid,
                "INVALID_STATE", "Output not completed, visible and successful")
        try:
            return {name:value.copy() for name, value in t.outputs.items()}
        except MemoryError as exc:
            raise ContractError("RESOURCE_LIMIT", "Output copy allocation failed") from exc

    @observed("device.release")
    def release(self, handle):
        t = self._get(handle)
        require(t.state in TERMINAL and t.quiescent, "BUSY", "Task is not confirmed quiescent")
        self._reserved -= t.reserved_bytes
        t.session._lease = None
        self._trace_task(t,"task.release")
        del self._tasks[handle.task_id]
        t.feeds.clear();t.outputs=None;t.events.clear()
        for token in t.resource_tokens:token.close()
        if t.event_token is not None:t.event_token.close()

    @observed("device.cancel")
    def cancel(self, handle):
        t = self._get(handle)
        if t.state not in TERMINAL | {"CANCEL_REQUESTED", "QUARANTINED", "RECOVERING"}:
            self._state(t, "CANCEL_REQUESTED", status="CANCEL_REQUESTED", remaining=self.config.cancel_ticks)
        return self.poll(handle)

    @observed("device.recover")
    def recover(self, handle):
        t = self._get(handle)
        require(t.state == "QUARANTINED", "INVALID_STATE", "Recovery requires quarantined task")
        self._state(t, "RECOVERING", remaining=self.config.recovery_ticks)
        return self.poll(handle)

    def _execute(self, task):
        with trace_context(self._trace,device_ref=self._trace_device_ref,
                           task_ref=f"{task.handle.device_id}:{task.handle.task_id}",logical_tick=self._tick):
            self._execute_inner(task)

    def _execute_inner(self, task):
        inner = task.session._session
        prior_execution = inner.execution_id
        try:
            task.outputs = inner.run(task.feeds)
            task.resource_tokens[1].resize(task.reserved_bytes,resident_bytes=sum(v.nbytes for v in task.feeds.values())+sum(v.nbytes for v in task.outputs.values()))
            task.completed_steps = inner.last_result["completed_steps"]
            task.execution_status = "OK"
        except ContractError as exc:
            if inner.execution_id == prior_execution:
                self._quarantine(task, f"Execution rejected before run entry: {exc.code}: {exc}")
                return
            task.completed_steps = inner.last_result["completed_steps"]
            task.execution_status, task.error = exc.code, str(exc)
        except BaseException as exc:
            if inner.execution_id != prior_execution:
                progress = inner.last_result
                task.completed_steps = progress["completed_steps"]
                task.execution_status = progress["status"]
            self._quarantine(task, f"Unexpected execution exception: {type(exc).__name__}: {exc}")
            if not isinstance(exc, Exception):
                raise
            return
        if task.fault == "lost_completion":
            self._quarantine(task, "Simulated loss of completion/quiescence confirmation")
        elif task.fault == "device_error":
            task.error = "Simulated acknowledged device error"
            self._finish(task, "FAILED", "DEVICE_ERROR")
        elif task.execution_status != "OK":
            self._finish(task, "FAILED", task.execution_status)
        else:
            self._state(task, "SYNCING", remaining=self.config.sync_ticks)

    @observed("device.advance")
    def advance(self, ticks=1):
        self._check()
        _ticks(ticks)
        for _ in range(ticks):
            self._tick += 1
            if self._active is None:
                task = next((t for t in self._tasks.values() if t.state not in TERMINAL), None)
                if task is None:
                    continue
                self._active = task.handle.task_id
                if task.state == "QUEUED":
                    self._state(task, "TRANSFERRING", remaining=self.config.transfer_ticks)
                    continue
            task = self._tasks[self._active]
            if task.state == "QUARANTINED":
                continue
            task.remaining -= 1
            if task.remaining > 0:
                continue
            if task.state == "TRANSFERRING":
                self._state(task, "RUNNING", remaining=self.config.compute_ticks)
            elif task.state == "RUNNING":
                self._execute(task)
            elif task.state == "SYNCING":
                self._finish(task, "SUCCEEDED", "OK")
            elif task.state == "CANCEL_REQUESTED":
                if task.fault == "stuck_cancel":
                    self._quarantine(task, "Simulated loss of cancellation acknowledgement")
                else:
                    self._finish(task, "CANCELLED", "CANCELLED")
            elif task.state == "RECOVERING":
                try: task.session._session.recover()
                except Exception as exc: self._quarantine(task,f'Backend recovery unconfirmed: {exc}')
                else: self._finish(task, "FAILED", "DEVICE_ERROR")

    @observed("device.wait")
    def wait(self, handle, *, timeout_ticks=0):
        self._get(handle)
        _ticks(timeout_ticks)
        for step in range(timeout_ticks+1):
            snapshot = self.poll(handle)
            if snapshot.terminal and snapshot.quiescent:
                return WaitResult("COMPLETED", snapshot)
            if snapshot.state == "QUARANTINED":
                return WaitResult("DEVICE_ERROR", snapshot)
            if step < timeout_ticks:
                self.advance()
        return WaitResult("TIMEOUT", snapshot)

    @observed("device.drain")
    def drain(self, *, timeout_ticks=0):
        self._check()
        _ticks(timeout_ticks)
        for step in range(timeout_ticks+1):
            snapshots = tuple(self.poll(t.handle) for t in self._tasks.values())
            if all(t.terminal and t.quiescent for t in snapshots):
                return DrainResult("COMPLETED", snapshots)
            if any(t.state == "QUARANTINED" for t in snapshots):
                return DrainResult("DEVICE_ERROR", snapshots)
            if step < timeout_ticks:
                self.advance()
        return DrainResult("TIMEOUT", snapshots)

    @observed("device.quiesce")
    def quiesce(self, *, timeout_ticks=0):
        self._check()
        _ticks(timeout_ticks)
        for task in self._tasks.values():
            self.cancel(task.handle)
        return self.drain(timeout_ticks=timeout_ticks)

    def stats(self):
        self._check()
        return {"logical_tick": self._tick, "live_tasks": len(self._tasks),
                "live_sessions": len(self._sessions), "staging_reserved_bytes": self._reserved,
                "active_task_id": self._active}

    def resource_info(self):
        self._check()
        ledgers={id(s._session.platform.ledger):s._session.platform.ledger for s in self._sessions.values()}
        if self._platform is not None:ledgers[id(self._platform.ledger)]=self._platform.ledger
        return {'ledgers':[ledger.snapshot() for ledger in ledgers.values()],
            'task_history_events':sum(len(t.events) for t in self._tasks.values()),
            'dropped_task_events':sum(t.dropped_events for t in self._tasks.values())}

    @observed("device.close")
    def close(self):
        self._owner_check()
        if self._closed:
            return
        require(not self._tasks, "BUSY", "Release all confirmed-quiescent tasks before close")
        for session in list(self._sessions.values()):
            session.close()
        self.backend = None
        self._registry=self._policy=None
        self._closed = True

    def __enter__(self):
        self._check()
        return self

    def __exit__(self, *_):
        self.close()
