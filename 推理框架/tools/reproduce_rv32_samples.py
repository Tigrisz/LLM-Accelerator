"""T5 source-only clean copy, explicit pinned compiler, freshly built simulators."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
from reproduce import ROOT,snapshot_source,validate_output,verify_manifest,clean_environment,run_command,write_json,sha


def main():
    p=argparse.ArgumentParser();p.add_argument('--toolchain',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--dtype',choices=('int32','float32'),default='int32');p.add_argument('--workload',choices=('samples','chains'),default='samples');a=p.parse_args();output=None
    try:
        tc=a.toolchain.resolve()
        if not (tc.parent/'receipt.json').is_file():raise ValueError('Explicit prepared toolchain receipt required')
        output=validate_output(ROOT,a.output)
        if not output.is_relative_to(ROOT/'build'):raise ValueError('Output below workspace/build required')
        output.mkdir(parents=True,exist_ok=False);workspace=output/'workspace';manifest=snapshot_source(ROOT,workspace)
        write_json(output/'source-manifest.json',{'format':'inference-source-snapshot','version':1,'files_sha256':manifest})
        if (workspace/'build').exists():raise ValueError('Source copy contains historical build')
        command=[sys.executable,'-B',str(workspace/'tools/run_rv32_samples.py'),'--toolchain',str(tc),'--output',str(workspace/'build/samples'),'--dtype',a.dtype,'--workload',a.workload]
        with (output/'samples.log').open('x',encoding='utf-8') as log:r=run_command(command,cwd=workspace,env=clean_environment(),stdout=log,stderr=subprocess.STDOUT,timeout=1800)
        child_path=workspace/'build/samples/report.json'
        if not child_path.is_file():
            failure=workspace/'build/samples/failure.json'
            write_json(output/'failure.json',{'passed':False,'child_exit_code':r.returncode,'target_result':None,
                'child_failure':json.loads(failure.read_text()) if failure.is_file() else None});return 1
        child=json.loads(child_path.read_text());intact=verify_manifest(ROOT,manifest) and verify_manifest(workspace,manifest)
        passed=r.returncode==0 and child['passed'] is True and intact
        artifacts={p.relative_to(output).as_posix():sha(p) for p in sorted(output.rglob('*')) if p.is_file() and not p.is_symlink()}
        report=dict(format='rv32-samples-reproduction',version=1,passed=passed,results=child,command=command,child_exit_code=r.returncode,
            source_files=len(manifest),source_and_copy_unchanged=intact,history_copied=False,initial_workspace_build_present=False,
            external_dependency={'toolchain':str(tc),'receipt_sha256':sha(tc.parent/'receipt.json')},artifacts_sha256=artifacts,
            board_verified=False,full_stack_worst_case=None,model_binding=None,quantization_binding=None)
        write_json(output/'report.json',report);(output/'report.sha256').write_text(sha(output/'report.json')+'  report.json\n')
        print(json.dumps({'passed':passed,'counts':child['counts'],'report':str(output/'report.json')}));return 0 if passed else 1
    except Exception as error:
        if output is not None and output.is_dir() and not (output/'failure.json').exists() and not (output/'report.json').exists():
            write_json(output/'failure.json',{'passed':False,'target_result':None,'error':type(error).__name__,'message':str(error)})
        print(str(error),file=sys.stderr);return 1


if __name__=='__main__':raise SystemExit(main())
