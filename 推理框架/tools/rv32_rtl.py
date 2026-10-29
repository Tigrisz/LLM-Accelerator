"""Explicit local RTL compatibility overlay; never alter archived upstream bytes."""
import hashlib
import json
from pathlib import Path

MODES=('upstream','portable-metadata')
REPLACEMENTS=(
    ('    wire [6:0] first_meta = fetch_meta[0], second_meta = fetch_meta[1];',
     '    // Precompute FIFO payload metadata; preserve NBA append priority across simulators.\n'
     '    wire [6:0] response_meta = issue_metadata(response_dec);\n'
     '    wire [6:0] response_meta_second = issue_metadata(response_dec_second);\n'
     '    wire [6:0] first_meta = fetch_meta[0], second_meta = fetch_meta[1];'),
    ('fetch_meta[fi] <= issue_metadata(response_dec);','fetch_meta[fi] <= response_meta;'),
    ('fetch_meta[fi] <= issue_metadata(response_dec_second);','fetch_meta[fi] <= response_meta_second;'))


def sha_bytes(data):return hashlib.sha256(data).hexdigest()


def select_rtl(root,mode):
    root=Path(root)
    if mode not in MODES:raise ValueError('Unknown RTL mode')
    path=root/'docs/target_platform_sources/main/fpga/generated/qinglong_all.sv'
    data=path.read_bytes()
    manifest=json.loads((root/'docs/target_platform_sources/manifest.json').read_text())
    source=next(s for s in manifest['sources'] if s['id']=='main:fpga/generated/qinglong_all.sv')
    lock=json.loads((root/'tools/target_toolchain.lock.json').read_text())
    if sha_bytes(data)!=source['sha256'] or source['ref']!=lock['source_commit']:raise ValueError('Archived upstream RTL identity mismatch')
    text=data.decode('utf-8')
    if mode=='portable-metadata':
        for old,new in REPLACEMENTS:
            if text.count(old)!=1:raise ValueError('RTL overlay anchor is missing or ambiguous')
            text=text.replace(old,new)
    selected=text.encode('utf-8')
    return selected,{'mode':mode,'upstream_sha256':sha_bytes(data),'selected_sha256':sha_bytes(selected),
        'upstream_commit':source['ref'],'upstream_modified':False,'local_overlay':mode!='upstream',
        'purpose':'Verilator 5.032 FIFO NBA scheduling compatibility; same combinational metadata semantics',
        'hardware_verified':False,'formal_equivalence':None}
