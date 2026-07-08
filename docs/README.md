# Documentation index

Agents: [AGENTS.md](../AGENTS.md) (symlinked as `CLAUDE.md`).

| Document | Audience | Purpose |
|----------|----------|---------|
| [SPEC.md](../SPEC.md) | Implementers | Normative wire format and consumer algorithm |
| [CONTRACT.md](../CONTRACT.md) | Publishers & crawlers | Social bargain, obligations, 429 pattern |
| [CONTENT_HYGIENE.md](../CONTENT_HYGIENE.md) | Publishers | Avoid false `rev`/`digest` churn; post-deploy reconcile |
| [ROADMAP.md](../ROADMAP.md) | Maintainers | Phases through v1.0 (complete) and Post-1.0 |
| [RELEASE_CHECKLIST.md](../RELEASE_CHECKLIST.md) | Maintainers | RC and 1.0 gates (v1.0 hard gates checked) |
| [ecosystem.md](./ecosystem.md) | Both | Relationship with [dotrepo](https://dotrepo.org) |
| [DOGFOOD_TEMPLATE.md](./DOGFOOD_TEMPLATE.md) | Publishers | Template for deployment case studies |
| [case-studies/dotrepo.md](./case-studies/dotrepo.md) | Publishers & consumers | Measured dotrepo.org dogfood deployment |
| [consumer-integration.md](./consumer-integration.md) | Consumers | Crawler, indexer, mirror, and agent integration guide |
| [cooperative-automation.md](./cooperative-automation.md) | Publishers & intermediaries | `PageDigest-State` logging, classification, nginx, and Cloudflare recipes |
| [announcements/v1-rc.md](./announcements/v1-rc.md) | Adopters & maintainers | Historical v1 RC announcement (protocol is v1.0) |
| [registrations/](./registrations/) | Maintainers | IANA registration drafts and filed request links |

Implementation guides: [rust-generator](../implementations/rust-generator/README.md), [python-consumer](../implementations/python-consumer/README.md).

Experimental integrations: [Scrapy consumer middleware](../integrations/scrapy/).

Conformance fixtures: [test-vectors/](../test-vectors/).
