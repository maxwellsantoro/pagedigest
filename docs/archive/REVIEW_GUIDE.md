# Review Guide (archived)

> **Archived** after v1 RC sign-off. Kept for historical context on the RC review round. For current quality gates, run `./tools/run_checks.sh`. For release tracking, see [RELEASE_CHECKLIST.md](../../RELEASE_CHECKLIST.md).

This document was a focused map for the RC review round.

## Primary goals for this round

- Confirm Phase 0 specification clarifications are precise and non-breaking.
- Confirm minimal reference implementations are credible and align with docs.
- Confirm conformance vectors and quality gates are sufficient for RC-level confidence.

## High-priority files

- `SPEC.md`: protocol clarification edits (consumer scope, lookup rules, rollback monotonicity, conditional requests, digest-free trust note).
- `README.md`: launch positioning, best-fit consumer framing, conformance/CI usage.
- `RELEASE_CHECKLIST.md`: pre-freeze clarifications and launch-now completion tracking.

## Implementation surfaces

- `implementations/rust-generator/`: minimal generator CLI and unit tests.
- `implementations/python-consumer/`: minimal consumer APIs and unit tests.
- `test-vectors/`: valid/invalid/anomalous fixtures and audit match/mismatch pairs.

## Quality-gate tooling

- `tools/validate_vectors.py`: vector integrity checks.
- `tools/smoke_generator_progression.py`: end-to-end generator revision progression smoke test.
- `tools/run_checks.sh`: one-command local check runner.
- `.github/workflows/ci.yml`: CI mirror of local quality gates.

## Reviewer commands

```bash
./tools/run_checks.sh
```

`tests/test_vectors.py` loads the conformance bundle through `validate_manifest` and `diff`.