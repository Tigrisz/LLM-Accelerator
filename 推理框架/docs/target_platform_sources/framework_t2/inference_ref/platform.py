"""Platform API 1: bounded reads, owned aligned host memory, monotonic time and sync."""

from abc import ABC,abstractmethod
from dataclasses import dataclass
from pathlib import Path
import os
import stat
import struct
import threading
import time
import uuid
import weakref

import numpy as np

from .contracts import ContractError,require
from .resources import ResourceLedger

PLATFORM_API_VERSION=1
U64_MAX=(1<<64)-1
NATIVE_BITS=struct.calcsize('P')*8
_RETENTION_LOCK=threading.RLock()
_RETAINED={}


@dataclass(frozen=True)
class RetainedResource:
    retention_id:str
    platform_id:str
    reason:str
    owner:object


def retained_resources(platform_id=None):
    """Enumerate strongly retained exceptional owners for explicit recover/close; never force-free."""
    with _RETENTION_LOCK:
        return tuple(r for r in _RETAINED.values() if platform_id is None or r.platform_id==platform_id)


def _uint(value): return type(value) is int and 0<=value<=U64_MAX


def checked_mul(a,b):
    require(_uint(a) and _uint(b),'INVALID_ARGUMENT','Unsigned integer operands required')
    require(a==0 or b<=U64_MAX//a,'RESOURCE_LIMIT','uint64 multiplication overflow')
    return a*b


def checked_range(offset,length,capacity):
    require(all(_uint(v) for v in (offset,length,capacity)),'INVALID_ARGUMENT','Invalid uint64 range')
    require(offset<=capacity and length<=capacity-offset,'INVALID_ARGUMENT','Range exceeds capacity')
    return offset+length


def checked_span(address,length,*,bits=NATIVE_BITS):
    require(type(bits) is int and bits in (32,64),'INVALID_ARGUMENT','Address width must be 32 or 64')
    maximum=(1<<bits)-1
    require(_uint(address) and _uint(length),'INVALID_ARGUMENT','Invalid address/length')
    require(address<=maximum and length<=maximum and length<=(1<<bits)-address,
            'RESOURCE_LIMIT','Address or size_t range cannot be represented without truncation')
    return address+length  # Exclusive mathematical end may be 2**bits; never cast it to a pointer.


class ReadSource(ABC):
    size:int

    @abstractmethod
    def read_at(self,offset,length): pass

    @abstractmethod
    def close(self): pass

    def __enter__(self): return self
    def __exit__(self,*_): self.close()


def read_exact(source,offset,length):
    require(isinstance(source,ReadSource),'INVALID_ARGUMENT','ReadSource required')
    checked_range(offset,length,source.size)
    try: value=source.read_at(offset,length)
    except MemoryError as exc: raise ContractError('RESOURCE_LIMIT','Read buffer allocation failed') from exc
    except OSError as exc: raise ContractError('IO_ERROR',str(exc)) from exc
    require(type(value) is bytes and len(value)==length,'IO_ERROR','Short read or invalid read result; partial data rejected')
    return value


class PCFileSource(ReadSource):
    def __init__(self,path):
        self._stream=None
        try:
            path=Path(path)
            require(path.is_file() and not path.is_symlink(),'IO_ERROR','Read source must be a regular non-symlink file')
            stream=path.open('rb')
            try:
                info=os.fstat(stream.fileno())
                require(stat.S_ISREG(info.st_mode),'IO_ERROR','Opened source is not a regular file')
                require(_uint(info.st_size),'RESOURCE_LIMIT','File size exceeds uint64')
                self.size=info.st_size
                self._stream=stream
            except BaseException:
                stream.close()
                raise
        except OSError as exc: raise ContractError('IO_ERROR',str(exc)) from exc
        self._lock=threading.RLock()

    def read_at(self,offset,length):
        with self._lock:
            require(self._stream is not None,'INVALID_STATE','Source is closed')
            checked_range(offset,length,self.size)
            try:
                self._stream.seek(offset)
                value=self._stream.read(length)
                require(os.fstat(self._stream.fileno()).st_size==self.size,'IO_ERROR','Source size changed during read')
                return value
            except (OSError,OverflowError) as exc: raise ContractError('IO_ERROR',str(exc)) from exc

    def close(self):
        if self._stream is not None:
            self._stream.close()
            self._stream=None


class MemoryBlock:
    memory_domain='host'
    def __init__(self,allocator,token,backing,data,alignment):
        self._allocator,self._token=allocator,token
        self.backing,self.data,self.alignment=backing,data,alignment
        self.released=False
        self._resource_ticket=None

    @property
    def address(self):
        require(not self.released,'INVALID_STATE','Memory block released')
        return int(self.data.ctypes.data) if self.data.size else 0

    def close(self):
        if not self.released:self._allocator.release(self)
        if self.released and self._resource_ticket is not None:self._resource_ticket.close()


class AlignedAllocator(ABC):
    pointer_bits=NATIVE_BITS
    @abstractmethod
    def allocate(self,size,alignment): pass
    @abstractmethod
    def release(self,block): pass
    @abstractmethod
    def stats(self): pass


class PCAllocator(AlignedAllocator):
    def __init__(self,*,budget_bytes=64*1024*1024,pointer_bits=NATIVE_BITS):
        require(_uint(budget_bytes),'INVALID_ARGUMENT','Invalid allocator budget')
        checked_span(0,0,bits=pointer_bits)
        self.budget_bytes,self.pointer_bits=budget_bytes,pointer_bits
        self._entries={}; self._next=0; self._lock=threading.RLock()

    def _allocate_backing(self,size): return np.zeros(size,dtype=np.uint8)

    def stats(self):
        with self._lock:
            self._entries={k:v for k,v in self._entries.items() if v[0]() is not None}
            return {'live_allocations':len(self._entries),'backing_bytes':sum(v[1] for v in self._entries.values()),
                    'budget_bytes':self.budget_bytes,'pointer_bits':self.pointer_bits}

    def allocate(self,size,alignment):
        require(_uint(size) and type(alignment) is int and 4<=alignment<=4096 and alignment&(alignment-1)==0,
                'INVALID_ARGUMENT','Invalid allocation size/alignment')
        with self._lock:
            overhead=alignment-1 if size else 0
            require(size<=U64_MAX-overhead,'RESOURCE_LIMIT','Allocation size overflow')
            capacity=size+overhead
            checked_span(0,capacity,bits=self.pointer_bits)
            require(capacity<=self.budget_bytes-self.stats()['backing_bytes'],'RESOURCE_LIMIT','Allocator budget exceeded')
            try:
                backing=self._allocate_backing(capacity)
                require(isinstance(backing,np.ndarray) and backing.dtype==np.uint8 and backing.ndim==1 and
                        backing.size==capacity and backing.flags.c_contiguous and backing.flags.writeable,
                        'RESOURCE_LIMIT','Invalid allocator backing')
                shift=(-int(backing.ctypes.data))%alignment if size else 0
                checked_span(int(backing.ctypes.data) if capacity else 0,capacity,bits=self.pointer_bits)
                data=backing[shift:shift+size]
                checked_span(int(data.ctypes.data) if size else 0,size,bits=self.pointer_bits)
                token=self._next+1
                block=MemoryBlock(self,token,backing,data,alignment)
                self._entries[token]=(weakref.ref(block),capacity)
                self._next=token
                return block
            except (MemoryError,ValueError,OverflowError) as exc:
                if isinstance(exc,ContractError): raise
                raise ContractError('RESOURCE_LIMIT','Aligned allocation failed') from exc

    def release(self,block):
        with self._lock:
            require(isinstance(block,MemoryBlock) and block._allocator is self and not block.released and
                    self._entries.get(block._token,(lambda:None,0))[0]() is block,
                    'INVALID_ARGUMENT','Foreign or released memory block')
            self._entries.pop(block._token)
            block.released=True
            block.data=block.backing=None
            if block._resource_ticket is not None:block._resource_ticket.close()


class ClockSource(ABC):
    domain='host_monotonic'
    unit='ns'
    @abstractmethod
    def now_ns(self): pass


class PCClock(ClockSource):
    domain='host_perf_counter'
    def now_ns(self):
        try: return time.perf_counter_ns()
        except Exception: return None


class Synchronizer(ABC):
    @abstractmethod
    def for_device(self,blocks): pass
    @abstractmethod
    def for_cpu(self,blocks): pass
    def recover(self): return False


class PCSynchronizer(Synchronizer):
    semantics='same_process_host_coherent_no_dma'
    def _check(self,blocks):
        require(isinstance(blocks,tuple),'INVALID_ARGUMENT','Tuple of borrowed blocks required')
        for block in blocks:
            require(isinstance(block,MemoryBlock) and not block.released and block.memory_domain=='host',
                    'INVALID_STATE','Cannot synchronize foreign-domain or released memory')
            checked_span(block.address,block.data.nbytes)
        return True
    def for_device(self,blocks): return self._check(blocks)
    def for_cpu(self,blocks): return self._check(blocks)
    def recover(self): return True


class Platform(ABC):
    api_version=PLATFORM_API_VERSION
    @abstractmethod
    def open_read(self,path): pass

    def _retain_resources(self,owner,reason):
        key=(self.platform_id,id(owner))
        with _RETENTION_LOCK:
            _RETAINED[key]=RetainedResource(f'{self.platform_id}:{id(owner)}',self.platform_id,reason,owner)

    def _release_retained_resources(self,owner):
        with _RETENTION_LOCK: _RETAINED.pop((self.platform_id,id(owner)),None)

    def read_blob(self,path,limit,*,trace=None):
        from .tracing import phase,safe_record
        with phase(trace,'platform.read'):
            with self.open_read(path) as source:
                size=source.size
                require(_uint(size) and _uint(limit),'INVALID_ARGUMENT','Invalid source size/limit')
                require(size<=limit,'RESOURCE_LIMIT','Read source exceeds limit')
                value=read_exact(source,0,size)
                safe_record(trace,'platform.read.result',data={'platform_id':self.platform_id,'bytes':len(value),'status':'OK'})
                return value

    def allocate(self,size,alignment,*,trace=None):
        from .tracing import phase,safe_record
        with phase(trace,'platform.allocate'):
            require(_uint(size) and type(alignment) is int and 4<=alignment<=4096 and alignment&(alignment-1)==0,'INVALID_ARGUMENT','Invalid allocation')
            capacity=size+(alignment-1 if size else 0)
            ticket=self.ledger.reserve('arena',capacity,label='aligned_backing')
            try:
                block=self.allocator.allocate(size,alignment)
                block._resource_ticket=ticket
                ticket.resize(block.backing.nbytes,resident_bytes=block.backing.nbytes)
            except BaseException:
                if 'block' in locals():block.close()
                ticket.close();raise
            safe_record(trace,'platform.allocate.result',data={'platform_id':self.platform_id,'size':size,
                        'backing_bytes':block.backing.nbytes,'alignment':alignment,'status':'OK'})
            return block


class PCPlatform(Platform):
    def __init__(self,*,allocator=None,clock=None,synchronizer=None,ledger=None):
        self.ledger=ResourceLedger() if ledger is None else ledger
        require(isinstance(self.ledger,ResourceLedger),'INVALID_ARGUMENT','ResourceLedger required')
        self.allocator=PCAllocator() if allocator is None else allocator
        self.clock=PCClock() if clock is None else clock
        self.synchronizer=PCSynchronizer() if synchronizer is None else synchronizer
        require(isinstance(self.allocator,AlignedAllocator) and isinstance(self.clock,ClockSource) and
                isinstance(self.synchronizer,Synchronizer),'INVALID_ARGUMENT','Invalid platform services')
        self.platform_id='pc:'+uuid.uuid4().hex
        self._sources=weakref.WeakSet()

    def open_read(self,path):
        source=PCFileSource(path)
        self._sources.add(source)
        return source

    def stats(self):
        return {**self.allocator.stats(),'open_sources':sum(s._stream is not None for s in self._sources),
                'retained_resources':len(retained_resources(self.platform_id))}

    def resource_info(self):return self.ledger.snapshot()


def resolve_platform(platform=None):
    value=PCPlatform() if platform is None else platform
    require(isinstance(value,Platform) and type(value.api_version) is int and value.api_version==PLATFORM_API_VERSION,
            'INVALID_ARGUMENT','Platform API 1 required')
    require(isinstance(value.allocator,AlignedAllocator) and isinstance(value.clock,ClockSource) and
            isinstance(value.synchronizer,Synchronizer),'INVALID_ARGUMENT','Platform services required')
    require(isinstance(getattr(value,'platform_id',None),str) and bool(value.platform_id),
            'INVALID_ARGUMENT','Platform identity required')
    checked_span(0,0,bits=value.allocator.pointer_bits)
    if not hasattr(value,'ledger'):value.ledger=ResourceLedger()
    require(isinstance(value.ledger,ResourceLedger),'INVALID_ARGUMENT','Platform resource ledger required')
    return value
