"""T5 offline preparation and actual PC-C/RV32 sample acceptance, no model binding."""
import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'tools'))
from reproduce import run_command,clean_environment,validate_output,write_json,sha
from rv32_samples import inventory,link_state,validate_sample_run,validate_exact_run,validate_recovery_run,NumericalMismatch,validate_overflow_run,parse_stream,verify_fixture_mapping,FROZEN_SUITE_SHA256
from rv32_profiles import parameters,verilator_arguments,check_build_parameters
from rv32_rtl import select_rtl
from rv32_evidence import check_elf,check_attributes,check_macros
from toolchain_integrity import verify_archive_install
from inference_ref import reference,oracle
from inference_ref.fixtures import read_fixture
from inference_ref.package_validation import package_fixture,_hash_tree
from inference_ref.model_package import read_package,write_package
from inference_ref.static_export import export_static
from inference_ref.static_backend import build_static
from inference_ref.static_validation import run_standalone
from inference_ref.c_backend import FLAGS,build_backend,CBackend
from inference_ref.contracts import ContractError
from inference_ref.compare import compare_arrays
from rv32_fp32 import compare_output,validate_float_run,validate_float_faults,check_softfloat_symbols,FP32Mismatch


def array(name,data,alignment=4):
    return f'_Alignas({alignment}) static const unsigned char {name}[{max(1,len(data))}]={{'+(','.join(map(str,data)) if data else '0')+'};\n'


def all_workload_result(results,extras_passed):
    states=[r['status'] for r in results]+(extras_passed if isinstance(extras_passed,list) else ['passed'] if extras_passed else ['unproven'])
    if not results:raise ValueError('Nonempty complete workload required')
    status=next((s for s in ('failed','tool_error','unproven','blocked_tcm') if s in states),'passed')
    return dict(status=status,passed=True if status=='passed' else False if status=='failed' else None,
        validation_completed=True,all_selected_rv32_validated=all(r['status']=='passed' for r in results))


def physical(value,spec):
    data=np.zeros(spec.storage_shape,dtype='<f4' if spec.dtype=='float32' else '<i4');data[tuple(slice(0,d) for d in spec.shape)]=value
    return data.tobytes()


def run(output,toolchain,fixtures,dtype='int32',workload='samples'):
    if workload not in ('samples','chains','all'):raise ValueError('Known static workload required')
    output=validate_output(ROOT,output);tc=Path(toolchain).resolve();fixtures=Path(fixtures).resolve()
    if not output.is_relative_to(ROOT/'build'):raise ValueError('Fresh output under workspace/build required')
    if output.is_relative_to(fixtures) or fixtures.is_relative_to(output):raise ValueError('Output and frozen fixture tree must be disjoint')
    before=_hash_tree(fixtures);rows=inventory(fixtures,dtype=dtype);frozen_rows=rows;selected=[r for r in rows if r['selected']] if workload=='samples' else []
    if workload=='all':
        rows=[{**row,'selected':True,'target_status':'pending'} for row in rows];frozen_rows=rows;selected=rows
    lock=json.loads((ROOT/'tools/target_toolchain.lock.json').read_text());receipt=json.loads((tc.parent/'receipt.json').read_text())
    if receipt.get('passed') is not True or receipt.get('lock')!=lock:raise ValueError('Prepared toolchain receipt mismatch')
    archive=Path(receipt.get('archive_path',str(tc.parent.parent/lock['archive_url'].rsplit('/',1)[1])))
    identity=verify_archive_install(archive,tc,lock)
    output.mkdir(parents=True,exist_ok=False);commands=[]
    def execute(name,args,cwd=None,timeout=120,required=True):
        command=list(map(str,args));result=run_command(command,cwd=cwd,env=clean_environment(),stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=timeout)
        (output/(name+'.stdout')).write_text(result.stdout,encoding='utf-8');(output/(name+'.stderr')).write_text(result.stderr,encoding='utf-8')
        row=dict(name=name,command=command,cwd=str(cwd) if cwd else None,exit_code=result.returncode);commands.append(row)
        with (output/'commands.jsonl').open('a',encoding='utf-8') as stream:stream.write(json.dumps(row,ensure_ascii=False)+'\n')
        if required and result.returncode:raise ValueError(name+' failed; consult stage logs')
        return result
    cc=tc/'bin/riscv-none-elf-gcc';prefix=tc/'bin/riscv-none-elf-'
    def tool(name):return Path(str(prefix)+name)
    flags=['-march='+lock['target_arch'],'-mabi=ilp32',*FLAGS,'-Os','-ffreestanding','-fno-builtin','-msmall-data-limit=0',
           '-ffunction-sections','-fdata-sections','-fno-asynchronous-unwind-tables','-fstack-usage','-fno-stack-protector']
    macros=execute('compiler_macros',[cc,*flags,'-dM','-E','-x','c','/dev/null']).stdout
    check_macros({line.split(None,2)[1]:line.split(None,2)[2] for line in macros.splitlines() if line.startswith('#define ') and len(line.split(None,2))==3})
    versions={name:execute(name+'_version',cmd).stdout for name,cmd in [('compiler',[cc,'--version']),('simulator',['verilator','--version'])]}
    selected_rtl,rtl_identity=select_rtl(ROOT,'portable-metadata');rtl=output/'selected_rtl.sv';rtl.write_bytes(selected_rtl)
    profiles={}
    for name in ('single_issue','dual_issue'):
        directory=output/name
        cmd=['verilator','--cc','--exe','--build','-j','4','-O2','-Wno-fatal','--top-module','qinglong_soc',
            *verilator_arguments(parameters(name)),'--Mdir',directory,rtl,ROOT/'c/rv32/sim_main.cpp']
        check_build_parameters(cmd,parameters(name));execute(name+'_build',cmd,timeout=300)
        profiles[name]={'parameters':parameters(name),'build_command':list(map(str,cmd)),'simulator':directory/'Vqinglong_soc'}
    pc_static=build_static(output/'pc_static');pc_core_artifact=build_backend(output/'pc_core');pc_core=CBackend(pc_core_artifact)
    pc_core_build={**pc_core.build,'library':str(pc_core_artifact)}
    common=output/'objects';common.mkdir();objects=[]
    for src in (ROOT/'c/rv32/start.S',ROOT/'c/src/ir_core.c',ROOT/'c/src/ir_static.c'):
        obj=common/(src.stem+'.o');execute('compile_'+src.stem,[cc,*flags,'-I',ROOT/'c/include','-c',src,'-o',obj]);objects.append(obj)
    def link(name,directory,extra):
        return execute(name+'_link',[cc,*flags,'-nostdlib','-nostartfiles','-Wl,--gc-sections','-Wl,-Map='+str(directory/'firmware.map'),
            '-T',ROOT/'c/rv32/link.ld',*extra,'-Wl,--start-group','-lc','-lm','-lgcc','-Wl,--end-group','-o',directory/'firmware.elf'],required=False)
    # A true over-capacity object proves the classifier without altering a fixture.
    capacity=output/'capacity_probe';capacity.mkdir();(capacity/'probe.c').write_text('static volatile unsigned char area[65536]; int main(void){return area[0]+area[65535];}\n')
    execute('capacity_compile',[cc,*flags,'-c',capacity/'probe.c','-o',capacity/'probe.o'])
    capacity_result=link('capacity',capacity,[objects[0],capacity/'probe.o'])
    if link_state(capacity_result.returncode,capacity_result.stderr)!='blocked_tcm':raise ValueError('Actual oversized static object was not rejected as TCM capacity')
    floating=prepare_float_probes(output,pc_static,pc_core,execute,link,cc,tool,flags,objects,profiles,strict=workload!='all') if dtype=='float32' or workload in ('chains','all') else None
    results=[]
    for record in selected:
        case_dtype=record['dtype']
        name=record['case_id'];directory=output/name;directory.mkdir();fixture=read_fixture(fixtures/name)
        feeds=package_fixture(directory/'package',fixture);package=read_package(directory/'package')
        verify_fixture_mapping(fixture,package,feeds)
        expected={};references={};float_refs={}
        output_tensor=next(t for t in package.tensors if t.role=='output')
        for label,data in [('normal',feeds),('zero',{k:np.zeros_like(v) for k,v in feeds.items()})]:
            inputs={k:v for k,v in fixture.inputs.items()};inputs.update(data)
            a=reference.execute(record['operation'],inputs);b=oracle.execute(record['operation'],inputs)
            direct=pc_core.execute(record['operation'],inputs)
            actual,execution=run_standalone(pc_static,directory/'package',data,directory/('pc_'+label))
            policy=fixture.metadata['comparison']
            checks={key:compare_arrays(a,value,policy['atol'],policy['rtol']) for key,value in [('numpy',b),('pc_core',direct),('pc_static',actual['y'])]}
            if label=='normal':checks['stored']=compare_arrays(fixture.expected,a,policy['atol'],policy['rtol'])
            if not all(c['passed'] for c in checks.values()):raise ValueError(name+' PC/Python reference disagreement')
            if case_dtype=='int32' and not a.tobytes()==b.tobytes()==direct.tobytes()==actual['y'].tobytes():raise ValueError(name+' exact INT32 mismatch')
            raw=physical(a,output_tensor.spec)
            pc_raw=(directory/('pc_'+label)/'outputs.bin').read_bytes()
            if case_dtype=='float32':
                if not compare_output(pc_raw.hex(),a,output_tensor.spec,policy)['passed']:raise ValueError(name+' PC physical padding/numeric mismatch')
                float_refs[label]={'scalar':a,'numpy':b,'pc_core':direct,'pc_static':actual['y']}
                if label=='normal':float_refs[label]['stored']=fixture.expected
            elif raw!=pc_raw:raise ValueError(name+' PC physical padding mismatch')
            expected[label]=raw.hex();references[label]={'scalar_sha256':__import__('hashlib').sha256(a.tobytes()).hexdigest(),
                'numpy_equal':True,'pc_core_equal':True,'pc_static_equal':True,'physical_output':pc_raw.hex(),'pc_execution':execution,
                'comparisons':checks,'bitwise_equal':{k:a.tobytes()==v.tobytes() for k,v in [('numpy',b),('pc_core',direct),('pc_static',actual['y'])]}}
        exported=export_static(directory/'package',directory/'export',address_bits=32)
        expected_runs={k:expected['zero'] if k=='RUN_1_OUTPUT' else expected['normal'] for k in ('RUN_0_OUTPUT','RUN_1_OUTPUT','RUN_2_OUTPUT','RECOVER_OUTPUT','REBIND_OUTPUT')}
        context=(float_refs,output_tensor.spec,policy) if case_dtype=='float32' else None
        result=build_case(name,directory,package,feeds,exported,False,expected_runs,execute,link,cc,tool,flags,objects,profiles,float_context=context)
        if context:result['float_references']={label:{key:value.tobytes().hex() for key,value in values.items()} for label,values in float_refs.items()};result['comparison_policy']=policy
        result.update(record=record,references=references);results.append(result)
        print(name,result['status'],flush=True)
    if workload in ('chains','all'):
        from rv32_chains import run_chains
        chain_results,chain_rows=run_chains(output,pc_static,pc_core,execute,link,cc,tool,flags,objects,profiles)
        if workload=='all':results=results+chain_results;rows=rows+chain_rows
        else:
            results,rows=chain_results,chain_rows
            frozen_rows=[{**row,'selected':False,'target_status':'not_in_scope'} for row in frozen_rows]
        selected=rows
    # Extra numeric overflow case is not one of the frozen samples.
    fault=output/'numeric_overflow';fault.mkdir()
    records=[{'id':n,'role':'output' if n=='y' else 'input','dtype':'int32','layout':'row_major','shape':[1],'storage_shape':[1]} for n in ('a','b','y')]
    write_package(fault/'package',model_id='t5_overflow_probe',tensors=records,nodes=[{'id':'add','op':'add','inputs':{'a':'a','b':'b'},'output':'y'}],inputs=['a','b'],outputs=['y'],constants={})
    feeds={'a':np.array([2147483647],np.int32),'b':np.array([1],np.int32)}
    for name,fn in [('scalar',reference.execute),('numpy',oracle.execute),('pc_core',pc_core.execute)]:
        try:fn('add',feeds)
        except ContractError as error:
            if error.code!='NUMERIC_OVERFLOW':raise
        else:raise ValueError(name+' did not reject overflowing addition')
    package=read_package(fault/'package');exported=export_static(fault/'package',fault/'export',address_bits=32)
    fault_result=build_case('numeric_overflow',fault,package,feeds,exported,True,{'RECOVER_OUTPUT':'00000000'},execute,link,cc,tool,flags,objects,profiles)
    unchanged=before==_hash_tree(fixtures)
    statuses={r['case_id']:r['status'] for r in results}
    for row in rows:
        if row['selected']:row['target_status']=statuses[row['case_id']]
    counts={state:sum(r['status']==state for r in results) for state in ('passed','blocked_tcm','failed','unproven','tool_error')}
    passed=unchanged and all(r['status'] in ('passed','blocked_tcm') for r in results) and fault_result['status']=='passed'
    if floating:passed=passed and floating['passed']
    report=dict(format='rv32-total-target-report' if workload=='all' else 'rv32-static-chains-report' if workload=='chains' else 'rv32-'+dtype+'-samples-report',version=4 if workload=='all' else 3,passed=passed,scope='54 frozen samples and two original four-node chains, selected CPU RTL simulation only' if workload=='all' else 'original FP32/INT32 four-node chains, selected CPU RTL simulation only' if workload=='chains' else 'frozen '+dtype+' fixture migration, selected CPU RTL simulation only',dtype='mixed' if workload in ('chains','all') else dtype,workload=workload,
        inventory=rows,inventory_complete=True,frozen_suite_sha256=FROZEN_SUITE_SHA256,selected_count=len(selected),counts=counts,all_selected_rv32_validated=counts['passed']==len(selected),cases=results,
        numeric_overflow=fault_result,capacity_probe={'passed':True,'status':'blocked_tcm','exit_code':capacity_result.returncode,'source_sha256':sha(capacity/'probe.c')},
        toolchain_integrity=identity,versions=versions,rtl_selection=rtl_identity,
        profiles={n:{k:str(v) if isinstance(v,Path) else v for k,v in p.items()} for n,p in profiles.items()},
        fixtures_unchanged=unchanged,fixture_files_sha256=before,pc_static_build=pc_static,pc_core_build=pc_core_build,commands=commands,
        frozen_fixture_inventory=frozen_rows,softfloat=floating,board_verified=False,floating_point_execution_verified=bool(floating and counts['passed']==len(selected)),full_stack_worst_case=None,model_binding=None,quantization_binding=None)
    if workload=='all':report.update(all_workload_result(results,[fault_result['status'],floating['faults']['status'],floating['boundary']['status'],'passed' if unchanged else 'failed']))
    write_json(output/'report.json',report);return report


def build_case(name,directory,package,feeds,exported,overflow,expected,execute,link,cc,tool,flags,objects,profiles,*,float_context=None,fault=False,harness=None,gate=None,header_defines=None):
    image=(directory/'export/execution.bin').read_bytes();weights=(directory/'export/weights.bin').read_bytes()
    tensors=package.tensors;out_index=next(i for i,t in enumerate(tensors) if t.role=='output')
    values={'T5_TENSORS':len(tensors),'T5_NODES':len(package.nodes),'T5_ALIGNMENT':exported['alignment'],
        'T5_ACT_BYTES':exported['arenas']['activations'],'T5_WORK_BYTES':exported['arenas']['workspace'],
        'T5_WEIGHT_BYTES':len(weights),'T5_INPUT_COUNT':len(feeds),'T5_OUTPUT_INDEX':out_index,
        'T5_OUTPUT_BYTES':tensors[out_index].spec.byte_length,'T5_OVERFLOW_PROBE':int(overflow)}
    if header_defines:
        if any(not k.startswith('T7_') or type(v) is not int for k,v in header_defines.items()):raise ValueError('Only explicit integer T7 harness parameters allowed')
        values.update(header_defines)
    header='\n'.join(f'#define {k} {v}' for k,v in values.items())+'\n'+array('t5_image',image,64)+array('t5_weights',weights,exported['alignment'])
    inputs=[]
    for i,t in enumerate(tensors):
        if t.role=='input':
            header+=array(f'input_{i}',physical(feeds[t.id],t.spec))+array(f'zero_{i}',physical(np.zeros_like(feeds[t.id]),t.spec))
            inputs.append(f'{{{i},{t.spec.byte_length},input_{i},zero_{i}}}')
    header+='typedef struct {uint32_t index,size;const unsigned char *normal,*zero;} t5_input;\nstatic const t5_input t5_inputs[T5_INPUT_COUNT]={'+','.join(inputs)+'};\n'
    (directory/'sample_blob.h').write_text(header,encoding='utf-8')
    source=harness or ROOT/'c/rv32'/('t6_float_faults.c' if fault else 't5_samples.c')
    obj=directory/'firmware.o';execute(name+'_compile',[cc,*flags,'-I',ROOT/'c/include','-I',directory,'-c',source,'-o',obj])
    linked=link(name,directory,[*objects,obj]);state=link_state(linked.returncode,linked.stderr)
    if state!='linked':return {'case_id':name,'status':state,'passed':None,'link_exit_code':linked.returncode,'shape_unchanged':True,'export':exported}
    elf=directory/'firmware.elf';elf_info=check_elf(elf.read_bytes())
    attrs=execute(name+'_readelf',[tool('readelf'),'-h','-A','-l','-S',elf]).stdout;check_attributes(attrs)
    symbols=execute(name+'_symbols',[tool('nm'),'--defined-only','--numeric-sort',elf]).stdout
    undefined=execute(name+'_undefined',[tool('nm'),'-u',elf]).stdout
    if undefined.strip() or any(re.search(r'\b'+s+r'$',symbols,re.M) for s in ('malloc','calloc','free','_sbrk','realloc')):raise ValueError('Unexpected unresolved/allocator target symbols')
    addresses={line.split()[-1]:int(line.split()[0],16) for line in symbols.splitlines() if len(line.split())>=3}
    if addresses['__bss_end']>57344 or addresses['__stack_bottom']!=57344 or addresses['__stack_top']!=65536:raise ValueError('Actual linker memory layout failed')
    disassembly=execute(name+'_objdump',[tool('objdump'),'-d',elf]).stdout
    fp_identity=check_softfloat_symbols(symbols,disassembly) if package.tensors[0].spec.dtype=='float32' else None
    execute(name+'_binary',[tool('objcopy'),'-O','binary',elf,directory/'firmware.bin'])
    data=(directory/'firmware.bin').read_bytes()
    if len(data)>57344:raise ValueError('Initialized image overlaps stack despite link success')
    data+=bytes((-len(data))%4);(directory/'firmware.hex').write_text(''.join(f'{int.from_bytes(data[i:i+4],"little"):08x}\n' for i in range(0,len(data),4)),encoding='ascii')
    observations={};statuses=[]
    for profile,p in profiles.items():
        actual=execute(name+'_'+profile,[p['simulator'],'20000000'],cwd=directory,timeout=180,required=False)
        try:
            if gate:validation=gate(actual.stdout,actual.returncode)
            elif fault:validation=validate_recovery_run(actual.stdout,actual.returncode,validate_float_faults,{'RECOVER_OUTPUT':'0000000000000000'})
            elif float_context:validation=validate_float_run(actual.stdout,actual.returncode,*float_context,len(package.nodes))
            else:validation=validate_overflow_run(actual.stdout,actual.returncode,expected['RECOVER_OUTPUT']) if overflow else validate_exact_run(actual.stdout,actual.returncode,expected,len(package.nodes))
            state='passed'
        except ValueError as error:
            try:fields,outputs=parse_stream(actual.stdout)
            except ValueError:fields,outputs={},{}
            confirmed=fields.get('RTL_TRAPS',0)>0 or fields.get('RTL_STACK_VIOLATIONS',0)>0 or fields.get('T5_STATUS',0)!=0
            from rv32_chains import ChainMismatch
            confirmed=confirmed or isinstance(error,(FP32Mismatch,NumericalMismatch,ChainMismatch))
            state='failed' if confirmed else 'unproven';validation={'passed':False if confirmed else None,'reason':str(error),'fields':fields,'outputs':outputs}
        observations[profile]={'status':state,'result':validation,'elf_sha256':sha(elf),'simulator_exit':actual.returncode};statuses.append(state)
    equality=None
    if statuses==['passed','passed']:
        equality=observations['single_issue']['result']['outputs']==observations['dual_issue']['result']['outputs']
    if float_context and equality is False:
        old=observations['dual_issue']['result']
        observations['dual_issue'].update(status='failed',result={**old,'passed':False,'reason':'Same ELF single/dual outputs differ bitwise'});statuses.append('failed')
    state='passed' if all(s=='passed' for s in statuses) else 'failed' if 'failed' in statuses else 'unproven'
    return {'case_id':name,'status':state,'passed':True if state=='passed' else False if state=='failed' else None,
        'shape_unchanged':True,'export':exported,'elf_sha256':sha(elf),'elf':elf_info,'layout':{k:addresses[k] for k in ('_start','__bss_start','__bss_end','__stack_bottom','__stack_top')},
        'initialized_bytes':len(data),'profiles':observations,'expected_outputs':expected,'softfloat_identity':fp_identity,
        'single_dual_bitwise_equal':equality,
        'compiler_frames':{p.name:p.read_text() for p in directory.glob('*.su')}}


def prepare_float_probes(output,pc_static,pc_core,execute,link,cc,tool,flags,objects,profiles,strict=True):
    """Measured library identity plus strict boundary and failure probes before fixtures."""
    multilib=execute('softfloat_multilib',[cc,*flags,'-print-multi-directory']).stdout.strip()
    library=Path(execute('softfloat_library',[cc,*flags,'-print-libgcc-file-name']).stdout.strip()).resolve()
    if not library.is_file():raise ValueError('Selected libgcc does not exist')
    execute('softfloat_library_symbols',[tool('nm'),'-g','--defined-only',library])
    boundary=output/'fp32_boundary';boundary.mkdir()
    records=[{'id':n,'role':'output' if n=='y' else 'input','dtype':'float32','layout':'row_major','shape':[6],'storage_shape':[6]} for n in ('a','b','y')]
    write_package(boundary/'package',model_id='t6_fp32_boundary',tensors=records,nodes=[{'id':'add','op':'add','inputs':{'a':'a','b':'b'},'output':'y'}],inputs=['a','b'],outputs=['y'],constants={})
    feeds={'a':np.array([0x3f800000,0x3f800001,1,0x80000001,0x7f7fffff,0x3f000000],dtype='<u4').view('<f4'),
           'b':np.array([0x33800000,0x33800000,1,1,0x71800000,0xbf000000],dtype='<u4').view('<f4')}
    expected=np.array([0x3f800000,0x3f800002,2,0,0x7f7fffff,0],dtype='<u4').view('<f4')
    package=read_package(boundary/'package');spec=package.tensors[-1].spec;refs={};pc_records={}
    for label,data in [('normal',feeds),('zero',{k:np.zeros_like(v) for k,v in feeds.items()})]:
        target=expected if label=='normal' else np.zeros(6,np.float32)
        static,execution=run_standalone(pc_static,boundary/'package',data,boundary/('pc_'+label))
        values={'scalar':reference.execute('add',data),'numpy':oracle.execute('add',data),'pc_core':pc_core.execute('add',data),'pc_static':static['y']}
        if any(value.tobytes()!=target.tobytes() for value in values.values()):raise ValueError('FP32 boundary PC reference disagreement')
        refs[label]=values;pc_records[label]={'expected_hex':target.tobytes().hex(),'all_bitwise_equal':True,'execution':execution}
    exported=export_static(boundary/'package',boundary/'export',address_bits=32)
    runs={k:(np.zeros(6,np.float32) if k=='RUN_1_OUTPUT' else expected).tobytes().hex() for k in ('RUN_0_OUTPUT','RUN_1_OUTPUT','RUN_2_OUTPUT','RECOVER_OUTPUT','REBIND_OUTPUT')}
    result=build_case('fp32_boundary',boundary,package,feeds,exported,False,runs,execute,link,cc,tool,flags,objects,profiles,float_context=(refs,spec,{'mode':'abs_plus_rel','atol':0,'rtol':0}))
    if strict and (result['status']!='passed' or any(row['result']['outputs']!=runs for row in result['profiles'].values())):raise ValueError('FP32 boundary target support not verified')
    fault=output/'fp32_faults';fault.mkdir()
    for tensor in records:tensor['shape']=[2];tensor['storage_shape']=[2]
    write_package(fault/'package',model_id='t6_fp32_faults',tensors=records,nodes=[{'id':'add','op':'add','inputs':{'a':'a','b':'b'},'output':'y'}],inputs=['a','b'],outputs=['y'],constants={})
    maximum=np.finfo(np.float32).max;feeds={'a':np.array([1,maximum],np.float32),'b':np.array([2,maximum],np.float32)}
    rejection={}
    for name,fn in [('scalar',reference.execute),('numpy',oracle.execute),('pc_core',pc_core.execute)]:
        rejection[name]={}
        for label,value,code in [('nan',np.nan,'NONFINITE'),('positive_infinity',np.inf,'NONFINITE'),('negative_infinity',-np.inf,'NONFINITE'),('overflow',None,'NUMERIC_OVERFLOW')]:
            data={k:v.copy() for k,v in feeds.items()}
            if value is not None:data['a'][0]=value
            try:fn('add',data)
            except ContractError as error:
                if error.code!=code:raise
                rejection[name][label]=error.code
            else:raise ValueError(name+' did not reject FP32 '+label)
    package=read_package(fault/'package');exported=export_static(fault/'package',fault/'export',address_bits=32)
    faults=build_case('fp32_faults',fault,package,feeds,exported,False,{'RECOVER_OUTPUT':'0000000000000000'},execute,link,cc,tool,flags,objects,profiles,fault=True)
    if strict and faults['status']!='passed':raise ValueError('FP32 failure/atomicity support not verified')
    return {'passed':result['status']==faults['status']=='passed','abi':'ilp32','isa':'rv32im_zicsr_zifencei','multilib':multilib,'libgcc':str(library),'libgcc_sha256':sha(library),
            'boundary':result,'boundary_pc':pc_records,'faults':faults,'pc_fault_rejections':rejection,'hardware_fp':False,
            'full_ieee754_conformance':None,'rounding_scope':'tested default nearest-even ties/subnormal/cancellation/near-overflow, no dynamic rounding mode claim'}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--toolchain',type=Path,required=True);p.add_argument('--fixtures',type=Path,default=ROOT/'fixtures/synthetic-v1');p.add_argument('--output',type=Path,required=True);p.add_argument('--dtype',choices=('int32','float32'),default='int32');p.add_argument('--workload',choices=('samples','chains','all'),default='samples');a=p.parse_args()
    fresh=not a.output.exists()
    try:
        report=run(a.output,a.toolchain,a.fixtures,a.dtype,a.workload);print(json.dumps({'passed':report['passed'],'counts':report['counts'],'report':str(a.output/'report.json')}));raise SystemExit(0 if report['passed'] else 1)
    except Exception as error:
        if fresh and a.output.is_dir() and not (a.output/'report.json').exists():write_json(a.output/'failure.json',{'passed':False,'target_result':None,'error':type(error).__name__,'message':str(error)})
        print(str(error),file=sys.stderr);raise SystemExit(1)
