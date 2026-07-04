from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from typing import TextIO

from .core import DEFAULT_MAX_AUDIT_BYTES, DEFAULT_MAX_MANIFEST_BYTES, verify_live


def _add_verify_live_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("base_url", help="Site base URL, e.g. https://example.com")
    parser.add_argument(
        "--manifest-url",
        help="Override manifest URL (defaults to /.well-known/pagedigest.json)",
    )
    parser.add_argument(
        "--sample-size",
        type=int,
        default=25,
        help="Number of digest entries to sample",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for deterministic sampling",
    )
    parser.add_argument("--timeout", type=int, default=15, help="HTTP timeout seconds")
    parser.add_argument(
        "--max-bytes",
        type=int,
        default=DEFAULT_MAX_AUDIT_BYTES,
        help="Abort identity fetches larger than this many bytes",
    )
    parser.add_argument(
        "--manifest-max-bytes",
        type=int,
        default=DEFAULT_MAX_MANIFEST_BYTES,
        help="Abort manifest fetches larger than this many bytes",
    )


def _run_verify_live(args: argparse.Namespace, stdout: TextIO, stderr: TextIO) -> int:
    if args.sample_size < 0:
        print("sample-size must be non-negative", file=stderr)
        return 1
    if args.timeout <= 0:
        print("timeout must be positive", file=stderr)
        return 1
    if args.max_bytes <= 0:
        print("max-bytes must be positive", file=stderr)
        return 1
    if args.manifest_max_bytes <= 0:
        print("manifest-max-bytes must be positive", file=stderr)
        return 1

    result = verify_live(
        args.base_url,
        manifest_url_override=args.manifest_url,
        sample_size=args.sample_size,
        seed=args.seed,
        timeout=args.timeout,
        max_bytes=args.max_bytes,
        manifest_max_bytes=args.manifest_max_bytes,
    )

    print(f"manifest: {result.get('manifest_url')}", file=stdout)
    if not result.get("ok"):
        error = result.get("error") or "unknown-error"
        status_code = result.get("status_code")
        suffix = f":{status_code}" if status_code is not None else ""
        print(f"error: {error}{suffix}", file=stderr)
        return 1

    print(f"sampled: {result['sampled']}", file=stdout)
    print(f"match: {result['match_count']}", file=stdout)
    print(f"mismatch: {result['mismatch_count']}", file=stdout)
    print(f"inconclusive: {result['inconclusive_count']}", file=stdout)

    for item in result["results"]:
        if item["status"] != "match":
            print(f"- {item['status']}: {item['url']} ({item['detail']})", file=stdout)

    if result["mismatch_count"] > 0:
        return 2
    return 0


def verify_live_main(
    argv: Sequence[str] | None = None, stdout: TextIO | None = None, stderr: TextIO | None = None
) -> int:
    parser = argparse.ArgumentParser(description="Verify pagedigest digest values over the wire")
    _add_verify_live_args(parser)
    return _run_verify_live(parser.parse_args(argv), stdout or sys.stdout, stderr or sys.stderr)


def main(argv: Sequence[str] | None = None, stdout: TextIO | None = None, stderr: TextIO | None = None) -> int:
    parser = argparse.ArgumentParser(prog="pagedigest")
    subcommands = parser.add_subparsers(dest="command")
    verify_parser = subcommands.add_parser("verify-live", help="Verify manifest digests against live responses")
    _add_verify_live_args(verify_parser)

    args = parser.parse_args(argv)
    if args.command == "verify-live":
        return _run_verify_live(args, stdout or sys.stdout, stderr or sys.stderr)

    parser.print_help(stderr or sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
