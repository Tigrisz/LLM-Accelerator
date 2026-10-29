"""PC builds and S2 adapter for the same standalone C static runtime."""
import ctypes as ct
import hashlib
import os
from pathlib import Path

from .backend import ChainResult
from .c_backend import CBackend,CCall,CProfile,CTensor,FLAGS,ROOT,_compiler,_new_directory,_run
from .c_execution import CStaticBackend,CBoundChain
from .contracts import require
from .reporting import write_json_exclusive
from .static_export import encode_static
from .resources import ResourceGroup


def source_hashes():
    return {str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted((ROOT/'c').rglob('*')) if p.is_file()}


def build_static(output,compiler=None,*,sanitize=False):
    cc=_compiler(compiler);directory=_new_directory(Path(output))
    common=[cc,*FLAGS,'-O1' if sanitize else '-O2','-I',str(ROOT/'c/include')]
    if sanitize: common+=['-fsanitize=address,undefined','-fno-omit-frame-pointer','-fno-pie','-no-pie']
    sources=[str(ROOT/'c/src'/n) for n in ('ir_core.c','ir_static.c','ir_pc.c')]
    result={'tests':[],'source_sha256':source_hashes(),'compiler':_run([cc,'--version']).stdout.strip(),'sanitize':sanitize}
    commands=[]
    targets=[('host','ir_static_host',str(ROOT/'c/src/ir_static_host.c')),
             ('test','test_static',str(ROOT/'c/tests/test_static.c')),('test','test_pc',str(ROOT/'c/tests/test_pc.c')),
             ('test','test_resources',str(ROOT/'c/tests/test_resources.c'))]
    for kind,name,source in targets:
        target=directory/(name+('.exe' if os.name=='nt' else ''))
        command=[*common,source,*sources,'-lm','-o',str(target)];run=_run(command);commands.append(command)
        (directory/(name+'.build.log')).write_text(run.stdout+run.stderr,encoding='utf-8')
        require(run.returncode==0,'BUILD_FAILED',run.stderr)
        if kind=='test':result['tests'].append(str(target))
        else:result[kind]=str(target)
    if not sanitize:
        libdir=_new_directory(directory/'library')
        library=libdir/('ir_static.dll' if os.name=='nt' else 'libir_static.so')
        command=[*common,'-shared',*(['-fPIC'] if os.name!='nt' else []),*sources,'-lm','-o',str(library)]
        run=_run(command);commands.append(command)
        (directory/'library.build.log').write_text(run.stdout+run.stderr,encoding='utf-8')
        require(run.returncode==0,'BUILD_FAILED',run.stderr);result['library']=str(library)
        write_json_exclusive(libdir/'build.json',{'binary_sha256':hashlib.sha256(library.read_bytes()).hexdigest(),
            'source_sha256':source_hashes(),'abi_version':1,'runtime_api':1,'runtime_abi':2,'command':command})
    result['commands']=commands
    result['binary_sha256']={Path(p).name:hashlib.sha256(Path(p).read_bytes()).hexdigest()
        for p in result['tests']+[result['host']]+([result['library']] if 'library' in result else [])}
    write_json_exclusive(directory/'build.json',result)
    return result


def require_runtime_abi(lib):
    query=getattr(lib,'irs_runtime_abi_version',None)
    require(query is not None,'UNSUPPORTED','Static runtime ABI2 required; rebuild the library and caller')
    if hasattr(query,'restype'):query.restype=ct.c_uint32
    require(query()==2,'UNSUPPORTED','Static runtime ABI2 required; incompatible native layout')


class CStaticRuntimeBackend(CStaticBackend):
    execution_kind='pc_c_static_runtime'

    def __init__(self,library,*,backend_id='pc_c_static'):
        super().__init__(CBackend(Path(library)),backend_id=backend_id)
        lib=self.raw.lib
        require_runtime_abi(lib)
        lib.irs_context_size.restype=ct.c_size_t
        for name in ('irs_inspect_workspace_bytes','irs_tensor_state_bytes'):
            getattr(lib,name).argtypes=[ct.c_uint32];getattr(lib,name).restype=ct.c_size_t
        lib.irs_bind_v2.argtypes=[ct.c_void_p,ct.c_void_p,ct.c_size_t,ct.c_void_p,ct.c_uint64,
            ct.c_void_p,ct.c_uint64,ct.c_void_p,ct.c_uint64,ct.POINTER(CTensor),ct.c_uint32,
            ct.POINTER(CCall),ct.c_uint32,ct.POINTER(CProfile),ct.c_void_p,ct.c_uint32,
            ct.c_void_p,ct.c_size_t,ct.c_void_p,ct.c_void_p]
        lib.irs_bind_v2.restype=ct.c_uint32
        lib.irs_input.argtypes=[ct.c_void_p,ct.c_uint32,ct.c_void_p,ct.c_uint64];lib.irs_input.restype=ct.c_uint32
        for name in ('irs_run','irs_close','irs_recover','irs_completed'):
            fn=getattr(lib,name);fn.argtypes=[ct.c_void_p];fn.restype=ct.c_uint32

    def prepare(self,package,plan,views,workspace,*,profile=False):
        return StaticRuntimeBinding(self.raw,package,plan,views,workspace,profile=profile)


class StaticRuntimeBinding(CBoundChain):
    def __init__(self,backend,package,plan,views,workspace,*,profile=False):
        self._resources=ResourceGroup()
        try:self._initialize(backend,package,plan,views,workspace,profile=profile)
        except BaseException:
            self.context=self.image=self.descriptors=self.calls=self.profiles=self.tensor_state=None;self._resources.close();raise

    def _initialize(self,backend,package,plan,views,workspace,*,profile=False):
        self.backend,self.package,self.views=backend,package,views
        image,_=encode_static(package,plan)
        self.image=self._resources.allocate(lambda:ct.create_string_buffer(image),len(image)+1,label='execution_image')
        size=backend.lib.irs_context_size()
        self.context=self._resources.allocate(lambda:ct.create_string_buffer(size),size,label='static_context')
        self.descriptors=self._resources.allocate(lambda:(CTensor*len(package.tensors))(),ct.sizeof(CTensor)*len(package.tensors),label='tensor_table')
        self.calls=self._resources.allocate(lambda:(CCall*len(package.nodes))(),ct.sizeof(CCall)*len(package.nodes),label='call_table')
        state_bytes=backend.lib.irs_tensor_state_bytes(len(package.tensors))
        self.tensor_state=self._resources.allocate(lambda:(ct.c_ubyte*state_bytes)(),state_bytes,label='tensor_state')
        self.profiles=None
        def arena(name):
            for t in package.tensors:
                p=plan.placement(t.id)
                if p.arena==name:return views[t.id].ctypes.data-p.offset
            return None
        temporary=ResourceGroup(self._resources.ledger)
        try:
            size=backend.lib.irs_inspect_workspace_bytes(len(package.tensors))
            inspect=temporary.allocate(lambda:(ct.c_int16*(size//2))(),size,label='c_inspect_workspace')
            if profile:
                try:self.profiles=self._resources.allocate(lambda:(CProfile*len(package.nodes))(),ct.sizeof(CProfile)*len(package.nodes),category='c_profiles',label='node_profiles')
                except Exception:pass
            self.profiled=self.profiles is not None;self.profile_records_bytes=ct.sizeof(self.profiles) if self.profiled else 0
            code=backend.lib.irs_bind_v2(self.context,self.image,len(image),arena('weights'),plan.weight_bytes,
                arena('activations'),plan.activation_bytes,workspace.ctypes.data,plan.workspace_bytes,
                self.descriptors,len(self.descriptors),self.calls,len(self.calls),self.profiles,
                self.tensor_state,state_bytes,inspect,size,None,None)
        finally:
            temporary.close()
        require(code==0,'INVALID_MODEL',f'C static binding rejected image: {code}')

    def execute(self):
        require(self.context is not None,'INVALID_STATE','Static runtime binding closed')
        for i,t in enumerate(self.package.tensors):
            if t.role=='input':
                code=self.backend.lib.irs_input(self.context,i,self.views[t.id].ctypes.data,t.spec.byte_length)
                require(code==0,'DEVICE_ERROR','C static input failed')
        code=self.backend.lib.irs_run(self.context)
        if code>6:raise RuntimeError(f'C static runtime state unknown: {code}')
        return ChainResult(self.backend._status(code),int(self.backend.lib.irs_completed(self.context)))

    def close(self):
        if self.context is not None:
            require(self.backend.lib.irs_close(self.context)==0,'BUSY','C runtime cannot close unknown state')
            self.context=None;self.calls=self.profiles=None;self.descriptors=None;self.tensor_state=None;self.views=None;self.image=None
            self.backend=self.package=None
            self._resources.close()

    def recover(self):
        # This adapter uses the built-in same-thread C backend, with S3 outer synchronization.
        return self.context is not None
