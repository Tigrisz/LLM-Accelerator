"""Check actual retirement files and distinguish the specified fault from noise."""
from itertools import zip_longest
from pathlib import Path
import re


def parse_row(line,index):
    parts=line.split()
    if len(parts)!=7 or not all(re.fullmatch(r'[0-9]+',p) for p in parts[:3]) or not all(re.fullmatch(r'[0-9a-fA-F]{1,8}',p) for p in parts[3:]):
        raise ValueError('Malformed retirement trace line')
    row=tuple([int(p) for p in parts[:3]]+[int(p,16) for p in parts[3:]])
    if row[0]!=index or row[2] not in (0,1) or row[3]%4 or row[5]>31:raise ValueError('Trace index/lane/PC/register invalid')
    return row


def audit_trace(path,retired,declared_rows,*,require_full,max_cycle=None):
    if type(retired) is not int or type(declared_rows) is not int or not 0<declared_rows<=retired:
        raise ValueError('Invalid retirement/trace counters')
    if require_full and retired!=declared_rows:raise ValueError('Positive trace was intentionally truncated')
    count=0;previous=-1;critical={}
    with Path(path).open() as stream:
        for index,line in enumerate(stream):
            row=parse_row(line,index)
            if row[1]<previous or max_cycle is not None and row[1]>=max_cycle:raise ValueError('Trace cycle order/range invalid')
            previous=row[1];count+=1
            if row[3] in (0x18,0x1c,0x20,0x24):critical[row[3]]=row[4:]
    if count!=declared_rows:raise ValueError('Actual trace file length does not match completion counters')
    return {'rows':count,'retired':retired,'full':count==retired,'critical_writes':critical}


def compare_trace(left,right,expected_count=None):
    count=0
    with Path(left).open() as a,Path(right).open() as b:
        for index,(x,y) in enumerate(zip_longest(a,b)):
            if x is None or y is None:raise ValueError('Trace files have different lengths before a matching comparison completed')
            first=parse_row(x,index);second=parse_row(y,index)
            if first[3:]!=second[3:]:return {'equal':False,'index':index,'left':x.strip(),'right':y.strip()}
            count+=1
    if not count or expected_count is not None and count!=expected_count:raise ValueError('Empty or common truncated trace prefix')
    return {'equal':True,'instructions':count}


def parse_diagnostic(stdout,returncode):
    summaries=re.findall(r'^DONE=(\d+) EXIT=(\d+) CYCLES=(\d+) RETIRED=(\d+) TRACE_ROWS=(\d+)$',stdout,re.M)
    if len(summaries)!=1:raise ValueError('Exactly one complete diagnostic summary required')
    done,code,cycles,retired,rows=map(int,summaries[0])
    traps=[]
    for line in stdout.splitlines():
        if line.startswith('TRAP='):
            match=re.fullmatch(r'TRAP=([0-9a-fA-F]+),([0-9a-fA-F]+),([0-9a-fA-F]+)',line)
            if not match:raise ValueError('Malformed trap record')
            traps.append(tuple(int(p,16) for p in match.groups()))
    return dict(simulator_exit=returncode,done=done,target_exit=code,cycles=cycles,retired=retired,trace_rows=rows,traps=traps)


def check_original_failure(case,result,critical_writes,difference=None):
    if result.get('simulator_exit')!=1 or result.get('done')!=1:raise ValueError('Original fault not reproduced: tool failure/watchdog is unproven')
    if case=='minimal':
        expected={0x18:(0xfff60613,12,0xff97),0x1c:(0x40e60633,12,0x17),0x20:(0xffc67613,12,0xff94),0x24:(0x01464513,10,3)}
        if result.get('target_exit')!=3 or result.get('traps') or any(critical_writes.get(pc)!=value for pc,value in expected.items()):
            raise ValueError('Original minimal arithmetic fault signature differs')
    elif case=='full':
        if result.get('target_exit')!=133 or result.get('traps')!=[(0x264c,5,0x10000)]:raise ValueError('Original full-chain trap signature differs')
        if not difference or difference.get('equal') is not False or difference.get('index')!=1522:raise ValueError('Original first-difference position differs')
        left=parse_row(difference['left'],1522);right=parse_row(difference['right'],1522)
        if left[3:]!=(0x3f18,0xffc67613,12,0x14) or right[3:]!=(0x3f18,0xffc67613,12,0xff94):
            raise ValueError('Original first-difference instruction/value signature differs')
    else:raise ValueError('Unknown required reproduction case')
    return {'reproduced':True,'confirmed_target_failure':True,'signature':case}
