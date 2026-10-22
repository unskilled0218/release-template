# Retention safety

- [Retention safety](#retention-safety)
  - [Deletion evidence gate](#deletion-evidence-gate)
  - [Candidate selection](#candidate-selection)
  - [Staging and abandoned runs](#staging-and-abandoned-runs)

## Deletion evidence gate

Destructive container cleanup is blocked by default, including staging-alias retirement. No live Forgejo deletion verification was performed for the initial implementation. A mock test or manually setting a Boolean in configuration is not live evidence. An operator must first run the [disposable-server contract checks](verification.md#live-contract-checks) on the same Forgejo 17 server, preserve the actual results, and supply a private JSON attestation via `--deletion-evidence`.

The attestation is a trusted operator input, not a cryptographic proof. Its schema must include `schema: 1`, the exact `origin`, `server_major: 17`, a distinct `disposable_repository`, nonempty `operator` and `verified_at`, and true results for `alias_preserves_shared_manifest`, `digest_deletion_is_scoped`, and `retained_platforms_pullable`. It must accompany retained test logs and identify the actual tested environment. The tool verifies its target binding and the running server's major version; it cannot establish that an operator's attestation is truthful. Reverify after Forgejo/storage changes. No passing attestation is shipped in examples or generated from mock tests for real use.

Until an authorized disposable environment is available, deliver code/tests with cleanup disabled. The engine must never substitute a production project as a contract-test target.

## Candidate selection

Read-only `cleanup-plan` performs no deletion and needs no deletion attestation. Apply snapshots all paginated candidates before deletion, then revalidates current publication and candidate identities between operations. Server-capped page sizes do not end enumeration early. Repeated pages, malformed responses, uncertain API failures, and unbounded enumeration fail closed.

Only exact configured container names associated with the configured repository qualify. Older stable semantic release records are deleted, not their Git tags or source history. Drafts, prereleases, unknown versions, newer records, and unrelated packages are preserved. Digests require source-label and older-version evidence; ambiguous digest records remain with an explicit incomplete result.

Current aliases, indexes, runnable platform manifests, attestations, and nested graph dependencies remain protected. The protected union includes unfinished sibling checkpoint outputs for the same repository. A current manifest can have old tag aliases, so verified tag deletion semantics are required even when only deleting an alias. Never delete a protected `sha256:` package record. Attestation-only historical digests without trustworthy version/source evidence are deliberately left for manual investigation, not speculative garbage collection.

After a failed deletion, publication remains successful, cleanup returns nonzero, and the persisted candidate inventory supports idempotent retry. Confirmed target absence is safe; authorization/connectivity errors are not absence. Current images are reverified after cleanup. Historical packages/releases and attachments are not a rollback archive: once removed, version-pinned consumers may no longer pull old versions. Git tags remain but do not restore registry availability.

## Staging and abandoned runs

Staging tags are `rt-<run-id>-<image>` and are owned by exact checkpoint tag/digest inventories. Successful runs retire their staging aliases only after publication verification and the deletion gate. Partial retirement resumes from saved candidates; unsafe or unclassifiable leftovers report cleanup incomplete.

Unfinished runs retain manifests needed to resume. Abandoned-run cleanup must be explicitly selected and is not automatic expiration:

```sh
FORGEJO_USERNAME=your-login ./scripts/release.sh abandon --tag v2.0.0 --run <abandoned-run-id> --minimum-age-days 30 --deletion-evidence /protected/forgejo-verification.json
```

The current release must already be verified. Selected checkpoints must belong to the same repository, be unpublished, not be the current run, be older than the threshold (at least one day), and have complete staging ownership/digests. This command retires selected aliases only, preserves graph protection, and records abandonment. It never deletes raw manifest digests from an abandoned run. Missing inventories, changed digests, and unknown ownership stop the operation. Stop any external publisher of that run first; a timestamp or tag prefix alone never authorizes deletion.
