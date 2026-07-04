#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_CONSUMER_DIR="${ROOT_DIR}/implementations/python-consumer"

if ! command -v uv >/dev/null 2>&1; then
  echo "missing uv; install it from https://docs.astral.sh/uv/ and rerun." >&2
  exit 1
fi

echo "[1/9] checking python formatting"
uv run --project "${PYTHON_CONSUMER_DIR}" --extra dev --locked ruff format --check \
  "${PYTHON_CONSUMER_DIR}/pagedigest" \
  "${PYTHON_CONSUMER_DIR}/tests" \
  "${PYTHON_CONSUMER_DIR}/examples" \
  "${ROOT_DIR}/tools"

echo "[2/9] linting python"
uv run --project "${PYTHON_CONSUMER_DIR}" --extra dev --locked ruff check \
  "${PYTHON_CONSUMER_DIR}/pagedigest" \
  "${PYTHON_CONSUMER_DIR}/tests" \
  "${PYTHON_CONSUMER_DIR}/examples" \
  "${ROOT_DIR}/tools"

echo "[3/9] validating test vectors"
uv run --project "${PYTHON_CONSUMER_DIR}" --extra dev --locked python "${ROOT_DIR}/tools/validate_vectors.py"

echo "[4/9] running python consumer tests"
cd "${PYTHON_CONSUMER_DIR}"
uv run --locked python -m unittest discover -s tests -v

echo "[5/9] checking python CLI"
uv run --locked pagedigest verify-live --help >/dev/null

echo "[6/9] checking rust formatting"
cd "${ROOT_DIR}/implementations/rust-generator"
cargo fmt --check

echo "[7/9] linting and testing rust generator"
cd "${ROOT_DIR}/implementations/rust-generator"
cargo clippy --locked --all-targets -- -D warnings
cargo test --locked

echo "[8/9] running generator integration smoke test"
cd "${ROOT_DIR}"
uv run --project "${PYTHON_CONSUMER_DIR}" --locked python "${ROOT_DIR}/tools/smoke_generator_progression.py"

echo "[9/9] checking dogfood manifest in sync with site/"
cd "${ROOT_DIR}"
uv run --project "${PYTHON_CONSUMER_DIR}" --locked python "${ROOT_DIR}/tools/check_dogfood_manifest.py"

echo "all checks passed"
