"""Package reproducible A/B sources and the reviewed B memory fixes."""
from pathlib import Path
import difflib
import zipfile

ROOT = Path(__file__).resolve().parents[1]
patch = []
for source in sorted((ROOT / "upstream-b/rtl/memory").glob("*.sv")):
    target = ROOT / "rtl/memory" / source.name
    patch.extend(difflib.unified_diff(source.read_text().splitlines(keepends=True),
                                     target.read_text().splitlines(keepends=True),
                                     fromfile=f"a/rtl/memory/{source.name}",
                                     tofile=f"b/rtl/memory/{source.name}"))
if patch:
    (ROOT / "docs/b_memory_fixes.patch").write_text("".join(patch), encoding="utf-8", newline="\n")
out = ROOT / "artifacts/A-B-integration-2026-10-17.zip"
out.parent.mkdir(exist_ok=True)
with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as archive:
    for folder in ("rtl", "model", "scripts", "tests", "docs"):
        for path in sorted((ROOT / folder).rglob("*")):
            if path.is_file() and "__pycache__" not in path.parts:
                archive.write(path, path.relative_to(ROOT))
    for name in ("README.md", "Makefile", ".gitignore"):
        archive.write(ROOT / name, name)
print(out)
