# Conformance fixtures

Machine-readable case index: [`index.json`](./index.json). Validated by `tools/validate_vectors.py` and `implementations/python-consumer/tests/test_vectors.py`.

| Kind | Examples |
|------|----------|
| `valid` | Minimal, digests, partial `coverage`, URL-key variants |
| `semantic-site-rev-bump` | Coverage mode/prefix changes bump `site_rev` |
| `semantic-rev-bump` | Content rollback still increments `rev` |
| `anomalous-sequence` | `site_rev` / `rev` decreases |
| `invalid-schema` / `invalid-spec` | Missing fields, fragment URL keys |
| `audit-match` / `audit-mismatch` | Digest vs `page-body.bin` |

Schema validation is necessary but not sufficient — normative rules are in [SPEC.md](../SPEC.md).