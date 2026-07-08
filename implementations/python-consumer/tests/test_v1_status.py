"""Drive the shipped v1.0 status gate against the real repository tree."""

from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
CHECKER = ROOT / "tools" / "check_v1_status.py"


class V1StatusGateTests(unittest.TestCase):
    def test_checker_exists(self) -> None:
        self.assertTrue(CHECKER.is_file(), f"missing {CHECKER}")

    def test_check_v1_status_passes_on_repo(self) -> None:
        result = subprocess.run(
            [sys.executable, str(CHECKER)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(
            result.returncode,
            0,
            msg=f"stdout={result.stdout!r} stderr={result.stderr!r}",
        )
        self.assertIn("ok", result.stdout)


if __name__ == "__main__":
    unittest.main()
