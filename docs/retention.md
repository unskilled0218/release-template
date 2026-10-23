# Retention safety

- [Retention safety](#retention-safety)
  - [Deletion evidence gate](#deletion-evidence-gate)
  - [Candidate selection](#candidate-selection)
  - [Retirement schedule](#retirement-schedule)
  - [Staging and abandoned runs](#staging-and-abandoned-runs)

## Deletion evidence gate

Destructive container cleanup is blocked by default, including staging-alias retirement. Historical initial implementation records did not verify live Forgejo deletion; they do not establish Gitea compatibility. No live Gitea deletion verification has been performed. A mock test or manually setting a Boolean in configuration is not live evidence. An operator must first run the [disposable-server contract checks](verification.md#live-contract-checks) on the actual Gitea deployment, preserve the actual results, and supply a private JSON attestation via `--deletion-evidence`.

The attestation is a trusted operator input, not a cryptographic proof. It requires `schema: 2`, `product: "gitea"`, the exact configured `origin`, an exact full `server_version`, a distinct `disposable_repository` in owner/repository form, nonempty `operator` and `verified_at`, and true results for `alias_preserves_shared_manifest`, `digest_deletion_is_scoped`, and `retained_platforms_pullable`. It must accompany retained test logs and identify the actual tested environment. Versions must be bounded `MAJOR.MINOR.PATCH` with optional prerelease/build suffixes; runtime equality includes those suffixes. Old schema-1, major-only, mixed-product, stale, or malformed evidence cannot enable deletion. The tool checks target/version binding but cannot establish product identity from `/version` alone or prove an attestation truthful. Reverify after Gitea version/build or storage changes. No passing attestation is shipped in examples or generated from mock tests for real use.

Until an authorized disposable environment is available, deliver code/tests with cleanup disabled. The engine must never substitute a production project as a contract-test target. Missing or foreign repository links produce explicit skipped diagnostics and cleanup incomplete. Linking is an operator-controlled whole-package action requiring separate adoption approval; the tool never links or reassigns owner-scoped packages.

## Candidate selection

Read-only `cleanup-plan` performs no deletion and needs no deletion attestation. Apply snapshots all paginated candidates before deletion, then revalidates current publication and candidate identities between operations. Server-capped page sizes do not end enumeration early. Repeated pages, malformed responses, uncertain API failures, and unbounded enumeration fail closed.

Only exact configured container names associated with the configured repository qualify. Older stable semantic release records are deleted, not their Git tags or source history. Drafts, prereleases, unknown versions, newer records, and unrelated packages are preserved. Digests require source-label and older-version evidence; ambiguous digest records remain with an explicit incomplete result.

Current aliases, indexes, runnable platform manifests, attestations, and nested graph dependencies remain protected. The protected union includes unfinished sibling checkpoint outputs for the same repository. A current manifest can have old tag aliases, so verified tag deletion semantics are required even when only deleting an alias. Never delete a protected `sha256:` package record. Attestation-only historical digests without trustworthy version/source evidence are deliberately left for manual investigation, not speculative garbage collection.

Preserving a reference also preserves its complete reachable manifest graph. Inventory is exhausted before selecting digest deletions. Unknown, prerelease, newer, external-staging, and ineligible digest records contribute graph protection, even when an older checkpoint already completed cleanup. Same-name records with missing or different repository association are never deletion targets and still protect shared content. If a relevant reference cannot resolve or its graph cannot be fetched, cleanup stops before deletion. Uncertain digest ownership is decided across all runnable configurations, including subject dependencies, not just AMD64/ARM64; every runnable source label must match and every version must be provably older. Artifact-only or unclassifiable evidence cannot authorize digest deletion.

Saved inventories do not gain authority from fresh policy eligibility. Every live reference without an exact matching pending candidate protects its graph, including a newly introduced older stable alias or a recreated completed record. Cleanup never silently adds these references to its candidate list. Before any saved-plan deletion and between operations, fresh evidence revalidates pending identities and survivor protection; newly protected candidates stop with cleanup incomplete. Authorized aliases retire before their backing digests even if the saved inventory has a different order. Matching-identity old-shaped inventories receive these checks; cross-revision checkpoint adoption is not supported.

After a failed deletion, publication remains successful, cleanup returns nonzero, and the persisted candidate inventory supports idempotent retry. Only an explicitly allowed HTTP 404 establishes lookup absence; HTTP 200 JSON `null`, non-object optional lookups, malformed JSON, and authorization/connectivity errors are not absence. Invalid lookup evidence cannot authorize release creation, deletion, candidate completion, or abandonment. If DELETE already succeeded but confirmation is malformed, the candidate remains pending and later/dependent deletions stop. A consistent listing and verified-404 retry reconcile absence without repeating that DELETE or rebuilding retired dependencies; no rollback is attempted. Earlier legitimate side effects and durable intent remain intact. This patch does not automatically repair old falsely completed checkpoints or adopt old-pin state; preserve their provenance for separately reviewed recovery. Current images are reverified after cleanup. Historical packages/releases and attachments are not a rollback archive: once removed, version-pinned consumers may no longer pull old versions. Git tags remain but do not restore registry availability.

## Retirement schedule

Version 0.1.2 retires authorized referring manifests before their candidate dependencies, not in package listing order. Membership and subject reachability both count, including transitive paths through manifests without package records. Every candidate parent must retire before a shared child. Image names scope graph keys, so identical digests in different image namespaces do not merge authority. Aliases still retire before raw digests. Ineligible artifact/attestation roots remain protected, not reclassified to make scheduling easier.

The cleanup inventory contains nested `retirement` metadata with these fields:

- `schema`: `1`, independent of the unchanged outer checkpoint schema.
- `run`: the exact cleanup run ID.
- `graphs`: records containing `key: [image_name, digest]` and sorted `reachable` immutable manifest digests, including the root and transitive dependencies. Every raw digest candidate has exactly one record.
- `order`: referring-manifest-first topological order of those stable keys, with deterministic image/digest tie-breaking for independent nodes.
- `fingerprint`: SHA-256 of canonical JSON containing `run`, `graphs`, and sorted immutable candidate projections. Package projections contain kind/name/version/digest; release projections contain kind/id/tag. Mutable completion flags are excluded, so progress does not change approval.

Read-only planning returns this proposed metadata without writing it. Apply durably saves the approved candidate inventory and schedule together before any deletion, including earlier alias/release deletions. Unknown schemas, missing/duplicate nodes, cycles, altered identities, or inconsistent order/fingerprint stop deletion. Limits are 10,000 candidates and 100,000 total stored reachability references; oversized inputs stop rather than truncate. Metadata is local checkpoint evidence, not a signature or a substitute for current ownership checks.

Retries preserve the schedule and reconcile exact candidate absence against fresh package inventory and the scoped API before graph traversal of remaining records. Successful package deletion is confirmed absent before completion is flushed. A lost response can therefore complete an already absent operation without another DELETE or fetching its retired parent graph. Inconsistent listings, authorization/connectivity failures, or unreadable live graphs stop progress. Every live pending graph is fetched again and must match approved reachability; preserved-reference and unfinished-run protection is still refreshed between operations. A recreated completed parent or a newly introduced unscheduled root protects its graph and can stop a pending dependency deletion. Saved topology never grants new deletion authority.

An intact matching-identity old-shaped inventory without `retirement` may acquire a schedule only when all raw candidates are still present with full validated evidence and none is marked complete. Alias-only inventories can use an empty schedule. Missing/completed raw candidates or broken pending graphs without an approved schedule require explicit operator recovery; the tool does not infer past order, reconstruct deleted content, erase checkpoints, or rewrite identity. Cross-revision adoption remains unsupported, even though the outer checkpoint schema remains 1.

## Staging and abandoned runs

Staging tags are `rt-<run-id>-<image>` and are owned by exact checkpoint tag/digest inventories. Successful runs retire their staging aliases only after publication verification and the deletion gate. Partial retirement resumes from saved candidates; unsafe or unclassifiable leftovers report cleanup incomplete.

Unfinished runs retain manifests needed to resume. Abandoned-run cleanup must be explicitly selected and is not automatic expiration:

```sh
GIT_USERNAME=your-login ./scripts/release.sh abandon --tag v2.0.0 --run <abandoned-run-id> --minimum-age-days 30 --deletion-evidence /protected/gitea-verification.json
```

The current release must already be verified. Selected checkpoints must belong to the same repository, be unpublished, not be the current run, be older than the threshold (at least one day), and have complete staging ownership/digests. This command retires selected aliases only, preserves graph protection, and records abandonment. It never deletes raw manifest digests from an abandoned run. Missing inventories, changed digests, and unknown ownership stop the operation. Stop any external publisher of that run first; a timestamp or tag prefix alone never authorizes deletion.
