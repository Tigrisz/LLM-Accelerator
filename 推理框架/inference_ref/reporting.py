"""Exclusive output writing; source fixtures are never overwritten."""

import json
from pathlib import Path

from .contracts import ContractError


def write_json_exclusive(path: Path, value: dict) -> None:
    path = Path(path)
    text = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
    except FileExistsError as exc:
        raise ContractError("ALREADY_EXISTS", f"Refuse to overwrite {path}") from exc
    except OSError as exc:
        raise ContractError("IO_ERROR", str(exc)) from exc
