# Plan

- [Plan](#plan)

1. Build directly to the plain `VERSION` tag. Reuse verified matching content after interruption; refuse conflicting content. Promote the digest to `latest` as before.
2. Require the version tag to match the bound digest on completed retries and before reporting success. Keep the annotated Git tag and immutable digest reference.
3. Update fake-registry tests, the release summary, operator docs, README, version and release notes. Run shell syntax, offline validation and publication tests.
