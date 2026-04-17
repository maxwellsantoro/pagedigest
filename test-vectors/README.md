# pagedigest Test Vectors

This directory contains conformance-oriented fixtures for generators and consumers.

## Contents

- `valid-minimal.json`: valid minimal manifest.
- `valid-with-digest.json`: valid manifest with digests.
- `valid-partial-prefix.json`: valid partial manifest with `coverage.mode=prefixes`.
- `valid-with-coverage-complete.json`: valid manifest with `coverage.mode=complete`.
- `coverage-mode-change-prev.json` and `coverage-mode-change-next.json`: pair illustrating that coverage semantic changes bump `site_rev`.
- `url-key-variants.json`: valid key examples for trailing slash, material query variants, and percent-encoding.
- `invalid-missing-required.json`: invalid manifest (missing required `entries`).
- `invalid-url-key-fragment.json`: invalid key example (contains `#fragment`).
- `violation-monotonicity-prev.json` and `violation-monotonicity-next.json`: pair illustrating monotonicity violation.
- `audit-match/`: audit sample where digest matches identity bytes.
- `audit-mismatch/`: audit sample where digest does not match identity bytes.
- `index.json`: machine-readable case index.

These vectors intentionally include both schema-invalid and protocol-anomalous examples.
