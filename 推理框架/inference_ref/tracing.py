"""Bounded metadata-only observation, independent host/CPU/logical clocks."""

from collections import Counter, defaultdict
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
import hashlib
import json
from pathlib import Path
import threading
import time
import uuid

from .contracts import ContractError, require
from .platform import ClockSource,PCClock,U64_MAX
from .resources import ResourceLedger


def _encode(value):
    return json.dumps(value, ensure_ascii=True, allow_nan=False, separators=(",", ":")).encode("utf-8")


def _uint(value):
    return type(value) is int and value >= 0


class TraceRecorder:
    def __init__(self, *, max_events=16384, max_bytes=16*1024*1024,clock=None,ledger=None):
        require(type(max_events) is int and 0 <= max_events <= 1_000_000 and
                type(max_bytes) is int and 0 <= max_bytes <= 64*1024*1024,
                "INVALID_ARGUMENT", "Invalid trace budget")
        self.max_events, self.max_bytes = max_events, max_bytes
        self.trace_id = uuid.uuid4().hex
        self._clock=PCClock() if clock is None else clock
        require(isinstance(self._clock,ClockSource) and self._clock.domain in {'host_perf_counter','host_monotonic'} and
                self._clock.unit=='ns','INVALID_ARGUMENT','Host monotonic ns ClockSource required')
        self._origin,self._last_clock_ns=None,None
        self._events, self._bytes, self._dropped, self._errors, self._ids = [], 0, 0, 0, 0
        self._lock = threading.RLock()
        self.ledger=ResourceLedger(budget_bytes=max_bytes) if ledger is None else ledger
        require(isinstance(self.ledger,ResourceLedger),'INVALID_ARGUMENT','ResourceLedger required')
        self._ticket=None;self._closed=False
        try:self._ticket=self.ledger.reserve('trace',0,count=0,label='trace_events')
        except ContractError:self._errors+=1
        self._context = ContextVar(f"trace_{self.trace_id}", default={})
        try: self.clock_now_ns()
        except Exception: self.note_failure()

    def clock_now_ns(self):
        with self._lock:
            now=self._clock.now_ns()
            require(_uint(now) and now<=U64_MAX and (self._last_clock_ns is None or now>=self._last_clock_ns),
                    'INVALID_ARGUMENT','Clock unavailable or non-monotonic')
            if self._origin is None: self._origin=now
            self._last_clock_ns=now
            return now

    def new_id(self, prefix):
        with self._lock:
            self._ids += 1
            return f"{prefix}:{self._ids}"

    @contextmanager
    def context(self, **values):
        token = self._context.set({**self._context.get(), **{k:v for k,v in values.items() if v is not None}})
        try:
            yield
        finally:
            self._context.reset(token)

    def note_failure(self):
        with self._lock:
            self._errors += 1

    def record(self, kind, *, data=None, context=None, start_ns=None):
        require(isinstance(kind,str) and 0 < len(kind) <= 80 and
                (data is None or isinstance(data,dict)) and (context is None or isinstance(context,dict)),
                "INVALID_ARGUMENT", "Invalid trace event")
        with self._lock:
            require(not self._closed,'INVALID_STATE','Trace recorder closed')
            try: now = self.clock_now_ns()
            except Exception:
                self.note_failure()
                raise
            event = {"seq":len(self._events)+1, "kind":kind, "t_ns":max(0,now-self._origin),
                     "context":{**self._context.get(), **(context or {})}, "data":data or {}}
            if start_ns is not None:
                require(type(start_ns) is int and self._origin <= start_ns <= now,
                        "INVALID_ARGUMENT", "Invalid host span start")
                event.update(start_ns=start_ns-self._origin, duration_ns=now-start_ns, duration_clock=self._clock.domain)
            try:
                raw = _encode(event)
            except (TypeError,ValueError,RecursionError) as exc:
                raise ContractError("INVALID_ARGUMENT", "Event must contain finite JSON metadata only") from exc
            if len(self._events) >= self.max_events or self._bytes+len(raw) > self.max_bytes:
                self._dropped += 1
                return
            if self._ticket is None:self._dropped+=1;return
            try:
                self._ticket.resize(self._bytes+len(raw),resident_bytes=self._bytes+len(raw),count=len(self._events)+1)
                self._events.append(json.loads(raw))
            except (ContractError,MemoryError):
                self._ticket.resize(self._bytes,resident_bytes=self._bytes,count=len(self._events))
                self._dropped+=1;return
            self._bytes += len(raw)

    def close(self):
        with self._lock:
            if not self._closed:
                self._closed=True;self._events.clear();self._bytes=0
                if self._ticket is not None:self._ticket.close()

    def resource_info(self):return self.ledger.snapshot()

    def snapshot(self):
        with self._lock:
            require(not self._closed,'INVALID_STATE','Trace recorder closed; export before releasing cache')
            return {"format":"inference-runtime-trace", "version":1, "trace_id":self.trace_id,
                    "clock":self._clock.domain+'_ns_relative', "complete":self._dropped==0 and self._errors==0,
                    "max_events":self.max_events,"max_bytes":self.max_bytes,"recorded_bytes":self._bytes,
                    "dropped_events":self._dropped,"recording_errors":self._errors,
                    "events":json.loads(_encode(self._events))}

    def summary(self):
        return summarize(self.snapshot())

    def export(self, path):
        document = self.snapshot()
        files = {"trace.json":document, "timeline.json":timeline(document), "summary.json":summarize(document)}
        try:
            root = Path(path).resolve()
            root.mkdir(parents=True,exist_ok=False)
            metadata = {}
            for name,value in files.items():
                raw = _encode(value)+b"\n"
                with (root/name).open("xb") as stream: stream.write(raw)
                metadata[name] = {"byte_length":len(raw),"sha256":hashlib.sha256(raw).hexdigest()}
            with (root/"manifest.json").open("xb") as stream:
                stream.write(_encode({"format":"inference-trace-export","version":1,"files":metadata})+b"\n")
        except FileExistsError as exc:
            raise ContractError("ALREADY_EXISTS",str(exc)) from exc
        except (OSError,ValueError,TypeError) as exc:
            if isinstance(exc,ContractError): raise
            raise ContractError("IO_ERROR",str(exc)) from exc
        return {"path":str(root),"complete":document["complete"],"files":metadata}


def safe_record(recorder, kind, **kwargs):
    if recorder is None: return
    try:
        recorder.record(kind, **kwargs)
    except Exception:
        try: recorder.note_failure()
        except Exception: pass


def mark_incomplete(recorder):
    if recorder is not None:
        try: recorder.note_failure()
        except Exception: pass


def trace_id(recorder,prefix):
    if recorder is None: return None
    try: return recorder.new_id(prefix)
    except Exception:
        try: recorder.note_failure()
        except Exception: pass
        return None


@contextmanager
def trace_context(recorder,**context):
    if recorder is None:
        yield
        return
    token = None
    try: token = recorder._context.set({**recorder._context.get(), **{k:v for k,v in context.items() if v is not None}})
    except Exception: mark_incomplete(recorder)
    try:
        yield
    finally:
        if token is not None:
            try: recorder._context.reset(token)
            except Exception: mark_incomplete(recorder)


def host_start(recorder):
    try: return recorder.clock_now_ns() if recorder is not None else None
    except Exception:
        mark_incomplete(recorder)
        return None


@contextmanager
def phase(recorder,kind):
    start,status = host_start(recorder),"OK"
    try:
        yield
    except BaseException as exc:
        status = getattr(exc,"code",type(exc).__name__)
        raise
    finally:
        safe_record(recorder,kind,data={"status":status},start_ns=start)


def observed(kind):
    """Observe an API outcome; never serialize arbitrary arguments/array values."""
    def decorate(fn):
        @wraps(fn)
        def wrapped(self,*args,**kwargs):
            recorder = getattr(self,"_trace",None)
            if recorder is None: return fn(self,*args,**kwargs)
            start, tick, context, data = host_start(recorder), None, {}, {}
            try:
                tick = getattr(self,"_tick",None)
                context["device_ref"] = getattr(self,"_trace_device_ref",None)
                for source in (self, args[0] if args else None):
                    for key,attribute in (("session_ref","_trace_session_ref"),("model_ref","_trace_model_ref")):
                        if getattr(source,attribute,None) is not None: context[key] = getattr(source,attribute)
                if args and hasattr(args[0],"device_id") and hasattr(args[0],"task_id"):
                    context["task_ref"] = f"{args[0].device_id}:{args[0].task_id}"
            except Exception: mark_incomplete(recorder)
            try:
                value = fn(self,*args,**kwargs)
                data["status"] = "OK"
                try:
                    if hasattr(value,"wait_status"): data["wait_status"] = value.wait_status
                    if hasattr(value,"state"): data["state"] = value.state
                    if hasattr(value,"device_id") and hasattr(value,"task_id"):
                        context["task_ref"] = f"{value.device_id}:{value.task_id}"
                except Exception: mark_incomplete(recorder)
                return value
            except BaseException as exc:
                data["status"] = getattr(exc,"code",type(exc).__name__)
                raise
            finally:
                try:
                    if tick is not None: data["logical_elapsed_ticks"] = self._tick-tick
                    safe_record(recorder,kind,data=data,context={k:v for k,v in context.items() if v is not None},start_ns=start)
                except Exception: mark_incomplete(recorder)
        return wrapped
    return decorate


def summarize(document):
    operators, spans, tasks = {}, {}, Counter()
    maximum, plans, staging = 0, [], 0
    prior_tasks, logical, waits, errors = {}, {}, Counter(), Counter()
    for event in document["events"]:
        data, kind = event["data"], event["kind"]
        if kind in {"c.node","backend.node"}:
            key = (data["op"],data["dtype"],data['clock'])
            row = operators.setdefault(key,{"op":key[0],"dtype":key[1],"clock":key[2],
                "executed":0,"failed":0,"skipped":0,"timed":0,"cpu_duration_ns_total":0,
                "cpu_duration_ns_min":None,"cpu_duration_ns_max":None})
            row["executed" if data["executed"] else "skipped"] += 1
            row["failed"] += int(data["executed"] and data["status"]!="OK")
            if data["cpu_duration_ns"] is not None:
                row["timed"] += 1
                row["cpu_duration_ns_total"] += data["cpu_duration_ns"]
                row["cpu_duration_ns_min"] = min(row["cpu_duration_ns_min"],data["cpu_duration_ns"]) if row["timed"]>1 else data["cpu_duration_ns"]
                row["cpu_duration_ns_max"] = max(row["cpu_duration_ns_max"],data["cpu_duration_ns"]) if row["timed"]>1 else data["cpu_duration_ns"]
        if "duration_ns" in event:
            row = spans.setdefault(kind,{"kind":kind,"clock":event['duration_clock'],"count":0,"duration_ns_total":0})
            row["count"] += 1
            row["duration_ns_total"] += event["duration_ns"]
        if kind == "task.release": tasks[data["state"]] += 1
        if kind == "memory.plan": plans.append({"model_ref":event["context"].get("model_ref"),**data})
        if kind == "session.open": maximum = max(maximum,data["actual_backing_bytes"])
        if kind in {"task.accept","task.state","task.release"}:
            ref, tick = event["context"]["task_ref"],event["context"]["logical_tick"]
            if ref in prior_tasks:
                state,start = prior_tasks[ref]
                row = logical.setdefault(state,{"state":state,"clock":"simulator_logical_ticks","intervals":0,"ticks_total":0})
                row["intervals"] += 1
                row["ticks_total"] += tick-start
            prior_tasks[ref] = (data["state"],tick)
            staging = max(staging,data["staging_reserved_bytes"])
        if kind=="device.wait": waits[data.get("wait_status",data.get("status"))] += 1
        if data.get("status") not in (None,"OK","PENDING","CANCEL_REQUESTED","CANCELLED","NOT_RUN"):
            errors[f"{kind}:{data['status']}"] += 1
    return {"format":"inference-trace-summary","version":1,"trace_id":document["trace_id"],
            "complete":document["complete"],"events":len(document["events"]),
            "dropped_events":document["dropped_events"],"recording_errors":document["recording_errors"],
            "operators":list(operators.values()),"host_spans":list(spans.values()),
            "released_tasks_by_state":dict(tasks),"memory_plans":plans,"max_session_backing_bytes":maximum,
            "logical_stages":list(logical.values()),"wait_results":dict(waits),"error_events":dict(errors),
            "max_staging_reserved_bytes":staging,
            "notes":"CPU/host/logical clocks are separate; spans overlap; memory is not RSS or global live peak."}


def timeline(document):
    events, lanes = [], {}
    for event in document["events"]:
        ctx = event["context"]
        lane = ctx.get("session_ref",ctx.get("device_ref","loader"))
        lanes.setdefault(lane,len(lanes)+1)
        output = {"name":event["kind"],"cat":"runtime","pid":1,"tid":lanes[lane],
                  "ts":event.get("start_ns",event["t_ns"])/1000,
                  "args":{"seq":event["seq"],**ctx,**event["data"]}}
        if "duration_ns" in event: output.update(ph="X",dur=event["duration_ns"]/1000)
        else: output.update(ph="i",s="t")
        events.append(output)
    return {"traceEvents":events,"displayTimeUnit":"ns","metadata":{"trace_id":document["trace_id"],
            "complete":document["complete"],"timeline_clock":document['clock'],
            "cpu_ticks_and_logical_ticks":"arguments only, never used as timeline timestamps"}}


def validate_trace(document, *, require_complete=True):
    errors = []
    def check(condition,message):
        if not condition and len(errors)<50: errors.append(message)
    try:
        check(document["format"]=="inference-runtime-trace" and type(document["version"]) is int and document["version"]==1,"format/version")
        events = document["events"]
        check(isinstance(events,list),"events")
        check(all(_uint(document[k]) for k in ("max_events","max_bytes","recorded_bytes","dropped_events","recording_errors")),"counters")
        check(len(events)<=document["max_events"] and document["recorded_bytes"]<=document["max_bytes"],"budget")
        check(type(document["complete"]) is bool and document["complete"] == (document["dropped_events"]==0 and document["recording_errors"]==0),"complete flag")
        check(document["clock"] in {'host_perf_counter_ns_relative','host_monotonic_ns_relative'},"host clock")
        if require_complete: check(document["complete"] is True,"incomplete observation")
        previous, nodes, chains = -1, defaultdict(list), {}
        models, sessions, runs, ended, tasks, released = set(), {}, {}, set(), {}, set()
        model_nodes, tensor_types = {}, {}
        for index,event in enumerate(events,1):
            check(type(event["seq"]) is int and event["seq"]==index,"sequence")
            check(_uint(event["t_ns"]) and event["t_ns"]>=previous,"timestamp order")
            previous = event["t_ns"]
            check(isinstance(event["kind"],str) and isinstance(event["data"],dict) and isinstance(event["context"],dict),"event schema")
            if "duration_ns" in event:
                check(event["duration_clock"]+'_ns_relative'==document['clock'] and _uint(event["duration_ns"]) and
                      _uint(event["start_ns"]) and event["start_ns"]+event["duration_ns"]==event["t_ns"],"host span")
            ctx,data = event["context"],event["data"]
            if "logical_tick" in ctx: check(_uint(ctx["logical_tick"]),"logical clock")
            kind = _execution_kind(event['kind'])
            if kind=="model.loaded":
                check(bool(ctx.get("model_ref")) and ctx["model_ref"] not in models,"model identity")
                models.add(ctx["model_ref"])
            if kind=="session.open":
                check(bool(ctx.get("session_ref")) and ctx.get("model_ref") in models,"session model link")
                check(ctx["session_ref"] not in sessions,"duplicate session")
                sessions[ctx["session_ref"]] = ctx.get("model_ref")
            if kind=="model.tensor": tensor_types[(ctx["model_ref"],data["tensor_id"])] = data["dtype"]
            if kind=="model.node": model_nodes[(ctx["model_ref"],data["index"])] = data
            if kind=="task.accept":
                check(ctx.get("session_ref") in sessions and sessions.get(ctx.get("session_ref"))==ctx.get("model_ref"),"task session link")
                check(bool(ctx.get("task_ref")) and ctx["task_ref"] not in tasks,"task identity")
                tasks[ctx["task_ref"]] = ctx.get("session_ref")
            if kind in {"task.state","task.release"}:
                check(ctx.get("task_ref") in tasks and tasks.get(ctx.get("task_ref"))==ctx.get("session_ref"),"task lifecycle link")
                check(ctx.get("task_ref") not in released,"event after release")
                if kind=="task.release":
                    check(data["quiescent"] is True and data["state"] in {"SUCCEEDED","FAILED","CANCELLED"},"unsafe release")
                    released.add(ctx["task_ref"])
            if kind=="run.begin":
                check(ctx.get("session_ref") in sessions and sessions.get(ctx.get("session_ref"))==ctx.get("model_ref"),"run session link")
                check(bool(ctx.get("run_ref")) and ctx["run_ref"] not in runs,"run identity")
                if ctx.get("task_ref") is not None:
                    check(tasks.get(ctx["task_ref"])==ctx.get("session_ref") and ctx["task_ref"] not in released,"run task link")
                runs[ctx["run_ref"]] = ctx
            if kind in {"c.chain","c.node","run.end"}:
                original = runs.get(ctx.get("run_ref"),{})
                check(bool(original) and all(ctx.get(k)==original.get(k) for k in ("session_ref","model_ref","task_ref","device_ref")),"node/run context link")
            if kind=="run.end":
                check(ctx["run_ref"] not in ended,"duplicate run end")
                ended.add(ctx["run_ref"])
            if kind=="c.node":
                check(bool(ctx.get("run_ref")),"node run link")
                check(type(data['executed']) is bool,'execution flag')
                if event['kind']=='c.node': check(data['clock']=='c_process_cpu','CPU domain')
                else: check(data['clock']=='unavailable' and data['timing_valid'] is False and
                            all(data[k] is None for k in ('ticks_per_second','start_ticks','end_ticks','cpu_duration_ns')),'generic clock domain')
                check(data["cpu_duration_ns"] is None or _uint(data["cpu_duration_ns"]),"CPU duration")
                declared = model_nodes.get((ctx.get("model_ref"),data["index"]),{})
                check(bool(declared) and declared.get("node_id")==data["node_id"] and declared.get("op")==data["op"] and
                      tensor_types.get((ctx.get("model_ref"),declared.get("output")))==data["dtype"],"node metadata")
                check(type(data["timing_valid"]) is bool,"timing valid flag")
                if data["timing_valid"]:
                    check(data["executed"] and _uint(data["ticks_per_second"]) and data["ticks_per_second"]>0 and
                          _uint(data["start_ticks"]) and _uint(data["end_ticks"]) and data["end_ticks"]>=data["start_ticks"] and
                          data["cpu_duration_ns"]==(data["end_ticks"]-data["start_ticks"])*1_000_000_000//data["ticks_per_second"],"CPU arithmetic")
                else: check(data["cpu_duration_ns"] is None,"invalid timing has duration")
                nodes[ctx["run_ref"]].append(data)
            if kind=="c.chain": chains[ctx["run_ref"]] = data
        check(document["recorded_bytes"]==sum(len(_encode(e)) for e in events),"byte count")
        if document["complete"]: check(set(runs)==ended,"unclosed run")
        for ref,chain in chains.items():
            if not chain["profiled"]: continue
            rows = nodes[ref]
            if document["complete"]:
                check([n["index"] for n in rows]==list(range(chain["node_count"])),"missing/reordered node records")
                check(sum(n["executed"] and n["status"]=="OK" for n in rows)==chain["completed_steps"],"completed count")
        for ref in nodes: check(ref in chains,"orphan C node")
        _validate_execution(events,check,document["complete"])
        _validate_backend_links(events,check)
        _validate_platform_links(events,check,document['complete'])
    except (KeyError,TypeError,ValueError,AttributeError,IndexError,OverflowError,RecursionError):
        errors.append("malformed trace")
    count = len(document["events"]) if isinstance(document,dict) and isinstance(document.get("events"),list) else 0
    return {"passed":not errors,"errors":errors,"event_count":count}


def _execution_kind(kind):
    return {'backend.chain':'c.chain','backend.node':'c.node'}.get(kind,kind)


def _validate_platform_links(events,check,complete):
    active=any(e['kind'].startswith('platform.') for e in events)
    sessions,runs={},{}
    for e in events:
        kind,ctx,data=e['kind'],e['context'],e['data']
        session,run=ctx.get('session_ref'),ctx.get('run_ref')
        if kind=='session.open' and (active or 'platform_api' in data):
            check(type(data.get('platform_api')) is int and data['platform_api']==1 and
                  isinstance(data.get('platform_id'),str) and bool(data['platform_id']) and
                  type(data.get('pointer_bits')) is int and data['pointer_bits'] in (32,64),'session platform metadata')
            sessions[session]=data
        if kind=='run.begin' and session in sessions:
            check(ctx.get('platform_id')==sessions[session].get('platform_id'),'run platform link')
            runs[run]={'syncs':{},'chain':None,'outputs':None,'context':ctx,'ended':False}
        if run not in runs: continue
        row=runs[run]
        if kind in {'platform.sync.to_backend','platform.sync.to_cpu'}:
            check(not row['ended'] and all(ctx.get(k)==row['context'].get(k) for k in
                  ('model_ref','session_ref','run_ref','task_ref','device_ref','platform_id','selected_backend')),
                  'sync/run context link')
            check(ctx.get('platform_id')==sessions[session].get('platform_id'),'sync platform link')
            check(kind not in row['syncs'],'duplicate platform sync')
            row['syncs'][kind]=(e['seq'],data['status'])
        if kind in {'c.chain','backend.chain'}: row['chain']=e['seq']
        if kind=='run.outputs': row['outputs']=e['seq']
        if kind=='run.end' and data['status']=='OK' and complete:
            before=row['syncs'].get('platform.sync.to_backend')
            after=row['syncs'].get('platform.sync.to_cpu')
            check(before is not None and after is not None and before[1]==after[1]=='OK' and
                  row['chain'] is not None and row['outputs'] is not None and
                  before[0]<row['chain']<after[0]<row['outputs'],'successful run missing ordered platform synchronization')
        if kind=='run.end': row['ended']=True


def _validate_backend_links(events,check):
    """Optional S2 metadata: legacy traces remain readable; selected executions cannot change identity."""
    selections,sessions,declared={},{},{}
    for event in events:
        kind,ctx,data=event['kind'],event['context'],event['data']
        session=ctx.get('session_ref')
        if kind=='model.node': declared.setdefault(ctx['model_ref'],[]).append((data['index'],data['node_id']))
        if kind=='backend.selection':
            check(session not in selections,'duplicate backend selection')
            selections[session]=data
            check(type(data['supported']) is bool and type(data['used_fallback']) is bool and type(data['allow_fallback']) is bool,'selection flags')
            reports=data['attempts']; ids=[r['backend_id'] for r in reports]
            check(bool(ids) and ids[0]==data['preferred_backend'] and len(set(ids))==len(ids),'selection attempts')
            permitted=[data['preferred_backend']]+(data['fallbacks'] if data['allow_fallback'] else [])
            check(ids==permitted[:len(ids)],'fallback order/policy')
            for report in reports:
                check(type(report['supported']) is bool and report['supported']==all(n['supported'] for n in report['nodes']),'support consistency')
                check([(n['index'],n['node_id']) for n in report['nodes']]==declared.get(ctx['model_ref'],[]),'support coverage')
                for n in report['nodes']:
                    check(type(n['supported']) is bool and isinstance(n['reason'],str) and
                          (n['reason']=='' if n['supported'] else bool(n['reason'])),'support reason')
            if data['supported']:
                check(ids[-1]==data['selected_backend'] and reports[-1]['supported'] and
                      all(not r['supported'] for r in reports[:-1]),'selected unsupported backend')
            else: check(data['selected_backend'] is None and len(ids)==len(permitted) and all(not r['supported'] for r in reports),'incomplete support search')
            check(data['used_fallback']==(data['supported'] and data['selected_backend']!=data['preferred_backend']),'fallback flag')
        if kind=='session.open' and (session in selections or any(k in data for k in ('selected_backend','execution','trace_kind'))):
            selected=selections.get(session,{})
            check(selected.get('supported') is True and selected.get('selected_backend')==data['selected_backend'] and
                  selected.get('execution')==data['execution'],'session selection link')
            sessions[session]=data
        if kind=='run.begin' and session in sessions:
            check(ctx.get('selected_backend')==sessions[session]['selected_backend'],'run backend link')
        if kind in {'c.chain','c.node','backend.chain','backend.node','task.accept','task.state','task.release'} and session in sessions:
            check(data.get('selected_backend')==sessions[session]['selected_backend'],'execution backend link')
            if kind in {'c.chain','c.node','backend.chain','backend.node'}:
                check(kind.split('.')[0]==sessions[session]['trace_kind'],'backend trace domain')


def _validate_execution(events,check,complete):
    """Cross-check observed execution evidence, not just JSON/accounting fields."""
    models, sessions, runs, tasks, leases = {}, {}, {}, {}, {}
    transitions = {
        "QUEUED":{"TRANSFERRING","CANCEL_REQUESTED"},
        "TRANSFERRING":{"RUNNING","CANCEL_REQUESTED"},
        "RUNNING":{"SYNCING","FAILED","QUARANTINED","CANCEL_REQUESTED"},
        "SYNCING":{"SUCCEEDED","CANCEL_REQUESTED"},
        "CANCEL_REQUESTED":{"CANCELLED","QUARANTINED"},
        "QUARANTINED":{"RECOVERING"},"RECOVERING":{"FAILED","QUARANTINED"},
        "SUCCEEDED":set(),"FAILED":set(),"CANCELLED":set()}
    c_statuses = {"OK","INVALID_ARGUMENT","INVALID_SHAPE","UNSUPPORTED","RESOURCE_LIMIT",
                  "NONFINITE","NUMERIC_OVERFLOW"}
    for event in events:
        kind,ctx,data = _execution_kind(event["kind"]),event["context"],event["data"]
        model,session,run,task = (ctx.get(k) for k in ("model_ref","session_ref","run_ref","task_ref"))
        if kind=="model.loaded":
            check(_uint(data["node_count"]) and data["node_count"]>0,"model node count")
            models[model] = data["node_count"]
        if kind=="session.open": sessions[session] = model
        if kind=="run.begin":
            check(data["node_count"]==models.get(model) and _uint(data["node_count"]),"run declared count")
            check(not any(r["context"].get("session_ref")==session and r["end"] is None for r in runs.values()),"overlapping session run")
            runs[run] = {"context":ctx,"count":data["node_count"],"chain":None,"nodes":[],"end":None,"phases":{},'generic':False}
            if task is not None:
                current = tasks.get(task,{})
                check(current.get("data",{}).get("state")=="RUNNING" and leases.get(session)==task,"run owns running task")
                check(current.get("run") is None,"multiple runs for task")
                current["run"] = run
        if kind in {"run.validate","run.prepare","run.outputs","c.chain","c.node","run.end"}:
            row = runs.get(run)
            check(row is not None,"execution without run")
            if row is None: continue
            check(row["end"] is None,"execution after run end")
            check(all(ctx.get(k)==row["context"].get(k) for k in ("session_ref","model_ref","task_ref","device_ref")),"phase/run context link")
            if kind.startswith("run.") and kind!="run.end":
                check(kind not in row["phases"],"duplicate run phase")
                if kind=="run.validate": check(row["chain"] is None and not row["phases"],"validate phase order")
                if kind=="run.prepare": check(row["chain"] is None and row["phases"].get("run.validate")=="OK","prepare phase order")
                if kind=="run.outputs": check(row["chain"] is not None and row["chain"]["status"]=="OK","outputs phase order")
                row["phases"][kind] = data["status"]
            elif kind=="c.chain":
                check(row["chain"] is None,"duplicate C chain")
                check(row["phases"].get("run.prepare")=="OK" and "run.outputs" not in row["phases"],"C chain phase order")
                check(data["node_count"]==row["count"] and type(data["node_count"]) is int,"C declared count")
                allowed=c_statuses|{'DEVICE_ERROR'} if event['kind']=='backend.chain' else c_statuses
                check(type(data["profiled"]) is bool and data["status"] in allowed,"C chain fields")
                check(_uint(data["completed_steps"]) and data["completed_steps"]<=row["count"],"C count bounds")
                if data["status"]=="OK": check(data["completed_steps"]==row["count"],"successful C count")
                row["chain"] = data
                row['generic']=event['kind']=='backend.chain'
            elif kind=="c.node":
                check(row["chain"] is not None and "run.outputs" not in row["phases"],"C node phase order")
                allowed=c_statuses|{'DEVICE_ERROR'} if event['kind']=='backend.node' else c_statuses
                check(data["status"] in allowed|{"NOT_RUN"} and data["executed"]==(data["status"]!="NOT_RUN"),"C node outcome")
                row["nodes"].append(data)
            elif kind=="run.end":
                row["end"] = data
                check(_uint(data["completed_steps"]) and data["completed_steps"]<=row["count"],"run count bounds")
        if kind in {"task.accept","task.state","task.release"}:
            state = data["state"]
            check(state in transitions,"unknown task state")
            check(sessions.get(session)==model and ctx.get("device_ref") is not None,"task model/device link")
            count = models.get(model,0)
            check(_uint(data["completed_steps"]) and data["completed_steps"]<=count,"task count bounds")
            check(type(data["quiescent"]) is bool and type(data["outputs_valid"]) is bool,"task visibility flags")
            if state=="SUCCEEDED":
                check(data["status"]=="OK" and data["execution_status"]=="OK" and data["quiescent"] and
                      data["outputs_valid"] and data["completed_steps"]==count,"unsafe successful task")
            elif state in {"FAILED","CANCELLED"}:
                check(data["quiescent"] and not data["outputs_valid"] and
                      data["status"] not in {"OK","PENDING"},"terminal task flags")
                if state=="CANCELLED": check(data["status"]=="CANCELLED","cancel status")
            else:
                expected = "DEVICE_ERROR" if state=="QUARANTINED" else "CANCEL_REQUESTED" if state=="CANCEL_REQUESTED" else "PENDING"
                check(not data["quiescent"] and not data["outputs_valid"] and data["status"]==expected,"pending task flags")
            if kind=="task.accept":
                check(state=="QUEUED" and data["completed_steps"]==0 and data["execution_status"] is None,"task admission state")
                check(session not in leases,"duplicate session lease")
                leases[session] = task
                tasks[task] = {"context":ctx,"data":data,"tick":ctx["logical_tick"],"run":None}
            else:
                prior = tasks.get(task)
                check(prior is not None and leases.get(session)==task,"task lease link")
                if prior is None: continue
                check(all(ctx.get(k)==prior["context"].get(k) for k in ("model_ref","session_ref","device_ref")),"task context changed")
                check(ctx["logical_tick"]>=prior["tick"] and data["completed_steps"]>=prior["data"]["completed_steps"],"task progress order")
                if kind=="task.state": check(state in transitions.get(prior["data"]["state"],set()),"task state transition")
                else:
                    check(all(data[k]==prior["data"][k] for k in ("state","status","completed_steps","execution_status","quiescent","outputs_valid")),"release changed outcome")
                    leases.pop(session,None)
                prior.update(data=data,tick=ctx["logical_tick"])
                if state=="SUCCEEDED" and complete:
                    executed = runs.get(prior["run"],{})
                    ended = executed.get("end")
                    check(isinstance(ended,dict) and ended.get("status")=="OK","task lacks successful run")
                if prior["run"] is not None and state!="RUNNING":
                    end = runs[prior["run"]]["end"]
                    check(end is not None and data["completed_steps"]==end["completed_steps"],"task/run completed count")
        if kind=="session.close" and data.get("status")=="OK":
            check(session not in leases,"close while leased")
    for row in runs.values():
        chain,end,nodes = row["chain"],row["end"],row["nodes"]
        if chain is not None:
            if complete: check(chain["profiled"],"complete trace lacks C profiling")
            if chain["profiled"] and complete:
                check([n["index"] for n in nodes]==list(range(row["count"])),"C node coverage")
                done = chain["completed_steps"]
                if chain["status"]=="OK":
                    check(all(n["executed"] and n["status"]=="OK" for n in nodes),"successful C has failed/skipped node")
                elif row['generic'] and chain['status']=='DEVICE_ERROR':
                    check(all(n['executed'] and n['status']=='OK' for n in nodes[:done]),'device error successful prefix')
                    tail=nodes[done:]
                    check(all(not n['executed'] and n['status']=='NOT_RUN' for n in tail) or
                          bool(tail) and tail[0]['executed'] and tail[0]['status']=='DEVICE_ERROR' and
                          all(not n['executed'] and n['status']=='NOT_RUN' for n in tail[1:]),'device error/skip order')
                elif any(n["executed"] for n in nodes):
                    check(done<len(nodes) and all(n["executed"] and n["status"]=="OK" for n in nodes[:done]) and
                          nodes[done]["executed"] and nodes[done]["status"]==chain["status"] and
                          all(not n["executed"] and n["status"]=="NOT_RUN" for n in nodes[done+1:]),"C failure/skip order")
                else: check(done==0,"unexecuted C progress")
        if end is not None:
            if chain is None:
                check(end["status"]!="OK" and end["completed_steps"]==0,"run missing C execution")
            else:
                check(end["completed_steps"]==chain["completed_steps"],"run/C completed count")
                if chain["status"]!="OK": check(end["status"]==chain["status"],"run/C failure status")
                if end["status"]=="OK":
                    check(chain["status"]=="OK" and row["phases"].get("run.outputs")=="OK","successful run phases")
                if "run.outputs" in row["phases"] and row["phases"]["run.outputs"]!="OK":
                    check(end["status"]==row["phases"]["run.outputs"],"host output failure status")
                for kind in ("run.validate","run.prepare"):
                    check(row["phases"].get(kind)=="OK","C without successful host preparation")
            for kind,status in row["phases"].items():
                if status!="OK": check(end["status"]==status,"run/phase failure status")


def _load_json(path,limit):
    require(path.is_file() and not path.is_symlink(),"IO_ERROR","Not a regular trace file")
    with path.open("rb") as stream: raw = stream.read(limit+1)
    require(len(raw)<=limit,"RESOURCE_LIMIT","Trace file exceeds limit")
    def pairs(values):
        result = {}
        for key,value in values:
            require(key not in result,"INVALID_TRACE","Duplicate JSON key")
            result[key] = value
        return result
    def constant(value): raise ContractError("INVALID_TRACE","Nonfinite JSON number")
    return raw,json.loads(raw.decode("utf-8"),object_pairs_hook=pairs,parse_constant=constant)


def read_export(path, *, require_complete=True):
    try:
        root = Path(path).resolve()
        _,manifest = _load_json(root/"manifest.json",16384)
        require(manifest["format"]=="inference-trace-export" and type(manifest["version"]) is int and manifest["version"]==1 and
                set(manifest["files"])=={"trace.json","timeline.json","summary.json"},"INVALID_TRACE","Invalid export manifest")
        loaded = {}
        for name,record in manifest["files"].items():
            raw,value = _load_json(root/name,256*1024*1024)
            require(len(raw)==record["byte_length"] and hashlib.sha256(raw).hexdigest()==record["sha256"],
                    "CHECKSUM_MISMATCH","Trace export checksum mismatch")
            loaded[name] = value
        validation = validate_trace(loaded["trace.json"],require_complete=require_complete)
        require(loaded["summary.json"]==summarize(loaded["trace.json"]) and loaded["timeline.json"]==timeline(loaded["trace.json"]),
                "INVALID_TRACE","Derived trace artifacts mismatch")
        return {"trace":loaded["trace.json"],"timeline":loaded["timeline.json"],"summary":loaded["summary.json"],"validation":validation}
    except ContractError: raise
    except (OSError,ValueError,TypeError,KeyError,RecursionError) as exc:
        raise ContractError("INVALID_TRACE",str(exc)) from exc
