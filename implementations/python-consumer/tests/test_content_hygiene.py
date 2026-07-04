from __future__ import annotations

import importlib.util
import io
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]


def load_tool(name: str) -> Any:
    path = ROOT / "tools" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class ContentHygieneTests(unittest.TestCase):
    def test_clean_tree_has_no_findings(self) -> None:
        checker = load_tool("check_content_hygiene")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "index.html").write_text("<h1>Hello</h1>\n", encoding="utf-8")

            findings = checker.check_tree(root)

        self.assertEqual(findings, [])

    def test_detects_common_hygiene_warnings(self) -> None:
        checker = load_tool("check_content_hygiene")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "index.html").write_text(
                '<a href="mailto:hi@example.com">hi</a>\n'
                '<script src="/app.js?ts=20260704123456"></script>\n'
                "<p>Generated at 2026-07-04T01:00:00Z</p>\n",
                encoding="utf-8",
            )
            (root / "app.js.map").write_text("{}", encoding="utf-8")

            findings = checker.check_tree(root)

        rules = {finding.rule for finding in findings}
        self.assertIn("edge-email-obfuscation-risk", rules)
        self.assertIn("volatile-cache-busting-query", rules)
        self.assertIn("volatile-build-timestamp", rules)
        self.assertIn("source-map-artifact", rules)

    def test_fail_on_warning_returns_nonzero(self) -> None:
        checker = load_tool("check_content_hygiene")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "index.html").write_text("<p>Generated at 2026-07-04T01:00:00Z</p>\n", encoding="utf-8")
            stdout = io.StringIO()

            with redirect_stdout(stdout):
                code = checker.main([str(root), "--fail-on", "warning"])

        self.assertEqual(code, 1)
        self.assertIn("volatile-build-timestamp", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
