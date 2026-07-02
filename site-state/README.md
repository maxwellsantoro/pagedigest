# Generator state (dogfood)

This directory holds durable revision state for the `pagedigest.org` site manifest. The generator reads and updates it on each run so `site_rev` and per-URL `rev` values never decrease.

**Adopters:** treat your state file as private protocol state — persist it outside CI ephemeral storage (for example `.pagedigest/state.json` next to your build output). Do not commit it unless you intentionally want reproducible, shared counters across machines (as this dogfood setup does). After a backup restore or environment reseed, advance counters to a value strictly greater than any value previously published.