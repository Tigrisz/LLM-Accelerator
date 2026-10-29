"""Strict shape/dtype comparison with JSON-safe, zero-aware metrics."""

import numpy as np

from .contracts import DTYPES, require, valid_tolerance


def compare_arrays(expected: np.ndarray, actual: np.ndarray,
                   atol: float = 1e-6, rtol: float = 1e-5) -> dict:
    for tolerance in (atol, rtol):
        require(valid_tolerance(tolerance),
                "INVALID_ARGUMENT", "Tolerance must be finite and nonnegative")
    require(isinstance(expected, np.ndarray) and isinstance(actual, np.ndarray),
            "INVALID_ARGUMENT", "Expected two ndarrays")
    require(expected.shape == actual.shape and expected.size > 0,
            "INVALID_SHAPE", "Comparison does not broadcast or accept empty arrays")
    require(expected.dtype == actual.dtype, "INVALID_ARGUMENT", "Dtypes differ")
    require(expected.dtype.name in DTYPES, "UNSUPPORTED", "Unsupported comparison dtype")
    ref, got = expected.astype(np.float64), actual.astype(np.float64)
    finite = np.isfinite(ref) & np.isfinite(got)
    error = np.zeros(ref.shape, dtype=np.float64)
    error[finite] = np.abs(got[finite] - ref[finite])
    matched = np.zeros(ref.shape, dtype=bool)
    if expected.dtype.name == "int32":
        matched = expected == actual
    else:
        matched[finite] = error[finite] <= atol + rtol * np.abs(ref[finite])
    relative_mask = finite & (ref != 0)
    relative = error[relative_mask] / np.abs(ref[relative_mask])
    mismatch = np.argwhere(~matched)
    return {
        "passed": bool(matched.all()),
        "comparison": "exact" if expected.dtype.name == "int32" else "abs_plus_rel",
        "atol": float(atol), "rtol": float(rtol),
        "elements": int(expected.size),
        "mismatch_count": int((~matched).sum()),
        "nonfinite_count": int((~finite).sum()),
        "max_absolute_error": float(error[finite].max()) if finite.any() else None,
        "max_relative_error": float(relative.max()) if relative.size else None,
        "relative_error_excluded_count": int((~relative_mask).sum()),
        # A scalar mismatch has one coordinate row and zero columns: (1, 0).
        "first_mismatch": mismatch[0].tolist() if len(mismatch) else None,
    }
