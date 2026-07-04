from __future__ import annotations

import io
import unittest
from unittest.mock import patch

from pagedigest import cli


class CliTests(unittest.TestCase):
    def test_verify_live_subcommand_returns_two_on_mismatch(self) -> None:
        result = {
            "ok": True,
            "manifest_url": "https://example.com/.well-known/pagedigest.json",
            "sampled": 1,
            "match_count": 0,
            "mismatch_count": 1,
            "inconclusive_count": 0,
            "results": [
                {
                    "url_key": "/",
                    "url": "https://example.com/",
                    "status": "mismatch",
                    "detail": "expected=sha256:0 computed=sha256:1",
                }
            ],
        }
        stdout = io.StringIO()
        stderr = io.StringIO()

        with patch.object(cli, "verify_live", return_value=result):
            code = cli.main(["verify-live", "https://example.com"], stdout=stdout, stderr=stderr)

        self.assertEqual(code, 2)
        self.assertIn("mismatch: 1", stdout.getvalue())
        self.assertIn("- mismatch: https://example.com/", stdout.getvalue())
        self.assertEqual(stderr.getvalue(), "")

    def test_verify_live_subcommand_rejects_negative_sample_size(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()

        code = cli.main(
            ["verify-live", "https://example.com", "--sample-size", "-1"],
            stdout=stdout,
            stderr=stderr,
        )

        self.assertEqual(code, 1)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("sample-size must be non-negative", stderr.getvalue())

    def test_legacy_verify_live_main_accepts_old_script_argument_shape(self) -> None:
        result = {
            "ok": True,
            "manifest_url": "https://example.com/.well-known/pagedigest.json",
            "sampled": 0,
            "match_count": 0,
            "mismatch_count": 0,
            "inconclusive_count": 0,
            "results": [],
        }
        stdout = io.StringIO()
        stderr = io.StringIO()

        with patch.object(cli, "verify_live", return_value=result):
            code = cli.verify_live_main(["https://example.com"], stdout=stdout, stderr=stderr)

        self.assertEqual(code, 0)
        self.assertIn("sampled: 0", stdout.getvalue())
        self.assertEqual(stderr.getvalue(), "")


if __name__ == "__main__":
    unittest.main()
