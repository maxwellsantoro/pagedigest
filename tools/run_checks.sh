#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_CONSUMER_DIR="${ROOT_DIR}/implementations/python-consumer"

if ! command -v uv >/dev/null 2>&1; then
  echo "missing uv; install it from https://docs.astral.sh/uv/ and rerun." >&2
  exit 1
fi

echo "[1/4] validating test vectors"
uv run --project "${PYTHON_CONSUMER_DIR}" --extra dev --locked python "${ROOT_DIR}/tools/validate_vectors.py"

echo "[2/4] running python consumer tests"
cd "${PYTHON_CONSUMER_DIR}"
uv run --locked python -m unittest discover -s tests -v

echo "[3/4] running rust generator tests"
cd "${ROOT_DIR}/implementations/rust-generator"
cargo test --locked

echo "[4/4] running generator integration smoke test"
cd "${ROOT_DIR}"
uv run --project "${PYTHON_CONSUMER_DIR}" --locked python "${ROOT_DIR}/tools/smoke_generator_progression.py"

echo "all checks passed"
