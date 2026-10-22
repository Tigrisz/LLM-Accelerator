"""Export pre-W4A8 values without pretending BF16 checkpoint data is native FP32."""
import hashlib
import json
from pathlib import Path

import numpy as np


def write_float_reference(output: Path, weights, activation, metadata: dict) -> dict:
    output = Path(output)
    if output.exists():
        raise FileExistsError(output)
    w, x = np.asarray(weights, dtype=np.float32), np.asarray(activation, dtype=np.float32)
    if w.ndim != 2 or x.ndim != 1 or w.shape[1] != x.size or not w.size or x.size % 128:
        raise ValueError('reference must be nonempty [N,K], [K], K aligned to 128')
    if not np.isfinite(w).all() or not np.isfinite(x).all():
        raise ValueError('reference values must be finite')
    source_cols = metadata['source_cols']
    if not 0 < source_cols <= x.size or metadata['zero_padded_cols'] != x.size-source_cols:
        raise ValueError('invalid source/padding dimensions')
    if np.any(w[:, source_cols:]) or np.any(x[source_cols:]):
        raise ValueError('declared padding must be zero')
    groups = (w.astype(np.float64) * x.astype(np.float64)).reshape(w.shape[0], -1, 128).sum(axis=2)
    arrays = {'weights_fp32.npy': w, 'activation_fp32.npy': x,
              'reference_groups_fp64.npy': groups, 'reference_fp64.npy': groups.sum(axis=1),
              'reference_fp32.npy': w @ x}
    output.mkdir(parents=True)
    files = {}
    for name, array in arrays.items():
        np.save(output / name, array, allow_pickle=False)
        files[name] = dict(sha256=hashlib.sha256((output/name).read_bytes()).hexdigest(),
                           shape=list(array.shape), dtype=str(array.dtype))
    manifest = dict(format_version=1, source='checkpoint_replay_pre_w4a8',
                    N=w.shape[0], K=x.size, group_size=128, metadata=metadata,
                    reference_semantics='W @ x only; bias excluded to match integer GEMV',
                    storage_note='FP32 conversion of loaded checkpoint/captured activation; not native FP32 checkpoint inference',
                    reference_arithmetic='FP64 products, group reduction then row reduction', files=files)
    (output/'manifest.json').write_text(json.dumps(manifest, indent=2, allow_nan=False)+'\n', encoding='utf-8')
    return manifest
