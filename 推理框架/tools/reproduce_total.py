"""T8 public entry: one source snapshot, PC then all56 current RV32 cases."""
import argparse,json,subprocess,sys
from pathlib import Path
from reproduce import ROOT,validate_output,snapshot_source,verify_manifest,write_json,sha,run_command,clean_environment


def main(argv=None):
    p=argparse.ArgumentParser();p.add_argument('--toolchain',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--iterations',type=int,default=200);a=p.parse_args(argv);output=None
    try:
        requested=validate_output(ROOT,a.output)
        if not requested.is_relative_to(ROOT/'build') or not 1<=a.iterations<=10000:raise ValueError('Fresh workspace/build output and iterations1..10000 required')
        tc=a.toolchain.resolve()
        if not (tc.parent/'receipt.json').is_file():raise ValueError('Explicit prepared toolchain receipt required')
        output=requested;output.mkdir(parents=True,exist_ok=False);workspace=output/'workspace';manifest=snapshot_source(ROOT,workspace)
        write_json(output/'source-manifest.json',{'format':'inference-source-snapshot','version':1,'files_sha256':manifest})
        if (workspace/'build').exists():raise ValueError('Historical build copied')
        command=[sys.executable,'-B',str(workspace/'tools/run_total.py'),'--toolchain',str(tc),'--iterations',str(a.iterations)]
        print('T8: one clean source copy; PC then current all56 RV32 acceptance',flush=True)
        with (output/'total.log').open('x',encoding='utf-8') as log:r=run_command(command,cwd=workspace,env=clean_environment(),stdout=log,stderr=subprocess.STDOUT,timeout=3600)
        path=workspace/'build/total/report.json'
        child=json.loads(path.read_text()) if path.is_file() else {'status':'tool_error','passed':None,'validation_completed':False,'reason':'Worker receipt missing; see total.log'}
        intact=verify_manifest(ROOT,manifest) and verify_manifest(workspace,manifest)
        status=child['status'] if intact else 'failed';passed=child['passed'] if intact else False
        if r.returncode!=0 and passed is True:status='tool_error';passed=None
        artifacts={p.relative_to(output).as_posix():sha(p) for p in sorted(output.rglob('*')) if p.is_file() and not p.is_symlink()}
        report=dict(format='inference-total-reproduction',version=1,status=status,passed=passed,results=child,child_exit_code=r.returncode,command=command,
            source_files=len(manifest),source_and_copy_unchanged=intact,history_copied=False,initial_workspace_build_present=False,
            external_dependency={'toolchain':str(tc),'receipt_sha256':sha(tc.parent/'receipt.json')},artifacts_sha256=artifacts,board_verified=False,model_binding=None,quantization_binding=None)
        write_json(output/'report.json',report);(output/'report.sha256').write_text(sha(output/'report.json')+'  report.json\n')
        print(json.dumps({'status':status,'passed':passed,'report':str(output/'report.json')}));return 0 if passed is True and r.returncode==0 else 1
    except Exception as error:
        if output is not None and output.is_dir() and not (output/'report.json').exists():write_json(output/'failure.json',{'status':'tool_error','passed':None,'error':type(error).__name__,'message':str(error)})
        print(str(error),file=sys.stderr);return 1


if __name__=='__main__':raise SystemExit(main())
