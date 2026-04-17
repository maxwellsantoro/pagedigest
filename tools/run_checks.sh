#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${ROOT_DIR}/.venv/bin/python"

if [[ ! -x "${PYTHON_BIN}" ]]; then
  echo "missing python environment at ${PYTHON_BIN}" >&2
  echo "create one and install requests, then rerun." >&2
  exit 1
fi

echo "[1/4] validating test vectors"
"${PYTHON_BIN}" "${ROOT_DIR}/tools/validate_vectors.py"

echo "[2/4] running python consumer tests"
cd "${ROOT_DIR}/implementations/python-consumer"
"${PYTHON_BIN}" -m unittest discover -s tests -v

echo "[3/4] running rust generator tests"
cd "${ROOT_DIR}/implementations/rust-generator"
cargo test

echo "[4/4] running generator integration smoke test"
cd "${ROOT_DIR}"
"${PYTHON_BIN}" "${ROOT_DIR}/tools/smoke_generator_progression.py"

echo "all checks passed"
