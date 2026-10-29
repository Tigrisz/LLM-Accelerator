"""C-specific binding separated from model/session and static selection policy."""

import ctypes as ct
from math import prod

from .backend import BoundChain,ChainResult,NodeSupport,StaticBackend,SupportReport
from .c_backend import CBackend,CCall,CProfile,CTensor,DTYPES,OPS
from .contracts import require
from .resources import ResourceGroup


class CStaticBackend(StaticBackend):
    execution_kind='pc_c_backend'
    trace_kind='c'
    resource_tracking='native_payload_v1'

    def __init__(self,backend,*,backend_id='pc_c'):
        require(isinstance(backend,CBackend),'INVALID_ARGUMENT','CBackend required')
        self.raw,self.backend_id=backend,backend_id

    def query(self,requirements):
        rows=[]
        for n in requirements.nodes:
            reason=''; values=[t for _,t in n.inputs]+[n.output]
            if n.attributes: reason='attributes unsupported'
            elif n.output.read_only: reason='output permission is read-only'
            elif any(t.memory_domain!='host' for t in values): reason='memory domain unsupported'
            elif any(t.layout!='row_major' for t in values): reason='layout unsupported'
            elif any(t.dtype not in DTYPES or t.dtype!=n.output.dtype for t in values): reason='dtype unsupported'
            elif any(not 1<=len(t.shape)<=4 or len(t.shape)!=len(t.storage_shape) or
                     any(type(d) is not int or d<=0 for d in t.shape+t.storage_shape) or
                     any(a>b for a,b in zip(t.shape,t.storage_shape)) or prod(t.storage_shape)>1048576 for t in values):
                reason='shape or storage shape unsupported'
            elif n.op not in OPS: reason='operator unsupported'
            else:
                bound=dict(n.inputs)
                keys=set(bound)
                allowed={'linear':({'weight','input'},{'weight','input','bias'}),'add':({'a','b'},),'relu':({'input'},)}
                if keys not in allowed[n.op]: reason='input bindings unsupported'
                elif n.op=='linear':
                    w,x=bound['weight'],bound['input']
                    if len(w.shape)!=2 or len(x.shape)!=1 or w.shape[1]!=x.shape[0] or n.output.shape!=(w.shape[0],) or ('bias' in bound and bound['bias'].shape!=n.output.shape):
                        reason='linear shape unsupported'
                elif any(t.shape!=n.output.shape for t in bound.values()): reason='elementwise shape unsupported'
            scratch=prod(n.output.shape)*4
            if not reason and scratch>requirements.workspace_bytes: reason='workspace capacity unsupported'
            if not reason and (requirements.alignment<4 or requirements.alignment&(requirements.alignment-1)):
                reason='alignment unsupported'
            rows.append(NodeSupport(n.index,n.node_id,not reason,reason,scratch))
        return SupportReport(self.backend_id,all(r.supported for r in rows),tuple(rows))

    def prepare(self,package,plan,views,workspace,*,profile=False):
        return CBoundChain(self.raw,package,plan,views,workspace,profile=profile)


class CBoundChain(BoundChain):
    def __init__(self,backend,package,plan,views,workspace,*,profile=False):
        self._resources=ResourceGroup()
        try:self._initialize(backend,package,plan,views,workspace,profile=profile)
        except BaseException:
            self.descriptors={};self.calls=self.profiles=self.completed=None;self._resources.close();raise

    def _initialize(self,backend,package,plan,views,workspace,*,profile=False):
        self.backend,self.package=backend,package
        self.descriptors={}
        for t in package.tensors:
            descriptor=self._resources.allocate(CTensor,ct.sizeof(CTensor),label='tensor:'+t.id)
            self.descriptors[t.id]=descriptor
            descriptor.data=views[t.id].ctypes.data;descriptor.byte_length=t.spec.byte_length
            descriptor.dtype=DTYPES[t.spec.dtype];descriptor.layout=1;descriptor.rank=len(t.spec.shape)
            for axis,(logical,storage) in enumerate(zip(t.spec.shape,t.spec.storage_shape)):
                descriptor.shape[axis]=logical;descriptor.storage_shape[axis]=storage
        count=len(package.nodes)
        self.calls=self._resources.allocate(lambda:(CCall*count)(),ct.sizeof(CCall)*count,label='call_table')
        for index,n in enumerate(package.nodes):
            bound=dict(n.inputs)
            a=bound['weight'] if n.op=='linear' else bound['a'] if n.op=='add' else bound['input']
            b=bound['input'] if n.op=='linear' else bound.get('b')
            pointer=lambda name:ct.pointer(self.descriptors[name]) if name is not None else None
            call=self.calls[index];call.op=OPS[n.op];call.a=pointer(a);call.b=pointer(b)
            call.bias=pointer(bound.get('bias'));call.output=pointer(n.output)
            call.workspace=workspace.ctypes.data;call.workspace_bytes=plan.workspace_bytes
            status=backend._status(backend.lib.ir_query(ct.byref(call)))
            require(status=='OK',status,f'C rejected planned node {n.id}: {status}')
        self.completed=self._resources.allocate(ct.c_uint32,ct.sizeof(ct.c_uint32),label='completed_steps')
        self.profiles=None
        if profile and backend.has_profiling:
            try:self.profiles=self._resources.allocate(lambda:(CProfile*count)(),ct.sizeof(CProfile)*count,category='c_profiles',label='node_profiles')
            except Exception: pass  # Observation allocation must not change computation.
        self.profiled=self.profiles is not None
        self.profile_records_bytes=ct.sizeof(self.profiles) if self.profiled else 0

    def execute(self):
        require(self.calls is not None,'INVALID_STATE','C binding is closed')
        completed=self.completed;completed.value=0
        if self.profiled:
            ct.memset(ct.addressof(self.profiles),0,ct.sizeof(self.profiles))
            code=self.backend.lib.ir_execute_chain_profiled(self.calls,len(self.calls),ct.byref(completed),self.profiles,len(self.profiles))
        else: code=self.backend.lib.ir_execute_chain(self.calls,len(self.calls),ct.byref(completed))
        return ChainResult(self.backend._status(code),completed.value)

    def observe_nodes(self):
        if not self.profiled: return ()
        frequency=int(self.backend.lib.ir_clock_ticks_per_second())
        rows=[]
        for index,(node,p) in enumerate(zip(self.package.nodes,self.profiles)):
            valid=bool(p.executed and p.timing_valid and frequency>0 and p.end_ticks>=p.start_ticks)
            rows.append({'index':index,'node_id':node.id,'op':node.op,'dtype':self.package.tensor(node.output).spec.dtype,
                'executed':bool(p.executed),'status':self.backend._status(p.status) if p.executed else 'NOT_RUN',
                'clock':'c_process_cpu','ticks_per_second':frequency,'timing_valid':valid,
                'start_ticks':int(p.start_ticks) if valid else None,'end_ticks':int(p.end_ticks) if valid else None,
                'cpu_duration_ns':(int(p.end_ticks)-int(p.start_ticks))*1000000000//frequency if valid else None})
        return tuple(rows)

    def close(self):
        self.calls=self.profiles=None
        self.descriptors.clear()
        self.completed=None;self._resources.close()
        self.backend=self.package=None

    def recover(self):
        # PC C calls return on this same thread; there is no background execution.
        return self.calls is not None
