"""Bind a reused installation to the contents of the SHA-pinned official archive."""
import hashlib
import json
import os
from pathlib import Path
import tarfile


def stream_hash(stream):
    result=hashlib.sha256()
    for block in iter(lambda:stream.read(1<<20),b''):result.update(block)
    return result.hexdigest()


def file_hash(path):
    with Path(path).open('rb') as stream:return stream_hash(stream)


def verify_archive_install(archive,root,lock):
    """Check every archived file/link, including cc1, binutils, headers/specs.

    The manifest is derived afresh from authenticated archive bytes, never from
    a mutable installation or a self-asserted preparation receipt. No extraction.
    """
    archive=Path(archive);root=Path(root).resolve()
    if archive.stat().st_size!=lock['archive_bytes'] or file_hash(archive)!=lock['archive_sha256']:
        raise ValueError('Pinned toolchain archive changed or is missing')
    if not root.is_dir() or root.name!=lock['directory']:raise ValueError('Unexpected toolchain root')
    expected={}
    with tarfile.open(archive,'r|gz') as tar:
        for member in tar:
            path=Path(member.name)
            if path.is_absolute() or '..' in path.parts or not path.parts or path.parts[0]!=lock['directory']:
                raise ValueError('Unsafe archive identity entry')
            if member.isdir():continue
            rel=Path(*path.parts[1:]);name=rel.as_posix();actual=root/rel
            if not name or name in expected:raise ValueError('Duplicate archive identity entry')
            if any(p.is_symlink() for p in actual.parents if p!=root and p.is_relative_to(root)):
                raise ValueError('Installed parent is a symlink')
            if member.issym():
                if not actual.is_symlink() or os.readlink(actual)!=member.linkname or not actual.resolve().is_relative_to(root):
                    raise ValueError('Installed toolchain symlink differs: '+name)
                expected[name]={'kind':'symlink','target':member.linkname}
            elif member.isfile() or member.islnk():
                if actual.is_symlink() or not actual.is_file():raise ValueError('Installed toolchain file missing/nonregular: '+name)
                if member.islnk():
                    target=Path(member.linkname)
                    if target.is_absolute() or '..' in target.parts or target.parts[0]!=lock['directory']:raise ValueError('Unsafe hardlink identity')
                    previous=expected.get(Path(*target.parts[1:]).as_posix(),{})
                    if 'sha256' not in previous:raise ValueError('Hardlink target identity unavailable')
                    digest=previous['sha256']
                else:
                    stream=tar.extractfile(member)
                    if stream is None:raise ValueError('Archive file has no content')
                    with stream:digest=stream_hash(stream)
                if file_hash(actual)!=digest:raise ValueError('Installed toolchain content differs: '+name)
                expected[name]={'kind':'file','sha256':digest}
            else:raise ValueError('Unsupported toolchain archive entry')
    found=set()
    for directory,dirs,files in os.walk(root,followlinks=False):
        for name in files+list(dirs):
            path=Path(directory)/name
            if path.is_symlink() or not path.is_dir():found.add(path.relative_to(root).as_posix())
        dirs[:]=[name for name in dirs if not (Path(directory)/name).is_symlink()]
    if found!=set(expected):raise ValueError('Installed toolchain contains unexpected/missing files')
    identity=hashlib.sha256(json.dumps(expected,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    return {'passed':True,'archive_sha256':lock['archive_sha256'],'files_and_links':len(expected),
            'content_manifest_sha256':identity,'scope':'all archive files/links; unexpected installed files rejected',
            'archive':str(archive.resolve()),'root':str(root)}
