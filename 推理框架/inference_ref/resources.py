"""API 1 managed payload admission, not process RSS or Python object sizing."""
from contextlib import contextmanager
from contextvars import ContextVar
import threading

from .contracts import ContractError,require

RESOURCE_API_VERSION=1
U64_MAX=(1<<64)-1
CATEGORIES=('arena','c_metadata','c_profiles','trace','task_staging','task_records','session_records','task_events')
_PREPARE_LEDGER=ContextVar('prepare_resource_ledger',default=None)


def _uint(n):return type(n) is int and 0<=n<=U64_MAX


class Reservation:
    def __init__(self,ledger,key):self._ledger,self._key,self._closed=ledger,key,True
    def resize(self,bytes,*,resident_bytes=None,count=None):
        require(not self._closed,'INVALID_STATE','Resource reservation closed')
        self._ledger._resize(self._key,bytes,resident_bytes,count)
    def close(self):
        if not self._closed:self._ledger._release(self._key);self._closed=True
    def __del__(self):
        try:self.close()
        except Exception:pass


class ResourceLedger:
    def __init__(self,*,budget_bytes=64*1024*1024,byte_limits=None,count_limits=None,max_entries=100000):
        require(_uint(budget_bytes) and type(max_entries) is int and 1<=max_entries<=1000000,'INVALID_ARGUMENT','Invalid resource budget')
        self.budget_bytes,self.max_entries=budget_bytes,max_entries
        self.byte_limits={} if byte_limits is None else dict(byte_limits)
        self.count_limits={} if count_limits is None else dict(count_limits)
        for limits in (self.byte_limits,self.count_limits):
            require(set(limits)<=set(CATEGORIES) and all(_uint(n) for n in limits.values()),'INVALID_ARGUMENT','Invalid category limits')
        self._rows={};self._next=0;self._lock=threading.RLock();self.fail_after=None
        self._live=self._resident=self._peak=self._peak_resident=self._rejected=0
        self._categories={c:{'live_bytes':0,'resident_bytes':0,'live_count':0,'live_entries':0,
            'peak_bytes':0,'peak_resident_bytes':0,'peak_count':0} for c in CATEGORIES}

    def _admit(self,category,bytes,resident,count,old_bytes=0,old_resident=0,old_count=0,*,new=False):
        require(category in self._categories and all(_uint(n) for n in (bytes,resident,count)) and resident<=bytes,'INVALID_ARGUMENT','Invalid resource reservation')
        state=self._categories[category]
        growth=bytes>old_bytes or count>old_count or new
        allowed=(self._live-old_bytes+bytes<=self.budget_bytes and state['live_bytes']-old_bytes+bytes<=self.byte_limits.get(category,U64_MAX)
            and state['live_count']-old_count+count<=self.count_limits.get(category,U64_MAX)
            and (not new or len(self._rows)<self.max_entries))
        require(self.fail_after is None or type(self.fail_after) is int and self.fail_after>=0,'INVALID_ARGUMENT','Invalid allocation fault counter')
        if not allowed or growth and self.fail_after==0:
            self._rejected+=1;raise ContractError('RESOURCE_LIMIT','Managed resource budget or injected reservation failure')
        if growth and self.fail_after is not None:self.fail_after-=1

    def _account(self,category,db,dr,dc,de):
        self._live+=db;self._resident+=dr;self._peak=max(self._peak,self._live);self._peak_resident=max(self._peak_resident,self._resident)
        s=self._categories[category];s['live_bytes']+=db;s['resident_bytes']+=dr;s['live_count']+=dc;s['live_entries']+=de
        s['peak_bytes']=max(s['peak_bytes'],s['live_bytes']);s['peak_resident_bytes']=max(s['peak_resident_bytes'],s['resident_bytes']);s['peak_count']=max(s['peak_count'],s['live_count'])

    def reserve(self,category,bytes,*,resident_bytes=0,count=1,label=''):
        require(isinstance(label,str) and len(label)<=128,'INVALID_ARGUMENT','Resource label too long')
        with self._lock:
            self._admit(category,bytes,resident_bytes,count,new=True)
            key=self._next+1;token=Reservation(self,key)
            try:self._rows[key]=(category,bytes,resident_bytes,count,label)
            except MemoryError as exc:raise ContractError('RESOURCE_LIMIT','Resource record allocation failed') from exc
            self._next=key;token._closed=False;self._account(category,bytes,resident_bytes,count,1)
            return token

    def _resize(self,key,bytes,resident,count):
        with self._lock:
            require(_uint(bytes),'INVALID_ARGUMENT','Invalid reservation byte size')
            category,old_b,old_r,old_c,label=self._rows[key]
            resident=min(old_r,bytes) if resident is None else resident;count=old_c if count is None else count
            self._admit(category,bytes,resident,count,old_b,old_r,old_c)
            self._rows[key]=(category,bytes,resident,count,label);self._account(category,bytes-old_b,resident-old_r,count-old_c,0)

    def _release(self,key):
        with self._lock:
            row=self._rows.pop(key,None)
            if row is not None:self._account(row[0],-row[1],-row[2],-row[3],-1)

    def snapshot(self):
        with self._lock:
            return {'format':'inference-resource-ledger','version':1,'measurement':'managed_payload_and_record_counts_not_rss',
                'budget_bytes':self.budget_bytes,'byte_limits':dict(self.byte_limits),'count_limits':dict(self.count_limits),
                'live_bytes':self._live,'resident_bytes':self._resident,'live_entries':len(self._rows),
                'peak_bytes':self._peak,'peak_resident_bytes':self._peak_resident,'rejected_reservations':self._rejected,
                'categories':{c:dict(s) for c,s in self._categories.items()},
                'entries':[{'id':k,'category':v[0],'bytes':v[1],'resident_bytes':v[2],'count':v[3],'label':v[4]} for k,v in self._rows.items()]}


@contextmanager
def prepare_resources(ledger):
    token=_PREPARE_LEDGER.set(ledger)
    try:yield
    finally:_PREPARE_LEDGER.reset(token)


class ResourceGroup:
    def __init__(self,ledger=None):
        self.ledger=_PREPARE_LEDGER.get() if ledger is None else ledger
        self._tokens=[]
    def _create(self,factory):return factory()
    def allocate(self,factory,bytes,*,category='c_metadata',label=''):
        token=self.ledger.reserve(category,bytes,label=label) if self.ledger is not None else None
        try:
            value=self._create(factory)
            if token is not None:token.resize(bytes,resident_bytes=bytes);self._tokens.append(token)
            return value
        except BaseException as exc:
            if token is not None:token.close()
            if isinstance(exc,MemoryError):raise ContractError('RESOURCE_LIMIT','Native metadata allocation failed') from exc
            raise
    def close(self):
        for token in self._tokens:token.close()
        self._tokens.clear()
    def __del__(self):
        try:self.close()
        except Exception:pass
