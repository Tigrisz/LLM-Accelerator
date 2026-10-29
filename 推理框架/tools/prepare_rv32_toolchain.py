"""Verify and locally unpack the pinned toolchain. No global install or PATH edit."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tarfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from reproduce import write_json
from rv32_evidence import check_macros
from toolchain_integrity import verify_archive_install


def digest(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda:f.read(1<<20),b''):h.update(b)
    return h.hexdigest()


def prepare(archive,output):
    archive=Path(archive).resolve();output=Path(output).resolve()
    lock_path=ROOT/'tools/target_toolchain.lock.json';lock=json.loads(lock_path.read_text())
    if output.exists() or not output.is_relative_to(ROOT/'build'):raise ValueError('Fresh install directory under workspace/build required')
    if archive.stat().st_size!=lock['archive_bytes'] or digest(archive)!=lock['archive_sha256']:raise ValueError('Pinned archive SHA256/length mismatch')
    with tarfile.open(archive,'r:gz') as tar:
        for member in tar.getmembers():
            p=Path(member.name)
            if p.is_absolute() or '..' in p.parts or not p.parts or p.parts[0]!=lock['directory'] or member.isdev() or member.isfifo():
                raise ValueError('Archive entry outside pinned root or unsafe type')
        output.mkdir(parents=True,exist_ok=False)
        tar.extractall(output,filter='data')
    root=output/lock['directory'];identity=verify_archive_install(archive,root,lock)
    cc=root/lock['compiler'];flags=['-march='+lock['target_arch'],'-mabi='+lock['target_abi']]
    commands=[]
    def run(args,stdin=None):
        p=subprocess.run([str(cc),*args],input=stdin,capture_output=True,text=True,timeout=30)
        commands.append(dict(command=[str(cc),*args],exit_code=p.returncode,stdout=p.stdout,stderr=p.stderr))
        if p.returncode:raise ValueError(p.stderr)
        return p.stdout.strip()
    version=run(['--version']);machine=run(['-dumpmachine']);multi=run(['-print-multi-lib'])
    text=run([*flags,'-dM','-E','-x','c','-'],'')
    macros={line.split(None,2)[1]:line.split(None,2)[2] for line in text.splitlines() if line.startswith('#define ') and len(line.split(None,2))==3}
    check_macros(macros)
    selected={}
    for name in ('libgcc.a','libc.a','libm.a'):
        path=Path(run([*flags,'-print-file-name='+name]))
        selected[name]={'path':str(path),'exists':path.is_file(),'sha256':digest(path) if path.is_file() else None}
    if not all(v['exists'] for v in selected.values()):raise ValueError('RV32 runtime libraries are missing; preparation is incomplete')
    receipt=dict(format='rv32-toolchain-preparation',version=1,passed=True,lock=lock,lock_sha256=digest(lock_path),
        archive_sha256=digest(archive),archive_path=str(archive),install_integrity=identity,root=str(root),compiler_version=version,dumpmachine=machine,multilib=multi,
        selected_libraries=selected,macros=macros,commands=commands,
        compiler_sha256=digest(cc),global_install=False,path_modified=False,target_execution_verified=False)
    write_json(output/'receipt.json',receipt);print(json.dumps({'passed':True,'root':str(root),'version':version.splitlines()[0],'libraries':selected}))
    return receipt


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--archive',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();prepare(a.archive,a.output)
