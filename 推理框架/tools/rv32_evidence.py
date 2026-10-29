"""Bounded RV32 evidence gates. Successful PC builds never imply RTL/board pass."""
import struct
import re


def check_elf(blob):
    if len(blob)<52 or blob[:7]!=b'\x7fELF\x01\x01\x01':raise ValueError('ELF32 little-endian v1 required')
    h=struct.unpack_from('<HHIIIIIHHHHHH',blob,16)
    kind,machine,version,entry,phoff,shoff,flags,ehsize,phsize,phnum,shsize,shnum,shstr=h
    if (kind,machine,version,entry,flags,ehsize,phsize)!=(2,243,1,0,0,52,32):raise ValueError('RV32 bare-metal soft-float ABI/no RVC required')
    if not phnum or phnum>64 or phoff>len(blob) or phnum*phsize>len(blob)-phoff:raise ValueError('Invalid program headers')
    loads=[]
    for i in range(phnum):
        p=struct.unpack_from('<IIIIIIII',blob,phoff+i*phsize)
        tag,offset,vaddr,paddr,filesz,memsz,permissions,alignment=p
        if tag!=1:continue
        if filesz>memsz or offset>len(blob) or filesz>len(blob)-offset or vaddr!=paddr or vaddr>65536 or memsz>65536-vaddr:
            raise ValueError('Load segment outside 64KiB TCM or file')
        if any(memsz and x['memory_bytes'] and vaddr<x['address']+x['memory_bytes'] and x['address']<vaddr+memsz for x in loads):
            raise ValueError('Overlapping load segments')
        loads.append(dict(address=vaddr,file_bytes=filesz,memory_bytes=memsz,flags=permissions))
    if not any(x['flags']&1 and x['address']<=entry<x['address']+x['file_bytes'] for x in loads):raise ValueError('Entry is not in executable initialized memory')
    return {'passed':True,'class':32,'endian':'little','machine':243,'flags':flags,'entry':entry,'load_segments':loads}


def check_simulation(row,expected):
    good=(row.get('simulator_exit')==0 and row.get('target_status')==0 and row.get('completed')==4 and
          row.get('values')==expected and row.get('runtime_abi')==2 and row.get('pointer_bytes')==4 and
          row.get('done') is True and row.get('stack_started') is True and row.get('stack_violations')==0 and row.get('traps')==0 and
          type(row.get('min_sp')) is int and 0xe000<=row['min_sp']<=0x10000 and row['min_sp']%16==0)
    if not good:raise ValueError('RTL result, ABI, termination or stack evidence failed/incomplete')
    return {'passed':True,'simulation_observed_stack_bytes':65536-row['min_sp'],
            'target_stack_worst_case':None,'board_verified':False}


def check_macros(macros):
    required={'__riscv_xlen':'32','__SIZEOF_POINTER__':'4','__SIZEOF_SIZE_T__':'4',
              '__BYTE_ORDER__':'__ORDER_LITTLE_ENDIAN__','__riscv_float_abi_soft':'1'}
    if any(macros.get(k)!=v for k,v in required.items()) or any(k in macros for k in ('__riscv_compressed','__riscv_flen','__riscv_atomic','__riscv_vector')):
        raise ValueError('Measured compiler macros do not match supported RV32/ILP32 soft-float target')
    return {'passed':True,'measured':required}


def check_attributes(text):
    match=re.search(r'Tag_RISCV_arch:\s*"([^"]+)"',text)
    if not match or not re.search(r'Tag_RISCV_stack_align:\s*16-bytes',text):raise ValueError('Linked ISA/stack attributes missing')
    extensions={re.sub(r'\d+p\d+$','',word) for word in match.group(1).split('_')}
    if not {'rv32i','m','zicsr','zifencei'}<=extensions or not extensions<={'rv32i','m','zicsr','zifencei','zmmul'}:
        raise ValueError('Linked library introduced unsupported ISA requirements')
    return {'passed':True,'architecture':match.group(1),'stack_alignment':16}


def classify_simulation(row,expected):
    try:return check_simulation(row,expected)
    except ValueError as error:
        confirmed=(type(row.get('traps')) is int and row['traps']>0 or
            type(row.get('stack_violations')) is int and row['stack_violations']>0 or row.get('done') is True and (
            type(row.get('target_status')) is int and row['target_status']!=0 or
            type(row.get('traps')) is int and row['traps']>0 or
            row.get('values') is not None and row['values']!=expected or
            type(row.get('stack_violations')) is int and row['stack_violations']>0))
        return {'passed':False if confirmed else None,'failure_confirmed':confirmed,
                'state':'failed' if confirmed else 'unproven','reason':str(error),'root_cause':None}


def _summary(row):
    fields=row.get('fields',{})
    required=('RTL_DONE','RTL_EXIT','RTL_CYCLES','RTL_MIN_SP','RTL_STACK_VIOLATIONS','RTL_TRAPS','RTL_STACK_STARTED')
    if any(type(fields.get(key)) is not int for key in required):raise ValueError('Complete RTL summary required for negative control')
    return fields


def check_wrong_expected(row):
    fields=_summary(row)
    if not (row.get('simulator_exit')==1 and row.get('target_status')==10 and row.get('done') is True and
        row.get('traps')==0 and row.get('stack_violations')==0 and row.get('stack_started') is True and
        type(row.get('min_sp')) is int and 0xe000<=row['min_sp']<=0x10000 and row['min_sp']%16==0 and
        fields['RTL_DONE']==1 and fields['RTL_EXIT']==10 and fields['RTL_TRAPS']==fields['RTL_STACK_VIOLATIONS']==0 and
        fields['RTL_STACK_STARTED']==1 and fields['RTL_MIN_SP']==row['min_sp'] and fields['RTL_CYCLES']>0):
        raise ValueError('Wrong-expected control ended in an unrelated failure')
    return {'rejected':True,'reason':'target mismatch produced exit 10, complete RTL summary, no trap or stack violation'}


def check_watchdog(row,limit):
    fields=_summary(row)
    if not (row.get('simulator_exit')==1 and row.get('done') is False and row.get('traps')==0 and row.get('stack_violations')==0 and
        fields['RTL_DONE']==0 and fields['RTL_EXIT']==0 and fields['RTL_CYCLES']==limit and
        fields['RTL_TRAPS']==fields['RTL_STACK_VIOLATIONS']==0 and fields['RTL_STACK_STARTED'] in (0,1) and
        0xe000<=fields['RTL_MIN_SP']<=0x10000 and fields['RTL_MIN_SP']%16==0):
        raise ValueError('Watchdog control lacks a clean cycle-limited RTL termination')
    return {'rejected':True,'cycle_limit':limit,'reason':'complete RTL summary at requested cycle limit; no trap/host crash'}
