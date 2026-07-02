# Review Guide

This document is a focused map for the next review round.

## Primary goals for this round

- Confirm Phase 0 specification clarifications are precise and non-breaking.
- Confirm minimal reference implementations are credible and align with docs.
- Confirm conformance vectors and quality gates are sufficient for RC-level confidence.

## High-priority files

- `SPEC.md`: protocol clarification edits (consumer scope, lookup rules, rollback monotonicity, conditional requests, digest-free trust note).
- `README.md`: launch positioning, best-fit consumer framing, conformance/CI usage.
- `RELEASE_CHECKLIST.md`: pre-freeze clarifications and launch-now completion tracking.

## New implementation surfaces

- `implementations/rust-generator/`: minimal generator CLI and unit tests.
- `implementations/python-consumer/`: minimal consumer APIs and unit tests.
- `test-vectors/`: valid/invalid/anomalous fixtures and audit match/mismatch pairs.

## Quality-gate tooling

- `tools/validate_vectors.py`: vector integrity checks.
- `tools/smoke_generator_progression.py`: end-to-end generator revision progression smoke test.
- `tools/run_checks.sh`: one-command local check runner.
- `.github/workflows/ci.yml`: CI mirror of local quality gates.

## Suggested reviewer commands

```bash
./tools/run_checks.sh
```

Optional focused checks:

```bash
python tools/validate_vectors.py
python tools/smoke_generator_progression.py
cargo test --manifest-path implementations/rust-generator/Cargo.toml
python -m unittest discover -s implementations/python-consumer/tests -v
```

`tests/test_vectors.py` loads the conformance bundle through `validate_manifest` and `diff`.

## Review questions

- Do the new spec statements close interop ambiguity without expanding scope?
- Do generator/consumer behaviors match the contract and checklist claims?
- Are vectors representative enough to catch common implementation errors?
- Is CI coverage aligned with what maintainers will actually rely on before merge?
