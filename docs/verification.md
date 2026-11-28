# Verification

- [Verification](#verification)
  - [Local checks](#local-checks)
  - [Coverage and isolation](#coverage-and-isolation)
  - [Historical evidence and live limits](#historical-evidence-and-live-limits)

## Local checks

```sh
python3 -B -m unittest discover -s tests -v
for script in scripts/*.sh; do bash -n "$script"; done
./scripts/release.sh --validate
git diff --check
```

Root `VERSION`, README, configured notes path, and `# Release v<version>` heading must agree. Check active documentation links and TOCs; historical notes/tasks may retain retired paths. Help needs only Bash; validation needs no credentials, Docker, state, or network access.

## Coverage and isolation

Tests run the Bash entry, Python helper, bounded subprocesses, and owned temporary Git/bare repositories. Docker/curl ports are fake; transport helpers use injected responses. Tokens, Docker metadata, and plugin markers are synthetic. No production credentials, real Docker operations, or live publication are used.

Coverage includes:

- Fresh publication, staging reuse, completed retries that verify both the plain version and `latest` without retagging, ambiguous startup, exact annotations/notes/digests, source snapshots, and old-state refusal.
- Real Git URL rewriting, push fan-out/duplicates, and changed destination evidence. Tag/alias conflicts and failed reads block later writes without repair, including skipped and reconciled promotions.
- Package identity, correct/unlinked/conflicting/hidden links, linking without a version endpoint, permissions modeled by fixtures, empty 201, lost responses, and post-link verification. Completed retries can finish only a missing link.
- Private auth, Bearer challenges, host/context/TLS/builder selection, and modeled extra/config-local/system plugin order across preflight/build/promotion. Cases include relative paths, spaces, symlinks, malformed/bounded config, and alternate discovery-field spelling refusal.
- Lock ownership, inherited descriptors, setup guidance, signals, cleanup, and suppression of token/path/raw-output sentinels. A FIFO barrier checks that progress is visible while a build is blocked.
- Exact/over-limit receives, blocked stdin, unending output, timeouts/descendant termination, and inventory page/item/byte/time budgets. Incomplete, repeated, duplicate, or malformed evidence blocks subsequent writes.

Fault tests assert that injections occurred, inspect externally visible writes/state, and require preservation of accepted objects after refusal. Service/plugin models follow reviewed source contracts; they do not independently prove native behavior. See [association contracts](bash-publication.md#package-association) and [resource limits](bash-publication.md#resource-limits).

Tests prefer `/tmp/opencode` only when it exists, otherwise Python's standard temporary parent. Presence/absence simulations run actual Bearer assertions and publication setup with isolated `TMPDIR`/cache state, without changing a global directory. Retired engine, installer, cleanup, journal, and hook suites are not shipped or claimed as tested.

## Historical evidence and live limits

The v0.2.5 live results belong to the old workflow and original source/pin. See [archived task 9](../tasks/_archives/9-publish-images-readable-releases/4-implemented.md) and Git history. They do not certify 0.7.0; do not substitute current code into historical transactions.

Local checks do not certify live publication, deployed permissions/APIs/UI, native Docker behavior, runtime emulation, second-host portability, storage, deletion safety, or power-loss durability. Live experiments require explicit target/source/version, resource scope, credentials, and platform approval. Local verification does not authorize privileged setup, publication, repair, reassignment, deletion, or rewriting historical evidence.
