#!/usr/bin/env python3
"""Compatibility wrapper for ``pagedigest verify-live``."""

from __future__ import annotations

from pagedigest.cli import verify_live_main


def main() -> int:
    return verify_live_main()


if __name__ == "__main__":
    raise SystemExit(main())
