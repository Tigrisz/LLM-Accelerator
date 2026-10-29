"""T4 explicit RV32/RTL acceptance. Requires a locally prepared pinned toolchain."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'tools'))
import numpy as np
from inference_ref.c_backend import FLAGS
from inference_ref.model_package import write_package,read_package
from inference_ref.package_validation import chain_definition,_evaluate
from inference_ref import reference,oracle
from inference_ref.static_export import export_static
from reproduce import run_command,clean_environment,write_json,sha
from rv32_evidence import check_elf,check_macros,check_simulation,check_attributes,classify_simulation,check_wrong_expected,check_watchdog
from toolchain_integrity import verify_archive_install
from rv32_rtl import MODES,select_rtl
from rv32_profiles import parameters as rtl_parameters,verilator_arguments,profile_record,complete_dual_validation,require_dual_pass,ProfileValidationError


def array(name,data,alignment=4):
    return f'_Alignas({alignment}) static const unsigned char {name}[{len(data)}]={{'+','.join(str(x) for x in data)+'};\n'


def command(args,cwd=None,timeout=120):
    return run_command(list(map(str,args)),cwd=cwd,env=clean_environment(),stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=timeout)


def parse_output(run):
    fields={}
    for line in run.stdout.splitlines():
        if '=' in line:
            key,value=line.split('=',1)
            if re.fullmatch('[A-Z_0-9]+',key) and re.fullmatch('[0-9a-fA-F]+',value):fields[key]=int(value,10 if key.startswith('RTL_') else 16)
    def signed(n):return n-(1<<32) if n>=1<<31 else n
    return dict(simulator_exit=run.returncode,target_status=fields.get('TARGET_STATUS'),completed=fields.get('COMPLETED'),
        values=[signed(fields[k]) for k in ('VALUE_0','VALUE_1')] if all(k in fields for k in ('VALUE_0','VALUE_1')) else None,
        zero_values=[signed(fields[k]) for k in ('ZERO_0','ZERO_1')] if all(k in fields for k in ('ZERO_0','ZERO_1')) else None,
        runtime_abi=fields.get('RUNTIME_ABI'),pointer_bytes=fields.get('POINTER_BYTES'),min_sp=fields.get('RTL_MIN_SP'),
        stack_violations=fields.get('RTL_STACK_VIOLATIONS'),stack_started=fields.get('RTL_STACK_STARTED')==1,done=fields.get('RTL_DONE')==1,traps=fields.get('RTL_TRAPS'),fields=fields)


def run(output,toolchain,rtl_mode='portable-metadata'):
    output=Path(output).resolve();tc=Path(toolchain).resolve()
    if output.exists() or not output.is_relative_to(ROOT/'build'):raise ValueError('Fresh output below workspace/build required')
    lock=json.loads((ROOT/'tools/target_toolchain.lock.json').read_text())
    cc=tc/lock['compiler'];prefix=tc/'bin/riscv-none-elf-'
    def tool(name):return Path(str(prefix)+name)
    for p in (cc,tool('objcopy'),tool('readelf'),tool('nm'),tool('objdump')):
        if not p.is_file():raise ValueError('Missing target tool: '+str(p))
    receipt_path=tc.parent/'receipt.json'
    receipt=json.loads(receipt_path.read_text())
    if receipt.get('passed') is not True or receipt.get('version')!=1 or receipt.get('lock')!=lock or receipt.get('compiler_sha256')!=sha(cc) or receipt.get('archive_sha256')!=lock['archive_sha256']:
        raise ValueError('Toolchain preparation receipt does not match the pinned compiler')
    archive=Path(receipt.get('archive_path',str(tc.parent.parent/lock['archive_url'].rsplit('/',1)[1])))
    install_integrity=verify_archive_install(archive,tc,lock)
    tool_hashes={str(p.relative_to(tc)):sha(p) for p in (cc,tool('objcopy'),tool('readelf'),tool('nm'),tool('objdump'),tool('as'),tool('ld'))}
    if not shutil.which('verilator'):raise ValueError('Verilator is required for the actual CPU RTL')
    source_manifest=json.loads((ROOT/'docs/target_platform_sources/manifest.json').read_text())
    rtl=ROOT/'docs/target_platform_sources/main/fpga/generated/qinglong_all.sv'
    source=next(x for x in source_manifest['sources'] if x['id']=='main:fpga/generated/qinglong_all.sv')
    if sha(rtl)!=source['sha256'] or source['ref']!=lock['source_commit']:raise ValueError('Pinned RTL identity mismatch')
    selected,rtl_identity=select_rtl(ROOT,rtl_mode)
    output.mkdir(parents=True,exist_ok=False);commands=[]
    rtl=output/'selected_qinglong_all.sv';rtl.write_bytes(selected)
    def execute(args,name,cwd=None,timeout=120,allow_fail=False):
        r=command(args,cwd,timeout);commands.append(dict(command=list(map(str,args)),cwd=str(cwd) if cwd else None,exit_code=r.returncode,log=name))
        (output/(name+'.stdout')).write_text(r.stdout,encoding='utf-8');(output/(name+'.stderr')).write_text(r.stderr,encoding='utf-8')
        with (output/'commands.jsonl').open('a',encoding='utf-8') as stream:stream.write(json.dumps(commands[-1],ensure_ascii=False)+'\n')
        if r.returncode and not allow_fail:raise ValueError(name+' failed; see logs: '+r.stderr[-1500:])
        return r
    flags=['-march='+lock['target_arch'],'-mabi=ilp32',*FLAGS,'-Os','-ffreestanding','-fno-builtin','-msmall-data-limit=0',
        '-ffunction-sections','-fdata-sections','-fno-asynchronous-unwind-tables','-fstack-usage','-fno-stack-protector']
    macro_run=execute([cc,*flags,'-dM','-E','-x','c','/dev/null'],'macros')
    macros={line.split(None,2)[1]:line.split(None,2)[2] for line in macro_run.stdout.splitlines() if line.startswith('#define ') and len(line.split(None,2))==3}
    macro_check=check_macros(macros)
    version=execute([cc,'--version'],'compiler_version').stdout
    libs={}
    for name in ('libgcc.a','libc.a','libm.a'):
        p=Path(execute([cc,*flags,'-print-file-name='+name],'library_'+name).stdout.strip())
        if not p.is_file():raise ValueError('Selected library missing: '+name)
        libs[name]={'path':str(p),'sha256':sha(p)}
        if libs[name]['sha256']!=receipt['selected_libraries'][name]['sha256']:raise ValueError('Selected target library changed since preparation')
    model=output/'model';write_package(model,**chain_definition('int32'));package=read_package(model)
    exported=export_static(model,output/'export');image=(output/'export/execution.bin').read_bytes();weights=(output/'export/weights.bin').read_bytes()
    expected={};feeds={}
    for label,values in [('normal',[2,-3,4]),('zero',[0,0,0])]:
        feed={'x':np.array(values,np.int32)};a=_evaluate(package,feed,reference.execute)['y'];b=_evaluate(package,feed,oracle.execute)['y']
        if a.tobytes()!=b.tobytes():raise ValueError('Independent PC references differ')
        expected[label]=a.tolist();feeds[label]=feed['x'].tobytes()
    header='\n'.join(f'#define {k} {v}' for k,v in {'T4_TENSORS':len(package.tensors),'T4_NODES':len(package.nodes),
        'T4_ALIGNMENT':exported['alignment'],'T4_ACT_BYTES':exported['arenas']['activations'],'T4_WORK_BYTES':exported['arenas']['workspace'],
        'T4_INPUT_INDEX':next(i for i,t in enumerate(package.tensors) if t.role=='input'),
        'T4_OUTPUT_INDEX':next(i for i,t in enumerate(package.tensors) if t.role=='output')}.items())+'\n'
    header+=array('t4_image',image,64)+array('t4_weights',weights,exported['alignment'])
    # The first stage is explicitly an unquantized INT32 synthetic chain.
    for label in ('normal','zero'):
        values=[2,-3,4] if label=='normal' else [0,0,0]
        header+='static const int32_t t4_'+label+'_input[3]={'+','.join(map(str,values))+'};\n'
        header+='static const int32_t t4_'+label+'_expected[2]={'+','.join(map(str,expected[label]))+'};\n'
    (output/'chain_blob.h').write_text(header,encoding='utf-8')
    simulator_dir=output/'verilator_single';simulator_dir.mkdir()
    def simulator_command(directory,profile):
        return ['verilator','--cc','--exe','--build','-j','4','-O2','-Wno-fatal','--top-module','qinglong_soc',
            *verilator_arguments(rtl_parameters(profile)),'--Mdir',str(directory),str(rtl),str(ROOT/'c/rv32/sim_main.cpp')]
    simcmd=simulator_command(simulator_dir,'single_issue')
    execute(simcmd,'verilator_build',timeout=300)
    variants=[]
    for name,bad in [('normal',0),('bad_expected',1)]:
        directory=output/name;directory.mkdir();objects=[]
        sources=[ROOT/'c/rv32/start.S',ROOT/'c/rv32/firmware.c',ROOT/'c/src/ir_core.c',ROOT/'c/src/ir_static.c']
        for src in sources:
            obj=directory/(src.stem+'.o');objects.append(obj)
            execute([cc,*flags,'-I',ROOT/'c/include','-I',output,'-DT4_BAD_EXPECTED='+str(bad),'-c',src,'-o',obj],name+'_'+src.stem)
        elf=directory/'firmware.elf'
        execute([cc,*flags,'-nostdlib','-nostartfiles','-Wl,--gc-sections','-Wl,-Map='+str(directory/'firmware.map'),
            '-T',ROOT/'c/rv32/link.ld',*objects,'-Wl,--start-group','-lc','-lm','-lgcc','-Wl,--end-group','-o',elf],name+'_link')
        elf_check=check_elf(elf.read_bytes())
        attrs=execute([tool('readelf'),'-h','-A','-l','-S',elf],name+'_readelf').stdout
        attribute_check=check_attributes(attrs)
        symbols=execute([tool('nm'),'--defined-only','--numeric-sort',elf],name+'_symbols').stdout
        undefined=execute([tool('nm'),'-u',elf],name+'_undefined').stdout
        if undefined.strip():raise ValueError('Unresolved target symbols')
        if any(re.search(r'\b'+s+r'$',symbols,re.M) for s in ('malloc','calloc','realloc','free','_sbrk')):raise ValueError('Unexpected allocator in bare-metal image')
        object_sizes=execute([tool('nm'),'-S','--defined-only','--size-sort',elf],name+'_object_sizes').stdout
        execute([tool('objdump'),'-d',elf],name+'_disassembly')
        execute([tool('objcopy'),'-O','binary',elf,directory/'firmware.bin'],name+'_binary')
        raw=(directory/'firmware.bin').read_bytes()
        if len(raw)>0xe000:raise ValueError('Initialized image overlaps stack reservation')
        raw+=bytes((-len(raw))%4)
        (directory/'firmware.hex').write_text(''.join(f'{int.from_bytes(raw[i:i+4],"little"):08x}\n' for i in range(0,len(raw),4)),encoding='ascii')
        actual=execute([simulator_dir/'Vqinglong_soc','20000000'],name+'_simulation',cwd=directory,timeout=180,allow_fail=bool(bad))
        result=parse_output(actual)
        if bad:
            validation=check_wrong_expected(result)
        else:
            validation=check_simulation(result,expected['normal'])
            if result['zero_values']!=expected['zero'] or result['fields'].get('NEGATIVE_CHECKS')!=3 or result['fields'].get('SYNC_PUBLISH')!=2 or result['fields'].get('SYNC_ACQUIRE')!=2:
                raise ValueError('Zero input, fault rejection or synchronization evidence incomplete')
        frames={}
        for p in directory.glob('*.su'):
            frames[p.name]=p.read_text()
        addresses={line.split()[-1]:int(line.split()[0],16) for line in symbols.splitlines() if len(line.split())>=3}
        if addresses.get('__stack_top')!=65536 or addresses.get('__stack_bottom')!=57344 or addresses.get('__bss_end',65537)>57344:raise ValueError('Linker memory layout evidence failed')
        variants.append(dict(name=name,elf=elf_check,elf_sha256=sha(elf),result=result,validation=validation,compiler_frames=frames,
            layout={key:addresses[key] for key in ('_start','__bss_start','__bss_end','__stack_bottom','__stack_top')},attributes=attribute_check,
            object_sizes=object_sizes))
    timeout=execute([simulator_dir/'Vqinglong_soc','10'],'watchdog_simulation',cwd=output/'normal',allow_fail=True)
    watchdog_result=parse_output(timeout);watchdog=check_watchdog(watchdog_result,10)
    dual_dir=output/'verilator_dual';dual_dir.mkdir();dual_command=simulator_command(dual_dir,'dual_issue')
    execute(dual_command,'verilator_dual_build',timeout=300)
    dual=execute([dual_dir/'Vqinglong_soc','20000000'],'default_dual_simulation',cwd=output/'normal',timeout=180,allow_fail=True)
    dual_result=parse_output(dual)
    dual_validation=complete_dual_validation(dual_result,expected['normal'],expected['zero'])
    normal_variant=next(v for v in variants if v['name']=='normal');bad_variant=next(v for v in variants if v['name']=='bad_expected')
    profiles={
        'single_issue':profile_record('single_issue',simcmd,normal_variant['elf_sha256'],normal_variant['result'],normal_variant['validation'],
            bad_variant['result'],bad_variant['validation'],watchdog_result,watchdog,sha(rtl)),
        'dual_issue':profile_record('dual_issue',dual_command,normal_variant['elf_sha256'],dual_result,dual_validation,None,None,None,None,sha(rtl))}
    if rtl_mode=='portable-metadata':
        require_dual_pass(profiles)
        dual_bad=execute([dual_dir/'Vqinglong_soc','20000000'],'dual_bad_expected_simulation',cwd=output/'bad_expected',timeout=180,allow_fail=True)
        dual_bad_result=parse_output(dual_bad);dual_bad_validation=check_wrong_expected(dual_bad_result)
        dual_watch=execute([dual_dir/'Vqinglong_soc','10'],'dual_watchdog_simulation',cwd=output/'normal',allow_fail=True)
        dual_watch_result=parse_output(dual_watch);dual_watch_validation=check_watchdog(dual_watch_result,10)
    else:dual_bad_result=None;dual_bad_validation=None;dual_watch_result=None;dual_watch_validation=None
    profiles['dual_issue']=profile_record('dual_issue',dual_command,normal_variant['elf_sha256'],dual_result,dual_validation,
        dual_bad_result,dual_bad_validation,dual_watch_result,dual_watch_validation,sha(rtl))
    verification_target='single_and_dual_issue' if rtl_mode=='portable-metadata' else 'minimal_single_issue'
    report=dict(format='rv32-static-chain-report',version=2,passed=True,verification_target=verification_target,scope='QingLong selected RTL simulation, synthetic INT32 chain only',rtl_selection=rtl_identity,
        compiler_version=version,compiler_sha256=sha(cc),toolchain_lock=lock,toolchain_receipt_sha256=sha(receipt_path),toolchain_install_integrity=install_integrity,tool_binary_sha256=tool_hashes,selected_libraries=libs,macros=macro_check,commands=commands,
        rtl_sha256=sha(rtl),source_commit=lock['source_commit'],simulator=execute(['verilator','--version'],'simulator_version').stdout,
        expected=expected,variants=variants,watchdog_rejected=True,watchdog_validation=watchdog,board_verified=False,full_stack_worst_case=None,
        rtl_profiles_version=1,rtl_profiles=profiles,
        verified_rtl_parameters={k:v for k,v in rtl_parameters('single_issue').items() if k!='INIT_FILE'},
        verified_rtl_parameters_scope='deprecated legacy single_issue summary only; use rtl_profiles',
        default_dual_issue={'result':dual_result,'validation':dual_validation},default_configuration_verified=dual_validation['passed'],
        dual_negative_controls={'wrong_expected':dual_bad_result,'wrong_expected_validation':dual_bad_validation,'watchdog':dual_watch_validation},
        all_profiles_passed=dual_validation['passed'] is True,deployment_ready=False,
        floating_point_execution_verified=False,dma_cache_ddr_verified=False,model_binding=None,quantization_binding=None,
        source_sha256={p.relative_to(ROOT).as_posix():sha(p) for p in [*sources,ROOT/'c/rv32/link.ld',ROOT/'c/rv32/sim_main.cpp',ROOT/'c/include/ir_static.h',ROOT/'c/include/ir_core.h']})
    write_json(output/'report.json',report);print(json.dumps({'passed':True,'report':str(output/'report.json'),'results':[(x['name'],x['result']) for x in variants]}));return report


def main(argv=None):
    p=argparse.ArgumentParser();p.add_argument('--toolchain',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--rtl-mode',choices=MODES,default='portable-metadata');a=p.parse_args(argv)
    fresh=not a.output.exists()
    try:run(a.output,a.toolchain,a.rtl_mode);return 0
    except Exception as error:
        out=a.output.resolve()
        if fresh and out.is_relative_to(ROOT/'build') and out.is_dir() and not (out/'report.json').exists():
            failure={'passed':False,'target_result':None,'scope':'entrypoint failed; consult recorded stage logs','error':type(error).__name__,'message':str(error)}
            if isinstance(error,ProfileValidationError):failure.update(error.evidence)
            write_json(out/'failure.json',failure)
        print(str(error),file=sys.stderr);return 1


if __name__=='__main__':raise SystemExit(main())
