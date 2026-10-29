"""Offline checked model -> pointer-free static execution image, version 1."""
import hashlib
import struct
import zlib
from pathlib import Path

from .c_backend import DTYPES,OPS,_new_directory
from .contracts import require
from .memory import plan_memory,validate_plan_addressing
from .model_package import read_package
from .reporting import write_json_exclusive

HEADER=struct.Struct('<8s6I3Q2I')
TENSOR=struct.Struct('<4I10Q')
NODE=struct.Struct('<6I')
ABSENT=0xffffffff
ROLES={'constant':0,'input':1,'intermediate':2,'output':3}


def encode_static(package,plan):
    validate_plan_addressing(plan,address_bits=64)
    indices={t.id:i for i,t in enumerate(package.tensors)}
    weights=bytearray(plan.weight_bytes)
    records=[]
    for t in package.tensors:
        p=plan.placement(t.id)
        if t.role=='constant': weights[p.offset:p.offset+p.byte_length]=package.weights[t.offset:t.offset+t.length]
        records.append(TENSOR.pack(DTYPES[t.spec.dtype],len(t.spec.shape),ROLES[t.role],0 if p.arena=='weights' else 1,
            p.offset,p.byte_length,*t.spec.shape,*([0]*(4-len(t.spec.shape))),
            *t.spec.storage_shape,*([0]*(4-len(t.spec.shape)))))
    for n in package.nodes:
        bound=dict(n.inputs)
        a=bound['weight'] if n.op=='linear' else bound['a'] if n.op=='add' else bound['input']
        b=bound['input'] if n.op=='linear' else bound.get('b')
        records.append(NODE.pack(OPS[n.op],indices[a],indices[b] if b else ABSENT,
            indices[bound['bias']] if 'bias' in bound else ABSENT,indices[n.output],0))
    header=HEADER.pack(b'IRS4BIN1',1,0x01020304,len(package.tensors),len(package.nodes),plan.alignment,0,
                       plan.weight_bytes,plan.activation_bytes,plan.workspace_bytes,0,zlib.crc32(weights))
    blob=bytearray(header+b''.join(records))
    struct.pack_into('<I',blob,56,zlib.crc32(blob[:56]+blob[64:]))
    return bytes(blob),bytes(weights)


def export_static(package_path,output,*,platform=None,memory_budget=64*1024*1024,address_bits=64):
    package=read_package(package_path,platform=platform)
    plan=plan_memory(package,memory_budget=memory_budget)
    validate_plan_addressing(plan,address_bits=address_bits)
    blob,weights=encode_static(package,plan)
    output=Path(output).resolve()
    require(not output.is_relative_to(Path(package_path).resolve()),'INVALID_ARGUMENT','Export must be outside source package')
    directory=_new_directory(output)
    (directory/'execution.bin').write_bytes(blob)
    (directory/'weights.bin').write_bytes(weights)
    report={'format':'inference-static-export','version':1,'runtime_api':1,'backend_api':1,'platform_api':1,
        'model_id':package.model_id,'node_count':len(package.nodes),'tensor_count':len(package.tensors),
        'arenas':{'weights':plan.weight_bytes,'activations':plan.activation_bytes,'workspace':plan.workspace_bytes},
        'alignment':plan.alignment,'address_bits':address_bits,'plan':plan.to_dict(),
        'tensor_ids':[t.id for t in package.tensors],'node_ids':[n.id for n in package.nodes],
        'inputs':list(package.inputs),'outputs':list(package.outputs),
        'source_manifest_sha256':package.manifest_sha256,'source_weights_sha256':package.weights_sha256,
        'execution_sha256':hashlib.sha256(blob).hexdigest(),'weights_sha256':hashlib.sha256(weights).hexdigest()}
    write_json_exclusive(directory/'export.json',report)
    return report
