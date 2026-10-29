"""T1 reproducibility controller: fresh source snapshot, no historical build input."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import stat
import subprocess
import sys
import signal

ROOT=Path(__file__).resolve().parents[1]
SOURCE_DIRS=('inference_ref','c','tests','fixtures','docs','templates','tools')
SOURCE_FILES=('.gitignore','README.md','requirements.txt')
EXCLUDED={'__pycache__','.git','.venv','build'}
BINARY_SUFFIXES={'.so','.dll','.dylib','.exe','.o','.a','.pyc','.pyo'}
_ACTIVE=set()
_HANDLER=False


def _stop_group(process):
    try:os.killpg(process.pid,signal.SIGTERM)
    except ProcessLookupError:pass
    try:process.wait(timeout=2)
    except subprocess.TimeoutExpired:pass
    try:os.killpg(process.pid,signal.SIGKILL)
    except ProcessLookupError:pass
    process.wait()


def run_command(command,*,timeout,**kwargs):
    """Foreground command in its own group; recursively clean on timeout/signal."""
    global _HANDLER
    if not _HANDLER:
        def terminate(signum,frame):
            for process in tuple(_ACTIVE):_stop_group(process)
            raise SystemExit(128+signum)
        signal.signal(signal.SIGTERM,terminate);_HANDLER=True
    process=subprocess.Popen(command,start_new_session=True,**kwargs);_ACTIVE.add(process)
    try:
        out,err=process.communicate(timeout=timeout)
        return subprocess.CompletedProcess(command,process.returncode,out,err)
    except BaseException:
        _stop_group(process);raise
    finally:
        _ACTIVE.discard(process)
        # Foreground completion does not authorize a daemon to keep writing logs.
        try:os.killpg(process.pid,signal.SIGKILL)
        except ProcessLookupError:pass


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x',encoding='utf-8',newline='\n') as stream:json.dump(value,stream,ensure_ascii=False,indent=2,allow_nan=False);stream.write('\n')


def no_symlink_path(path):
    path=Path(os.path.abspath(path))
    if any(p.is_symlink() for p in (path,*path.parents)):raise ValueError('Symlink path is not an output/source location')
    return path


def validate_output(source,output):
    source=Path(source).resolve();output=no_symlink_path(output)
    if output==source or source.is_relative_to(output):raise ValueError('Output must not replace source or its ancestors')
    if any(output.is_relative_to(source/d) for d in SOURCE_DIRS):raise ValueError('Output must not be inside managed source/data directories')
    if output.exists():raise FileExistsError(f'Refuse to overwrite {output}')
    return output


def source_files(root):
    root=no_symlink_path(root)
    for name in SOURCE_FILES:
        p=root/name
        if p.is_symlink() or not p.is_file():raise ValueError(f'Missing/nonregular source entry {p}')
        yield p
    for name in SOURCE_DIRS:
        base=root/name
        if base.is_symlink():raise ValueError(f'Symlink source directory {base}')
        if not base.is_dir():raise ValueError(f'Missing source directory {base}')
        for directory,dirs,files in os.walk(base,followlinks=False):
            for item in list(dirs)+files:
                p=Path(directory)/item
                if p.is_symlink():raise ValueError(f'Symlink source entry {p}')
            dirs[:]=sorted(d for d in dirs if d not in EXCLUDED and not d.startswith('.venv'))
            for item in sorted(files):
                p=Path(directory)/item
                if not stat.S_ISREG(p.stat().st_mode):raise ValueError(f'Nonregular source entry {p}')
                if p.suffix.lower() in BINARY_SUFFIXES:continue
                yield p


def snapshot_source(source,target):
    source=Path(source).resolve();target=validate_output(source,target)
    files=list(source_files(source));before={p.relative_to(source).as_posix():sha(p) for p in files}
    target.mkdir(parents=True,exist_ok=False)
    for p in files:
        destination=target/p.relative_to(source);destination.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,destination)
    if not verify_manifest(target,before) or not verify_manifest(source,before):raise RuntimeError('Source changed while copying')
    return before


def verify_manifest(root,manifest):
    try:
        actual={p.relative_to(Path(root)).as_posix() for p in source_files(root)}
        return actual==set(manifest) and all((Path(root)/p).is_file() and not (Path(root)/p).is_symlink() and sha(Path(root)/p)==h for p,h in manifest.items())
    except (OSError,ValueError):return False


def clean_environment():
    env={key:os.environ[key] for key in ('PATH','HOME','USER','LOGNAME') if key in os.environ}
    env.update(PYTHONDONTWRITEBYTECODE='1',PYTHONHASHSEED='0',IR_REQUIRE_C='1',LANG='C.UTF-8',LC_ALL='C.UTF-8',TZ='UTC',
        ASAN_OPTIONS='detect_leaks=1:halt_on_error=1',UBSAN_OPTIONS='halt_on_error=1:print_stacktrace=1',
        OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1')
    return env


def preflight(*,which=shutil.which):
    if os.name!='posix' or platform.system()!='Linux':raise RuntimeError('Complete acceptance requires Linux/WSL; run this entry through WSL on Windows')
    if sys.version_info<(3,10):raise RuntimeError('Python >=3.10 required')
    tools={name:which(name) for name in ('gcc','cc')}
    if not tools['gcc'] or not tools['cc']:raise RuntimeError('gcc and cc are required for all 174 tests without skips')
    import numpy
    if tuple(int(v) for v in numpy.__version__.split('.')[:2])<(1,24):raise RuntimeError('NumPy >=1.24 required')
    versions={}
    for name,path in tools.items():
        run=subprocess.run([path,'--version'],capture_output=True,text=True,timeout=10,env=clean_environment())
        if run.returncode:raise RuntimeError(f'{name} --version failed')
        versions[name]={'path':str(Path(path).resolve()),'version':run.stdout.strip(),'driver_sha256':sha(Path(path).resolve())}
    return {'python':sys.version,'python_executable':sys.executable,'numpy':numpy.__version__,
        'numpy_origin':numpy.__file__,'os':platform.platform(),'machine':platform.machine(),'byteorder':sys.byteorder,
        'tools':versions,'effective_child_environment':clean_environment(),
        'environment_policy':'PATH/HOME/USER/LOGNAME allowlist + pinned locale/hashseed/sanitizer/thread policy; external build/library/Python overrides excluded'}


def main():
    parser=argparse.ArgumentParser(description='Snapshot sources and fully rebuild/accept in a clean copy')
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--iterations',type=int,default=200)
    args=parser.parse_args();output=None
    try:
        if not 1<=args.iterations<=10000:raise ValueError('Iterations must be 1..10000')
        environment=preflight();output=validate_output(ROOT,args.output);output.mkdir(parents=True,exist_ok=False)
        print('T1: copying sources/fixtures; historical build excluded',flush=True)
        manifest=snapshot_source(ROOT,output/'workspace');write_json(output/'source-manifest.json',{'format':'inference-source-snapshot','version':1,'files_sha256':manifest})
        workspace=output/'workspace'
        if (workspace/'build').exists() or (workspace/'.git').exists():raise RuntimeError('Clean snapshot contains build/git state')
        command=[sys.executable,'-B',str(workspace/'tools/acceptance.py'),'--output',str(workspace/'build/acceptance'),'--iterations',str(args.iterations)]
        print('T1: fresh workspace acceptance started',flush=True)
        with (output/'acceptance.log').open('x',encoding='utf-8') as log:
            run=run_command(command,cwd=workspace,env=clean_environment(),stdout=log,stderr=subprocess.STDOUT,timeout=1800)
        child=json.loads((workspace/'build/acceptance/report.json').read_text())
        intact=verify_manifest(ROOT,manifest) and verify_manifest(workspace,manifest)
        passed=run.returncode==0 and child.get('passed') is True and intact
        artifacts={p.relative_to(output).as_posix():sha(p) for p in sorted(output.rglob('*')) if p.is_file() and not p.is_symlink()}
        report={'format':'inference-reproduction-report','version':1,'passed':passed,'environment':environment,
            'command':command,'child_exit_code':run.returncode,'source_files':len(manifest),'source_and_copy_unchanged':intact,
            'history_copied':False,'initial_workspace_build_present':False,'acceptance':'workspace/build/acceptance/report.json',
            'results':child,'artifacts_sha256':artifacts,'reproducibility_scope':'source snapshot + rebuild + validation, not cross-environment byte-identical binaries'}
        write_json(output/'report.json',report)
        (output/'report.sha256').write_text(sha(output/'report.json')+'  report.json\n',encoding='utf-8')
        print(json.dumps({'passed':passed,'report':str(output/'report.json'),'framework_tests':child.get('framework_tests',{}).get('tests_run')}))
        return 0 if passed else 1
    except Exception as exc:
        if output is not None and output.is_dir() and not (output/'report.json').exists():
            write_json(output/'failure.json',{'passed':False,'error':type(exc).__name__,'message':str(exc)})
        print(json.dumps({'passed':False,'error':type(exc).__name__,'message':str(exc)}),file=sys.stderr);return 2


if __name__=='__main__':raise SystemExit(main())
