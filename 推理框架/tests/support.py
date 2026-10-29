"""Temporary test files stay under this project's build directory."""

from pathlib import Path
import shutil
import uuid


class Workspace:
    def __init__(self):
        self.root = (Path(__file__).resolve().parents[1] / "build" / "test-temp").resolve()
        self.path = self.root / uuid.uuid4().hex
        self.path.mkdir(parents=True)
        self.name = str(self.path)

    def cleanup(self):
        resolved = self.path.resolve()
        if resolved.parent != self.root or not resolved.name.isalnum():
            raise RuntimeError("Test cleanup target escaped project test-temp")
        if resolved.exists():
            shutil.rmtree(resolved)
