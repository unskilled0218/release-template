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

Root `VERSION` must agree with the prepared version in README, the configured versioned notes path, and its `# Release v<version>` heading. No package/module version metadata or external packages are required. Help needs only Bash; validation checks local settings without credentials, Docker, publication state, or network calls. Syntax checks apply only to the remaining scripts/tests. Active README/docs links and TOCs must resolve; historical notes and archived task records intentionally retain references to retired paths.

## Coverage and isolation

The retained suite exercises the actual Bash entry, standalone data helper, bounded subprocesses, and real owned temporary Git/bare-remotes. Docker/curl publication ports are fake executables; helper transport cases inject bounded capture results, not production HTTP. Tests use disposable private tokens and synthetic connection metadata, never real credentials, Docker config, TLS keys, or the default token. They perform no real Docker daemon operations or production publication.

Coverage includes one-build/digest-promotion/notes-only publication, completed no-write retries independent of staging, startup ambiguity, immutable image/tag/notes/source conflicts, accepted-but-response-lost writes, staging reuse, private auth, host/context/TLS/builder-state selection, locks/signals, committed snapshot isolation, and old-state refusal. Checked-read fault cases require actual injection and zero subsequent writes; confirmed-tag loss/replacement cases preserve accepted state without repair or rollback. All 65 previous Bash behavior tests remain represented, with the obsolete legacy-entry pointer assertion changed to supported usage. The 257 old-engine methods are retired after behavior mapping; useful current HTTP/Bearer/digest, literal-note/normalization, and deterministic-annotation cases are exercised against the standalone helper instead. No cleanup/installer/journal/hook suite is shipped or claimed as currently tested.

Package association cases cover differently named package/repository targets, untouched unrelated packages, correct/unlinked/conflicting and permission-hidden links, the stable-1.25.x write gate, empty 201 responses, exact identity parsing, refreshed prerequisites, failed reads and POSTs, accepted-but-lost transport responses, post-link verification failures, and publication changes after linking. Completed retries may finish only a missing association, with no build, promotion, tag push, release POST, or staging lookup. Fake-port tests assert actual injection and externally visible writes/state, including preservation of accepted publication and link state after failure. These tests do not certify the deployed API, account permissions, UI rendering, or distributed writer exclusion; the reference contract is Gitea v1.25.0, including its server-side refusal to replace existing links.

Receiving tests cover exact byte limits and one-byte overflow, unending output/stderr, blocked stdin, timeout and descendant termination. Inventory tests cover page/item/cumulative-byte/time budgets and incomplete, repeated, duplicate, or malformed evidence. Timeout-equivalent curl exits in full-entry tests complement real bounded subprocess timeouts; neither certifies actual network latency or power-loss behavior. See [budgets and retry limits](bash-publication.md#resource-limits).

The connection fixture models effective host/context selection and synthetic endpoint/TLS/builder state, not Docker CLI plugin discovery or native daemon routing. The [two known publication warnings](bash-publication.md#known-limits) remain unresolved and are separate from removal of old support. A passing suite is not live-release approval.

## Historical evidence and live limits

The v0.2.5 live results belong to their original source/pin and old workflow. Sanitized records remain in [archived task 9](../tasks/_archives/9-publish-images-readable-releases/4-implemented.md), its adjacent evidence, and immutable Git history. Existing release notes and archived task records remain unchanged. They do not certify 0.5.0, and current code must not be substituted into preserved transactions.

No live 0.5.0 publication, package association/UI result, Docker routing/TLS/plugin behavior, runtime emulation, deployed server/storage semantics, deletion safety, or power-loss durability is established by local checks. Any live experiment requires separate explicit target, version/source, image/release/package scope, credentials, and platform approval. Do not execute privileged host preparation, publish, repair/reassign/delete resources, or rewrite old evidence as part of local verification.
