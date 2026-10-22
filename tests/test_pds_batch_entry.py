"""Windows preflight must bind a concrete Task-A project, never the active GUI."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(os.name == "nt", "Windows PowerShell/PDS preflight")
class PdsBatchEntryTests(unittest.TestCase):
    def run_preflight(self, k, *extra):
        return subprocess.run(
            [shutil.which("pwsh") or "powershell.exe", "-NoProfile", "-File",
             str(ROOT / "scripts/build_a_multigroup_pds.ps1"), "-K", str(k), "-ValidateOnly", *extra],
            cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=30)

    def test_validate_only_does_not_require_installed_pds(self):
        result = self.run_preflight(256, "-PdsShellPath", str(ROOT / 'absent-pds.exe'))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['expected_records'], 6)

    def test_actual_build_rejects_missing_pds_before_launch(self):
        result = subprocess.run(
            [shutil.which('pwsh') or 'powershell.exe', '-NoProfile', '-File',
             str(ROOT / 'scripts/build_a_multigroup_pds.ps1'), '-K', '256',
             '-PdsShellPath', str(ROOT / 'absent-pds.exe')],
            cwd=ROOT, capture_output=True, text=True, encoding='utf-8', timeout=30)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('PDS shell executable not found', result.stderr)

    def test_k256_targets_explicit_project_independent_of_active_gui(self):
        result = self.run_preflight(256)
        self.assertEqual(result.returncode, 0, result.stderr)
        plan = json.loads(result.stdout)
        project = ROOT / "fpgatest/a_multigroup_k256/prj/a_multigroup_k256.pds"
        self.assertEqual(Path(plan["project"]), project)
        self.assertEqual(plan["arguments"], ["-project", str(project), "-run", "gen_bit_stream"])
        self.assertEqual(plan["top"], "a_multigroup_k256_uart_board_top")
        self.assertEqual(plan["expected_records"], 6)
        self.assertEqual(plan["rom_hash_checks"], 4)

    def test_k384_targets_separate_project(self):
        result = self.run_preflight(384)
        self.assertEqual(result.returncode, 0, result.stderr)
        plan = json.loads(result.stdout)
        self.assertEqual(plan["expected_records"], 9)
        self.assertEqual(Path(plan["project"]),
                         ROOT / "fpgatest/a_multigroup_k384/prj/a_multigroup_k384.pds")

    def test_rejects_case_outside_approved_two(self):
        result = self.run_preflight(2048)
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn('"project"', result.stdout)


if __name__ == "__main__":
    unittest.main()
