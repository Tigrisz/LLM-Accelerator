"""Extract a real Qwen2.5-1.5B-Instruct linear-layer W4A8 slice.

This script is an offline build-time tool. It loads the model on the
development machine, captures one activation vector, quantizes the selected
weight/activation slice, and emits a self-contained fixture. The FPGA runtime
uses only the generated files; it does not require this host script.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from model.model_slice import write_model_slice


def select_slice(
    weight: np.ndarray,
    activation: np.ndarray,
    *,
    rows_start: int,
    rows: int,
    cols_start: int,
    cols: int,
    allow_zero_pad_cols: bool = False,
) -> tuple[np.ndarray, np.ndarray, dict[str, int | list[int]]]:
    """Select a row/column tile and optionally zero-pad past model width."""
    if weight.ndim != 2 or activation.ndim != 1:
        raise ValueError("weight must be 2-D and activation must be 1-D")
    row_end = rows_start + rows
    col_end = cols_start + cols
    if rows <= 0 or cols <= 0 or rows_start < 0 or cols_start < 0:
        raise ValueError("rows, cols, rows_start, and cols_start must be valid")
    if row_end > weight.shape[0] or cols_start >= weight.shape[1]:
        raise ValueError(f"slice exceeds o_proj shape {tuple(weight.shape)}")
    if col_end > weight.shape[1] and not allow_zero_pad_cols:
        raise ValueError(f"slice exceeds o_proj shape {tuple(weight.shape)}")
    if col_end > activation.size and not allow_zero_pad_cols:
        raise ValueError(f"activation slice exceeds captured width {activation.size}")

    real_cols = min(cols, weight.shape[1] - cols_start, activation.size - cols_start)
    if real_cols < 0:
        real_cols = 0
    selected_weight = np.zeros((rows, cols), dtype=weight.dtype)
    selected_activation = np.zeros((cols,), dtype=activation.dtype)
    if real_cols:
        selected_weight[:, :real_cols] = weight[rows_start:row_end, cols_start:cols_start + real_cols]
        selected_activation[:real_cols] = activation[cols_start:cols_start + real_cols]
    metadata: dict[str, int | list[int]] = {
        "source_weight_shape": [int(weight.shape[0]), int(weight.shape[1])],
        "source_activation_width": int(activation.size),
        "source_cols": int(real_cols),
        "zero_padded_cols": int(cols - real_cols),
    }
    return selected_weight, selected_activation, metadata


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default="Qwen/Qwen2.5-1.5B-Instruct")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--layer", type=int, default=0)
    parser.add_argument("--rows-start", type=int, default=0)
    parser.add_argument("--rows", type=int, default=16)
    parser.add_argument("--cols-start", type=int, default=0)
    parser.add_argument("--cols", type=int, default=128)
    parser.add_argument(
        "--allow-zero-pad-cols",
        action="store_true",
        help="allow a requested tile to extend past the model width with zero columns",
    )
    parser.add_argument("--prompt", default="FPGA W4A8 slice validation.")
    parser.add_argument("--token-index", type=int, default=-1)
    args = parser.parse_args()
    try:
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer
    except ImportError as exc:
        raise SystemExit("install torch and transformers for offline Qwen extraction") from exc

    tokenizer = AutoTokenizer.from_pretrained(args.model)
    model = AutoModelForCausalLM.from_pretrained(args.model, torch_dtype="auto")
    model.eval()
    try:
        target = model.model.layers[args.layer].self_attn.o_proj
    except AttributeError as exc:
        raise SystemExit("the selected checkpoint does not expose model.layers[].self_attn.o_proj") from exc
    captured: dict[str, torch.Tensor] = {}

    def capture_input(module, inputs):
        captured["activation"] = inputs[0].detach().cpu()

    hook = target.register_forward_pre_hook(capture_input)
    inputs = tokenizer(args.prompt, return_tensors="pt")
    with torch.no_grad():
        model(**inputs, use_cache=False)
    hook.remove()
    # Qwen checkpoints are commonly loaded as BF16.  NumPy does not accept
    # torch.bfloat16 directly, so convert on the torch side before crossing
    # the PyTorch/NumPy boundary.
    activation = captured["activation"][0, args.token_index].float().numpy()
    weight = target.weight.detach().cpu().float().numpy()
    try:
        selected_weight, selected_activation, slice_metadata = select_slice(
            weight,
            activation,
            rows_start=args.rows_start,
            rows=args.rows,
            cols_start=args.cols_start,
            cols=args.cols,
            allow_zero_pad_cols=args.allow_zero_pad_cols,
        )
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    metadata = {
        "model": args.model,
        "layer": args.layer,
        "module": "model.layers[].self_attn.o_proj",
        "rows_start": args.rows_start,
        "cols_start": args.cols_start,
        "prompt": args.prompt,
        "token_index": args.token_index,
        **slice_metadata,
    }
    config = write_model_slice(
        args.output,
        selected_weight,
        selected_activation,
        metadata,
    )
    print(config)


if __name__ == "__main__":
    main()
