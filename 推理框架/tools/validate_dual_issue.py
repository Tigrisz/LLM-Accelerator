"""Rebuild original/portable RTL; same frozen ELF, minimal cases, two simulators."""
import argparse
import difflib
import json
from pathlib import Path
import re
import subprocess
import sys

from reproduce import ROOT,clean_environment,run_command,write_json,sha,validate_output
from rv32_rtl import select_rtl
from toolchain_integrity import verify_archive_install
from rv32_trace import compare_trace,audit_trace,parse_diagnostic,check_original_failure

FROZEN_ELF='18c4029261ed0d0b0988089a3724405b029986a74992964af153116962fa76b0'


def run(output,toolchain,elf):
    output=validate_output(ROOT,output);tc=Path(toolchain).resolve();elf=Path(elf).resolve()
    if not output.is_relative_to(ROOT/'build'):raise ValueError('Fresh output under workspace/build required')
    if sha(elf)!=FROZEN_ELF:raise ValueError('Expected original T4 frozen ELF; no firmware workaround allowed')
    lock=json.loads((ROOT/'tools/target_toolchain.lock.json').read_text());receipt=json.loads((tc.parent/'receipt.json').read_text())
    if receipt.get('lock')!=lock or receipt.get('passed') is not True:raise ValueError('Prepared toolchain receipt mismatch')
    archive=Path(receipt.get('archive_path',str(tc.parent.parent/lock['archive_url'].rsplit('/',1)[1])))
    identity=verify_archive_install(archive,tc,lock)
    output.mkdir(parents=True,exist_ok=False);commands=[]
    def execute(name,args,cwd=None,timeout=120):
        command=list(map(str,args));r=run_command(command,cwd=cwd,env=clean_environment(),stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=timeout)
        (output/(name+'.stdout')).write_text(r.stdout,encoding='utf-8');(output/(name+'.stderr')).write_text(r.stderr,encoding='utf-8')
        commands.append(dict(name=name,command=command,cwd=str(cwd) if cwd else None,exit_code=r.returncode))
        with (output/'commands.jsonl').open('a',encoding='utf-8') as stream:stream.write(json.dumps(commands[-1],ensure_ascii=False)+'\n')
        return r
    def required(name,args,**kwargs):
        r=execute(name,args,**kwargs)
        if r.returncode:raise ValueError(name+' failed; consult stage logs')
        return r
    cc=tc/'bin/riscv-none-elf-gcc';objcopy=tc/'bin/riscv-none-elf-objcopy';objdump=tc/'bin/riscv-none-elf-objdump'
    cases=[]
    def image(name,source=None,expected=None):
        directory=output/name;directory.mkdir()
        target=directory/'firmware.elf'
        if source is None:target.write_bytes(elf.read_bytes())
        else:
            path=directory/'case.S';path.write_text(source,encoding='utf-8')
            required(name+'_compile',[cc,'-march='+lock['target_arch'],'-mabi=ilp32','-nostdlib','-nostartfiles','-T',ROOT/'c/rv32/link.ld',path,'-o',target])
        required(name+'_objcopy',[objcopy,'-O','binary',target,directory/'firmware.bin'])
        required(name+'_disassembly',[objdump,'-d',target])
        raw=(directory/'firmware.bin').read_bytes();raw+=bytes((-len(raw))%4)
        if len(raw)>65536:raise ValueError('ELF binary exceeds TCM')
        # Full RAM initialization removes irrelevant readmemh warnings/X padding.
        raw+=bytes(65536-len(raw))
        (directory/'firmware.hex').write_text(''.join(f'{int.from_bytes(raw[i:i+4],"little"):08x}\n' for i in range(0,len(raw),4)),encoding='ascii')
        cases.append(dict(name=name,directory=directory,elf_sha256=sha(target),expected=expected))
    image('full')
    image('minimal',(ROOT/'c/rv32/dual_dependency_repro.S').read_text(),20)
    # RAW/WAW, destination separation, shift/add variants, two input ranges.
    for i,(second,dest,expected,initial) in enumerate([
        ('andi a2,a2,-4','a2',20,0xff98),('andi t2,a2,-4','t2',20,0xff98),
        ('addi a2,a2,3','a2',26,0xff98),('slli t2,a2,1','t2',46,0xff98),
        ('andi a2,a4,-4','a2',0xff80,0xff98),('andi a2,a2,-4','a2',116,0xfff8),
        ('addi t2,a2,-3','t2',116,0xfff8),('slli a2,a2,1','a2',238,0xfff8)]):
        source=f'.section .text.start\n.globl _start\n_start:\n li a2,{initial}\n li a4,0xff80\n j seq\n .balign 8\nseq:\n addi a2,a2,-1\n sub a2,a2,a4\n {second}\n li t6,{expected}\n xor a0,{dest},t6\n lui t0,0x10000\n sw a0,4(t0)\n1: j 1b\n'
        image(f'variant_{i}',source,expected)
    results=[];selections={}
    for mode in ('upstream','portable-metadata'):
        data,selection=select_rtl(ROOT,mode);selections[mode]=selection;rtl=output/(mode+'.sv');rtl.write_bytes(data)
        for dual in (0,1):
            label=mode+'_'+str(dual);sim=output/(label+'_verilator')
            required(label+'_build',['verilator','--cc','--exe','--build','-j','4','-O2','-Wno-fatal','--top-module','qinglong_soc','-GRAM_WORDS=16384','-GCLOCK_HZ=27000000',"-GSIM_FAST_UART=1'b1",f'-GDUAL_ISSUE={dual}','-GINIT_FILE="firmware.hex"','--Mdir',sim,rtl,ROOT/'c/rv32/diagnostic_driver.cpp'],timeout=300)
            iv=output/(label+'_iv')
            required(label+'_iv_build',['iverilog','-g2012','-s','icarus_driver',f'-Picarus_driver.DUAL={dual}','-Picarus_driver.LIMIT=4000000','-Picarus_driver.TRACE=0','-o',iv,rtl,ROOT/'c/rv32/icarus_driver.sv'])
            for case in cases:
                name=case['name'];directory=case['directory'];trace=output/(label+'_'+name+'.trace')
                vl=execute(label+'_'+name,[sim/'Vqinglong_soc','4000000' if name=='full' else '2000',trace],cwd=directory)
                observed=parse_diagnostic(vl.stdout,vl.returncode)
                values=[observed[key] for key in ('done','target_exit','cycles','retired','trace_rows')]
                good=vl.returncode==0 and values[0]==1 and values[1]==0 and not observed['traps']
                trace_evidence=audit_trace(trace,values[3],values[4],require_full=good or name!='full',max_cycle=values[2])
                # An upstream/current-Verilator mismatch is retained as a failure, never called unknown.
                if not (mode=='upstream' and dual==1) and not good:raise ValueError(label+' '+name+' unexpectedly failed')
                if not good and (observed['done']!=1 or observed['simulator_exit']!=1 or observed['target_exit']==0 and not observed['traps']):
                    raise ValueError('Unproven/unrelated termination cannot stand in for an observed upstream failure')
                if mode=='upstream' and dual==1 and name=='minimal':check_original_failure(name,observed,trace_evidence['critical_writes'])
                if name=='full' and good:
                    for marker in ('VALUE_0=00000014','VALUE_1=ffffffe7','ZERO_0=00000000','ZERO_1=fffffffb','COMPLETED=00000004','TARGET_STATUS=00000000'):
                        if marker not in vl.stdout:raise ValueError('Full chain output incomplete')
                    if values[3]!=values[4]:raise ValueError('Positive full trace truncated')
                other=execute(label+'_'+name+'_iv',['vvp',iv],cwd=directory,timeout=500)
                if other.returncode!=0 or 'DONE exit=0' not in other.stdout:raise ValueError('Icarus positive control failed')
                results.append(dict(mode=mode,dual_issue=dual,case=name,elf_sha256=case['elf_sha256'],verilator_passed=good,
                    target_exit=values[1],cycles=values[2],retired=values[3],trace_rows=values[4],trace_audit=trace_evidence,observed=observed,iverilog_passed=True))
    raw=next(r for r in results if r['mode']=='upstream' and r['dual_issue']==1 and r['case']=='minimal')
    if raw['verilator_passed'] is not False:raise ValueError('Original minimal failure was not reproduced')
    full_count=next(r['retired'] for r in results if r['mode']=='upstream' and r['dual_issue']==0 and r['case']=='full')
    comparisons={name:compare_trace(output/'upstream_0_full.trace',output/(name+'_full.trace'),expected_count=full_count) for name in ('upstream_1','portable-metadata_0','portable-metadata_1')}
    full=next(r for r in results if r['mode']=='upstream' and r['dual_issue']==1 and r['case']=='full')
    check_original_failure('full',full['observed'],{},comparisons['upstream_1'])
    if comparisons['upstream_1'].get('index')!=1522 or any(not comparisons[name]['equal'] for name in ('portable-metadata_0','portable-metadata_1')):
        raise ValueError('Frozen ELF first difference or corrected architectural trace changed')
    original,_=select_rtl(ROOT,'upstream');portable,_=select_rtl(ROOT,'portable-metadata')
    (output/'compatibility.patch').write_text(''.join(difflib.unified_diff(original.decode().splitlines(True),portable.decode().splitlines(True),fromfile='upstream/qinglong_all.sv',tofile='portable/qinglong_all.sv')),encoding='utf-8')
    report=dict(format='t4-dual-diagnosis',version=1,passed=True,scope='two-simulator evidence for frozen ELF and local RTL compatibility overlay',
        frozen_elf_sha256=FROZEN_ELF,toolchain_integrity=identity,rtl_selections=selections,results=results,trace_comparisons=comparisons,
        versions={name:required(name+'_version',command).stdout for name,command in [('verilator',['verilator','--version']),('iverilog',['iverilog','-V'])]},
        minimal_cases=9,profile_case_runs=len(results),board_verified=False,formal_equivalence=None,full_stack_worst_case=None,
        model_binding=None,quantization_binding=None,commands=commands)
    write_json(output/'report.json',report);print(json.dumps({'passed':True,'report':str(output/'report.json'),'profile_case_runs':len(results)}));return report


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--toolchain',type=Path,required=True);parser.add_argument('--elf',type=Path,required=True);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    fresh=not args.output.exists()
    try:run(args.output,args.toolchain,args.elf)
    except Exception as error:
        output=args.output.resolve()
        if fresh and output.is_relative_to(ROOT/'build') and output.is_dir() and not (output/'report.json').exists():
            write_json(output/'failure.json',{'passed':False,'error':type(error).__name__,'message':str(error)})
        print(str(error),file=sys.stderr);raise SystemExit(1)
