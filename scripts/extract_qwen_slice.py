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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default="Qwen/Qwen2.5-1.5B-Instruct")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--layer", type=int, default=0)
    parser.add_argument("--rows-start", type=int, default=0)
    parser.add_argument("--rows", type=int, default=16)
    parser.add_argument("--cols-start", type=int, default=0)
    parser.add_argument("--cols", type=int, default=128)
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
    row_end = args.rows_start + args.rows
    col_end = args.cols_start + args.cols
    if args.rows <= 0 or args.cols <= 0 or col_end > weight.shape[1] or row_end > weight.shape[0]:
        raise SystemExit(f"slice exceeds o_proj shape {tuple(weight.shape)}")
    metadata = {
        "model": args.model,
        "layer": args.layer,
        "module": "model.layers[].self_attn.o_proj",
        "rows_start": args.rows_start,
        "cols_start": args.cols_start,
        "prompt": args.prompt,
        "token_index": args.token_index,
    }
    config = write_model_slice(
        args.output,
        weight[args.rows_start:row_end, args.cols_start:col_end],
        activation[args.cols_start:col_end],
        metadata,
    )
    print(config)


if __name__ == "__main__":
    main()
