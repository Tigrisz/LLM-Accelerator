"""Run the Day 1-6 Python smoke and contract tests."""

from __future__ import annotations

import sys
import os
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


if __name__ == "__main__":
    os.chdir(ROOT)
    (ROOT / "tmp").mkdir(exist_ok=True)
    suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"), pattern="test_b_model.py")
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(0 if result.wasSuccessful() else 1)

