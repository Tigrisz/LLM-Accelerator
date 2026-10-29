"""T4 source-only copy + explicit pinned external toolchain + real RTL execution."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

from reproduce import (ROOT, snapshot_source, validate_output, verify_manifest,
                       clean_environment, run_command, write_json, sha)
from rv32_rtl import MODES


def main(argv=None):
    parser=argparse.ArgumentParser()
    parser.add_argument('--toolchain',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--rtl-mode',choices=MODES,default='portable-metadata')
    args=parser.parse_args(argv);output=None
    try:
        toolchain=args.toolchain.resolve()
        if not (toolchain.parent/'receipt.json').is_file():raise ValueError('Explicit prepared toolchain receipt required')
        output=validate_output(ROOT,args.output)
        if not output.is_relative_to(ROOT/'build'):raise ValueError('Output must be below workspace/build')
        output.mkdir(parents=True,exist_ok=False)
        workspace=output/'workspace';manifest=snapshot_source(ROOT,workspace)
        write_json(output/'source-manifest.json',{'format':'inference-source-snapshot','version':1,'files_sha256':manifest})
        if (workspace/'build').exists():raise ValueError('Snapshot contains historical build')
        command=[sys.executable,'-B',str(workspace/'tools/run_rv32.py'),'--toolchain',str(toolchain),'--output',str(workspace/'build/target'),'--rtl-mode',args.rtl_mode]
        with (output/'target.log').open('x',encoding='utf-8') as stream:
            result=run_command(command,cwd=workspace,env=clean_environment(),stdout=stream,stderr=subprocess.STDOUT,timeout=1200)
        if result.returncode:
            child_path=workspace/'build/target/failure.json'
            child=json.loads(child_path.read_text()) if child_path.is_file() else {'passed':False,'target_result':None,'scope':'child entrypoint failed without structured target evidence'}
            failure={'passed':False,'target_result':child.get('target_result'),'child_exit_code':result.returncode,'child_failure':child,
                'error':'ChildValidationFailure','message':'RV32 child validation failed; consult retained child classification',
                'rtl_profiles_version':child.get('rtl_profiles_version'),'rtl_profiles':child.get('rtl_profiles'),
                'classification':child.get('classification')}
            write_json(output/'failure.json',failure)
            print(json.dumps({'passed':False,'target_result':failure['target_result'],'error':failure['error'],'evidence':str(output/'failure.json')},ensure_ascii=False),file=sys.stderr);return 1
        child=json.loads((workspace/'build/target/report.json').read_text())
        intact=verify_manifest(ROOT,manifest) and verify_manifest(workspace,manifest)
        expected_target='single_and_dual_issue' if args.rtl_mode=='portable-metadata' else 'minimal_single_issue'
        passed=result.returncode==0 and child.get('passed') is True and child.get('verification_target')==expected_target and intact
        artifacts={p.relative_to(output).as_posix():sha(p) for p in sorted(output.rglob('*')) if p.is_file() and not p.is_symlink()}
        report={'format':'rv32-reproduction-report','version':2,'passed':passed,
            'verification_target':expected_target,'rtl_selection':child['rtl_selection'],'all_profiles_passed':child['all_profiles_passed'],
            'rtl_profiles_version':child['rtl_profiles_version'],'rtl_profiles':child['rtl_profiles'],
            'deployment_ready':False,'board_verified':False,'history_copied':False,
            'initial_workspace_build_present':False,'source_and_copy_unchanged':intact,'source_files':len(manifest),
            'command':command,'child_exit_code':result.returncode,'results':child,'artifacts_sha256':artifacts,
            'external_dependency':{'toolchain':str(toolchain),'preparation_receipt_sha256':sha(toolchain.parent/'receipt.json'),
                'scope':'explicit toolchain dependency; no reuse of historical runtime binaries or simulator builds'},
            'reproducibility_scope':'fresh source + rebuild + simulation; not cross-environment bit-identical binaries'}
        write_json(output/'report.json',report)
        (output/'report.sha256').write_text(sha(output/'report.json')+'  report.json\n',encoding='utf-8')
        print(json.dumps({'passed':passed,'verification_target':expected_target,'default_configuration_verified':child['default_configuration_verified'],'report':str(output/'report.json')}))
        return 0 if passed else 1
    except Exception as error:
        if output is not None and output.is_dir() and not (output/'report.json').exists() and not (output/'failure.json').exists():
            write_json(output/'failure.json',{'passed':False,'target_result':None,'error':type(error).__name__,'message':str(error)})
        print(str(error),file=sys.stderr);return 1


if __name__=='__main__':raise SystemExit(main())
