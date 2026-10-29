"""Version 1 synchronous whole-chain backend boundary; no execution-time fallback."""

from abc import ABC,abstractmethod
from dataclasses import asdict,dataclass
import re
from types import MappingProxyType

from .contracts import require

BACKEND_API_VERSION=1
STATUSES=frozenset({'OK','INVALID_ARGUMENT','INVALID_SHAPE','UNSUPPORTED','RESOURCE_LIMIT',
                    'NONFINITE','NUMERIC_OVERFLOW','DEVICE_ERROR'})


@dataclass(frozen=True)
class TensorRequirement:
    tensor_id:str
    dtype:str
    shape:tuple
    storage_shape:tuple
    layout:str
    role:str
    memory_domain:str='host'
    read_only:bool=False


@dataclass(frozen=True)
class NodeRequirement:
    index:int
    node_id:str
    op:str
    inputs:tuple
    output:TensorRequirement
    attributes:tuple=()


@dataclass(frozen=True)
class ChainRequirements:
    nodes:tuple
    workspace_bytes:int
    alignment:int
    total_backing_bytes:int


def requirements_for(package,plan):
    tensors={t.id:TensorRequirement(t.id,t.spec.dtype,tuple(t.spec.shape),tuple(t.spec.storage_shape),
             t.spec.layout,t.role,read_only=t.role=='constant') for t in package.tensors}
    return ChainRequirements(tuple(NodeRequirement(i,n.id,n.op,tuple((k,tensors[v]) for k,v in n.inputs),
                             tensors[n.output]) for i,n in enumerate(package.nodes)),
                             plan.workspace_bytes,plan.alignment,plan.total_bytes)


@dataclass(frozen=True)
class NodeSupport:
    index:int
    node_id:str
    supported:bool
    reason:str
    workspace_bytes:int


@dataclass(frozen=True)
class SupportReport:
    backend_id:str
    supported:bool
    nodes:tuple

    def to_dict(self): return asdict(self)


@dataclass(frozen=True)
class ChainResult:
    status:str
    completed_steps:int
    quiescent:bool=True


class BoundChain(ABC):
    """Binding owns descriptors, borrows arenas; execute returns confirmed synchronous progress."""
    profiled=False
    profile_records_bytes=0

    @abstractmethod
    def execute(self): pass

    def observe_nodes(self): return ()

    def recover(self):
        """True only after this backend confirms no remaining access to borrowed arenas."""
        return False

    @abstractmethod
    def close(self): pass


class StaticBackend(ABC):
    api_version=BACKEND_API_VERSION
    execution_kind='custom_synchronous'
    trace_kind='backend'

    @abstractmethod
    def query(self,requirements): pass

    @abstractmethod
    def prepare(self,package,plan,views,workspace,*,profile=False): pass


def adapt_backend(backend):
    from .c_backend import CBackend
    if isinstance(backend,CBackend):
        from .c_execution import CStaticBackend
        backend=CStaticBackend(backend)
    require(isinstance(backend,StaticBackend) and type(backend.api_version) is int and
            backend.api_version==BACKEND_API_VERSION,'INVALID_ARGUMENT','StaticBackend API 1 required')
    name=getattr(backend,'backend_id',None)
    require(isinstance(name,str) and re.fullmatch(r'[A-Za-z_][A-Za-z0-9_.-]{0,63}',name) is not None,
            'INVALID_ARGUMENT','Invalid backend identity')
    require(backend.trace_kind in {'c','backend'} and isinstance(backend.execution_kind,str) and
            0<len(backend.execution_kind)<=80,'INVALID_ARGUMENT','Invalid backend observation metadata')
    return backend


@dataclass(frozen=True)
class BackendPolicy:
    preferred:str
    allow_fallback:bool=False
    fallbacks:tuple=()

    def __post_init__(self):
        require(isinstance(self.preferred,str) and bool(self.preferred) and type(self.allow_fallback) is bool and
                type(self.fallbacks) is tuple and all(isinstance(n,str) and n for n in self.fallbacks) and
                len(set((self.preferred,)+self.fallbacks))==1+len(self.fallbacks),
                'INVALID_ARGUMENT','Invalid explicit backend policy')


@dataclass(frozen=True)
class BackendSelection:
    preferred:str
    backend:StaticBackend|None
    attempts:tuple

    @property
    def supported(self): return self.backend is not None

    @property
    def used_fallback(self): return self.supported and self.backend.backend_id!=self.preferred

    def to_dict(self):
        return {'supported':self.supported,'status':'OK' if self.supported else 'UNSUPPORTED',
                'preferred_backend':self.preferred,'selected_backend':self.backend.backend_id if self.backend else None,
                'execution':self.backend.execution_kind if self.backend else None,'used_fallback':self.used_fallback,
                'attempts':[r.to_dict() for r in self.attempts]}


class BackendRegistry:
    def __init__(self,backends):
        require(isinstance(backends,(list,tuple)) and 1<=len(backends)<=32,'INVALID_ARGUMENT','Need 1..32 backends')
        entries={}
        for value in backends:
            backend=adapt_backend(value)
            require(backend.backend_id not in entries,'INVALID_ARGUMENT','Duplicate backend identity')
            entries[backend.backend_id]=backend
        self.backends=MappingProxyType(entries)

    def query(self,requirements,backend_id):
        require(isinstance(requirements,ChainRequirements) and backend_id in self.backends,
                'INVALID_ARGUMENT','Unknown backend or invalid requirements')
        report=self.backends[backend_id].query(requirements)
        require(isinstance(report,SupportReport) and report.backend_id==backend_id and type(report.supported) is bool and
                type(report.nodes) is tuple and len(report.nodes)==len(requirements.nodes),
                'INVALID_ARGUMENT','Malformed backend capability report')
        for declared,row in zip(requirements.nodes,report.nodes):
            require(isinstance(row,NodeSupport) and type(row.index) is int and row.index==declared.index and
                    row.node_id==declared.node_id and type(row.supported) is bool and isinstance(row.reason,str) and
                    len(row.reason)<=8192 and (row.reason=='' if row.supported else bool(row.reason)) and
                    type(row.workspace_bytes) is int and 0<=row.workspace_bytes<=2**63-1 and
                    (not row.supported or row.workspace_bytes<=requirements.workspace_bytes),
                    'INVALID_ARGUMENT','Malformed node capability report')
        require(report.supported==all(r.supported for r in report.nodes),
                'INVALID_ARGUMENT','Contradictory backend capability report')
        return report

    def select(self,requirements,policy):
        require(isinstance(policy,BackendPolicy),'INVALID_ARGUMENT','BackendPolicy required')
        require(all(n in self.backends for n in (policy.preferred,)+policy.fallbacks),
                'INVALID_ARGUMENT','Policy names an unregistered backend')
        attempts=[]
        for name in (policy.preferred,)+(policy.fallbacks if policy.allow_fallback else ()):
            report=self.query(requirements,name); attempts.append(report)
            if report.supported: return BackendSelection(policy.preferred,self.backends[name],tuple(attempts))
        return BackendSelection(policy.preferred,None,tuple(attempts))


def configure(backend=None,registry=None,policy=None):
    require((backend is None)!=(registry is None),'INVALID_ARGUMENT','Specify one backend or registry')
    if backend is not None:
        registry=BackendRegistry([backend])
        if policy is None: policy=BackendPolicy(next(iter(registry.backends)))
    require(isinstance(registry,BackendRegistry) and isinstance(policy,BackendPolicy),
            'INVALID_ARGUMENT','Registry needs explicit BackendPolicy')
    return registry,policy
