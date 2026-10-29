"""PC sizeof and compiler-frame comparison; never target layout/stack proof."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'tools'))
from inference_ref.c_backend import FLAGS
from reproduce import clean_environment,run_command,sha,write_json


def audit(output):
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=False)
    flags=[*FLAGS,'-O2','-fno-inline','-fno-omit-frame-pointer','-fstack-usage']
    results={}
    for label,base in [('t2',ROOT/'docs/target_platform_sources/framework_t2'),('t3',ROOT)]:
        directory=output/label;directory.mkdir();inc=base/'c/include';src=base/'c/src/ir_static.c'
        command=['gcc',*flags,'-I',str(inc),'-c',str(src),'-o',str(directory/'static.o')]
        run=run_command(command,env=clean_environment(),stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=120)
        (directory/'compile.log').write_text(run.stdout+run.stderr,encoding='utf-8')
        if run.returncode or run.stderr:raise ValueError('PC frame build failed: '+run.stderr)
        frames={}
        for line in (directory/'static.su').read_text().splitlines():
            location,size,kind=line.split('\t');frames[location.rsplit(':',1)[1]]={'bytes':int(size),'kind':kind}
        probe=directory/'sizes.c'
        probe.write_text('#include "ir_static.h"\n#include <stdio.h>\nint main(void){printf("{\\"context_bytes\\":%zu,\\"tensor_bytes\\":%zu,\\"call_bytes\\":%zu,\\"profile_bytes\\":%zu}\\n",sizeof(irs_context),sizeof(ir_tensor),sizeof(ir_call),sizeof(ir_node_profile));return 0;}\n',encoding='utf-8')
        cmd=['gcc',*FLAGS,'-O2','-I',str(inc),str(probe),'-o',str(directory/'sizes')]
        build=run_command(cmd,env=clean_environment(),stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=120)
        if build.returncode or build.stderr:raise ValueError(build.stderr)
        sizes_run=run_command([str(directory/'sizes')],env=clean_environment(),stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=30)
        if sizes_run.returncode or sizes_run.stderr:raise ValueError('PC sizeof probe failed')
        results[label]={'frames':frames,'sizes':json.loads(sizes_run.stdout),'compile_command':command,
            'sizeof_command':cmd,'source_sha256':{str(p.relative_to(base)):sha(p) for p in (src,inc/'ir_static.h',inc/'ir_core.h')}}
    before,after=results['t2'],results['t3']
    if before['frames']['irs_inspect']['bytes']<32768 or after['frames']['irs_inspect_v2']['bytes']>2048 or after['frames']['irs_bind_v2']['bytes']>2048:
        raise ValueError('Expected large-frame removal was not observed')
    if not after['sizes']['context_bytes']<1024<before['sizes']['context_bytes']:
        raise ValueError('Expected context reduction was not observed')
    report={'format':'pc-static-metadata-audit','version':1,'passed':True,'compiler':subprocess.check_output(['gcc','--version'],text=True).splitlines()[0],
        'flags':flags,'measurements':results,'workspace_per_tensor':4,'state_per_tensor':1,'max_tensors':4096,'max_nodes':1024,
        'target_toolchain':None,'target_layout':None,'target_stack_peak':None,'pc_runtime_stack_peak':None,
        'scope':'PC sizeof and compiler per-function frames, not call-chain/ISR runtime high-water measurement'}
    write_json(output/'report.json',report);return report


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    result=audit(args.output);print(json.dumps({'passed':result['passed'],'measurements':{k:v['sizes'] for k,v in result['measurements'].items()}}))
