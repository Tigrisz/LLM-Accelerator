"""T8 worker, launched only inside an initially clean source workspace."""
import argparse,json,subprocess,sys
from pathlib import Path
from reproduce import ROOT,write_json,run_command,clean_environment,preflight
from total_acceptance import validate_pc,replay_target,combine_status,truth


def main():
    p=argparse.ArgumentParser();p.add_argument('--toolchain',type=Path,required=True);p.add_argument('--iterations',type=int,default=200);a=p.parse_args();out=ROOT/'build/total'
    if (ROOT/'build').exists() and any((ROOT/'build').iterdir()):raise ValueError('Total worker requires initially empty build')
    environment=preflight();commands=[];stages={}
    def run(name,args,timeout):
        command=[sys.executable,'-B',*map(str,args)];print('T8 stage: '+name,flush=True)
        r=run_command(command,cwd=ROOT,env=clean_environment(),stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=timeout)
        out.mkdir(parents=True,exist_ok=True);(out/(name+'.stdout')).write_text(r.stdout);(out/(name+'.stderr')).write_text(r.stderr)
        commands.append(dict(stage=name,command=command,exit_code=r.returncode));return r
    try:
        pc=run('pc',[ROOT/'tools/acceptance.py','--output',ROOT/'build/pc','--iterations',a.iterations],1800)
        pc_path=ROOT/'build/pc/report.json';pc_report=json.loads(pc_path.read_text()) if pc_path.is_file() else None
        if pc.returncode==0 and pc_report is not None:stages['pc']=validate_pc(pc_report,a.iterations)
        else:stages['pc']={'status':'failed' if pc_report is not None and pc_report.get('passed') is False else 'tool_error','passed':False if pc_report is not None and pc_report.get('passed') is False else None,'reason':'PC stage failed; target not executed'}
        if stages['pc']['passed'] is True:
            target=run('rv32',[ROOT/'tools/run_rv32_samples.py','--toolchain',a.toolchain.resolve(),'--workload','all','--output',ROOT/'build/rv32_total'],1800)
            target_path=ROOT/'build/rv32_total/report.json'
            if target_path.is_file():
                stages['simulation']=replay_target(json.loads(target_path.read_text()),target_path.parent)
                if target.returncode not in (0,1) or target.returncode==0 and stages['simulation']['passed'] is False:raise ValueError('Target exit/receipt mismatch')
            else:
                failure=ROOT/'build/rv32_total/failure.json'
                stages['simulation']={'status':'tool_error','passed':None,'validation_completed':False,'failure':json.loads(failure.read_text()) if failure.is_file() else None}
        else:stages['simulation']={'status':'unproven','passed':None,'validation_completed':False,'reason':'Not executed after PC failure'}
    except Exception as error:
        stages.setdefault('pc',{'status':'tool_error','passed':None})
        stages['simulation']={'status':'tool_error','passed':None,'validation_completed':False,'error':type(error).__name__,'message':str(error)}
    status=combine_status([r['status'] for r in stages.values()])
    controls=stages.get('simulation',{}).get('evidence_controls')
    if controls:status=combine_status([status,controls['status']])
    report=dict(format='inference-total-acceptance',version=1,status=status,passed=truth(status),validation_completed=bool(stages.get('simulation',{}).get('validation_completed')),
        environment=environment,stages=stages,commands=commands,initial_build_empty=True,runtime_version='0.6.0',native_runtime_abi=2,core_abi=1,wire_version=1,
        board={'status':'unproven','passed':None,'reason':'No board execution in this acceptance'},board_verified=False,deployment_ready=False,full_stack_worst_case=None,model_binding=None,quantization_binding=None)
    write_json(out/'report.json',report);print(json.dumps({'status':status,'passed':report['passed']}));return 0 if report['passed'] is True else 1


if __name__=='__main__':raise SystemExit(main())
