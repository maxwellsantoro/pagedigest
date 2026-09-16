#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_CONSUMER_DIR="${ROOT_DIR}/implementations/python-consumer"

if ! command -v uv >/dev/null 2>&1; then
  echo "missing uv; install it from https://docs.astral.sh/uv/ and rerun." >&2
  exit 1
fi

echo "[1/18] checking python formatting"
uv run --project "${PYTHON_CONSUMER_DIR}" --extra dev --locked ruff format --check \
  "${PYTHON_CONSUMER_DIR}/pagedigest" \
  "${PYTHON_CONSUMER_DIR}/tests" \
  "${PYTHON_CONSUMER_DIR}/examples" \
  "${ROOT_DIR}/tools"

echo "[2/18] linting python"
uv run --project "${PYTHON_CONSUMER_DIR}" --extra dev --locked ruff check \
  "${PYTHON_CONSUMER_DIR}/pagedigest" \
  "${PYTHON_CONSUMER_DIR}/tests" \
  "${PYTHON_CONSUMER_DIR}/examples" \
  "${ROOT_DIR}/tools"

echo "[3/18] validating test vectors"
uv run --project "${PYTHON_CONSUMER_DIR}" --extra dev --locked python "${ROOT_DIR}/tools/validate_vectors.py"

echo "[4/18] running python consumer tests"
cd "${PYTHON_CONSUMER_DIR}"
uv run --locked python -m unittest discover -s tests -v

echo "[5/18] checking python CLI"
uv run --locked pagedigest verify-live --help >/dev/null

echo "[6/18] checking content hygiene utility"
cd "${ROOT_DIR}"
uv run --project "${PYTHON_CONSUMER_DIR}" --locked python "${ROOT_DIR}/tools/check_content_hygiene.py" "${ROOT_DIR}/site" --fail-on warning

echo "[7/18] testing Astro integration"
cd "${ROOT_DIR}/packages/astro"
npm ci
npm test

echo "[8/18] testing npm launcher"
cd "${ROOT_DIR}/packages/cli"
npm ci
npm test

echo "[9/18] checking rust formatting"
cd "${ROOT_DIR}/implementations/rust-generator"
cargo fmt --check

echo "[10/18] linting and testing rust generator"
cd "${ROOT_DIR}/implementations/rust-generator"
cargo clippy --locked --all-targets -- -D warnings
cargo test --locked

echo "[11/18] running generator integration smoke test"
cd "${ROOT_DIR}"
uv run --project "${PYTHON_CONSUMER_DIR}" --locked python "${ROOT_DIR}/tools/smoke_generator_progression.py"

echo "[12/18] running generator↔Astro conformance smoke"
cd "${ROOT_DIR}"
uv run --project "${PYTHON_CONSUMER_DIR}" --locked python "${ROOT_DIR}/tools/smoke_generator_astro_conformance.py"

echo "[13/18] testing scrapy offline integration"
cd "${ROOT_DIR}/integrations/scrapy"
# Use the in-tree consumer so adapter tests track reference validation, not PyPI lag.
uv run --with 'Scrapy>=2.11' --with 'requests>=2.31' \
  --with-editable "${ROOT_DIR}/implementations/python-consumer" \
  python tests/test_offline.py

echo "[14/18] checking dogfood manifest in sync with site/"
cd "${ROOT_DIR}"
uv run --project "${PYTHON_CONSUMER_DIR}" --locked python "${ROOT_DIR}/tools/check_dogfood_manifest.py"

echo "[15/18] checking v1.0 status disposition"
uv run --project "${PYTHON_CONSUMER_DIR}" --locked python "${ROOT_DIR}/tools/check_v1_status.py"

echo "[16/18] testing real Scrapy traversal"
uv run --project "${ROOT_DIR}/integrations/scrapy" --with 'Scrapy>=2.11' \
  --with-editable "${PYTHON_CONSUMER_DIR}" python "${ROOT_DIR}/integrations/scrapy/tests/test_traversal.py"
echo "[17/18] checking clean artifact installs"
uv run --project "${PYTHON_CONSUMER_DIR}" --locked python "${ROOT_DIR}/tools/check_install_artifacts.py"
echo "[18/18] checking equivalent benchmark outcomes"
uv run --project "${PYTHON_CONSUMER_DIR}" --locked python "${ROOT_DIR}/tools/benchmark_consumers.py" --pages 20 --output /tmp/pagedigest-benchmark-check.json
echo "all checks passed"
