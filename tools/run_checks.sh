#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_CONSUMER_DIR="${ROOT_DIR}/implementations/python-consumer"

if ! command -v uv >/dev/null 2>&1; then
  echo "missing uv; install it from https://docs.astral.sh/uv/ and rerun." >&2
  exit 1
fi

echo "[1/20] checking python formatting"
uv run --project "${PYTHON_CONSUMER_DIR}" --extra dev --locked ruff format --check \
  "${PYTHON_CONSUMER_DIR}/pagedigest" \
  "${PYTHON_CONSUMER_DIR}/tests" \
  "${PYTHON_CONSUMER_DIR}/examples" \
  "${ROOT_DIR}/tools"

echo "[2/20] linting python"
uv run --project "${PYTHON_CONSUMER_DIR}" --extra dev --locked ruff check \
  "${PYTHON_CONSUMER_DIR}/pagedigest" \
  "${PYTHON_CONSUMER_DIR}/tests" \
  "${PYTHON_CONSUMER_DIR}/examples" \
  "${ROOT_DIR}/tools"

echo "[3/20] validating test vectors"
uv run --project "${PYTHON_CONSUMER_DIR}" --extra dev --locked python "${ROOT_DIR}/tools/validate_vectors.py"

echo "[4/20] running python consumer tests"
cd "${PYTHON_CONSUMER_DIR}"
uv run --locked python -m unittest discover -s tests -v

echo "[5/20] checking python CLI"
uv run --locked pagedigest verify-live --help >/dev/null

echo "[6/20] checking content hygiene utility"
cd "${ROOT_DIR}"
uv run --project "${PYTHON_CONSUMER_DIR}" --locked python "${ROOT_DIR}/tools/check_content_hygiene.py" "${ROOT_DIR}/site" --fail-on warning

echo "[7/20] testing Astro integration"
cd "${ROOT_DIR}/packages/astro"
npm ci
npm test

echo "[8/20] testing npm launcher"
cd "${ROOT_DIR}/packages/cli"
npm ci
npm test

echo "[9/20] checking rust formatting"
cd "${ROOT_DIR}/implementations/rust-generator"
cargo fmt --check

echo "[10/20] linting and testing rust generator"
cd "${ROOT_DIR}/implementations/rust-generator"
cargo clippy --locked --all-targets -- -D warnings
cargo test --locked

echo "[11/20] running generator integration smoke test"
cd "${ROOT_DIR}"
uv run --project "${PYTHON_CONSUMER_DIR}" --locked python "${ROOT_DIR}/tools/smoke_generator_progression.py"

echo "[12/20] running generator↔Astro conformance smoke"
cd "${ROOT_DIR}"
uv run --project "${PYTHON_CONSUMER_DIR}" --locked python "${ROOT_DIR}/tools/smoke_generator_astro_conformance.py"

echo "[13/20] testing scrapy offline integration"
cd "${ROOT_DIR}/integrations/scrapy"
# Use the in-tree consumer so adapter tests track reference validation, not PyPI lag.
uv run --with 'Scrapy>=2.11' --with 'requests>=2.31' \
  --with-editable "${ROOT_DIR}/implementations/python-consumer" \
  python tests/test_offline.py

echo "[14/20] checking dogfood manifest in sync with site/"
cd "${ROOT_DIR}"
uv run --project "${PYTHON_CONSUMER_DIR}" --locked python "${ROOT_DIR}/tools/check_dogfood_manifest.py"

echo "[15/20] checking v1.0 status disposition"
uv run --project "${PYTHON_CONSUMER_DIR}" --locked python "${ROOT_DIR}/tools/check_v1_status.py"

echo "[16/20] testing real Scrapy traversal"
uv run --project "${ROOT_DIR}/integrations/scrapy" --with 'Scrapy>=2.11' \
  --with-editable "${PYTHON_CONSUMER_DIR}" python "${ROOT_DIR}/integrations/scrapy/tests/test_traversal.py"
echo "[17/20] checking clean artifact installs"
uv run --project "${PYTHON_CONSUMER_DIR}" --locked python "${ROOT_DIR}/tools/check_install_artifacts.py"
echo "[18/20] checking equivalent benchmark outcomes"
uv run --project "${PYTHON_CONSUMER_DIR}" --locked python "${ROOT_DIR}/tools/benchmark_consumers.py" --pages 20 --output /tmp/pagedigest-benchmark-check.json
echo "[19/20] testing real Scrapy cache policy transitions"
uv run --project "${ROOT_DIR}/integrations/scrapy" --with 'Scrapy>=2.11' \
  --with-editable "${PYTHON_CONSUMER_DIR}" python "${ROOT_DIR}/integrations/scrapy/tests/test_cache_policy.py"
echo "[20/20] testing dogfood whole-collection sync"
uv run --project "${PYTHON_CONSUMER_DIR}" --locked python "${ROOT_DIR}/tools/smoke_dogfood_sync.py"
echo "all checks passed"
