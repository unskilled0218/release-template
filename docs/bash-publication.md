# Bash publication and recovery

- [Bash publication and recovery](#bash-publication-and-recovery)
  - [Sequence](#sequence)
  - [Retry states](#retry-states)
  - [Resource limits](#resource-limits)
  - [Limits of authority](#limits-of-authority)

## Sequence

After [setup](bash-configuration.md), run `./scripts/release.sh` from the clean, already-pushed project `main`. The command locks `.template-operation.lock`, rejects managed/incomplete legacy installations and same-version legacy checkpoints, checks advertised platforms, and verifies effective fetch/push destinations and exact remote main. It does not push source for you. One operator must serialize writers to the target repository/image; a checkout lock is not a distributed lock.

Before any staging lookup that could build, complete bounded release/tag inventories and classify the requested remote tag/release. For a fresh version, capture `latest` as the predecessor, recover matching release-specific staging evidence or build once into a staging tag from a private committed source snapshot, verify both platform manifests/configuration labels, create/push the exact deterministic annotated tag, promote the verified digest to `latest`, create the notes-only Gitea release, then freshly verify all results. The command does not build image archives or rebuild for promotion. Ignored/untracked worktree secrets are not exported into the committed snapshot; credential files must remain outside the project.

Prerequisite reads have explicit failure branches; they are not evaluated as mutation permission inside a Bash comparison. The final promotion decision validates the same successfully read alias against the captured predecessor and prepared digest. A failed/oversized/malformed read or a newly foreign alias stops before promotion or release creation; an already-prepared alias skips duplicate promotion. No failure refreshes the predecessor or authorizes rollback.

Machine identity uses the separate `container-release-bash/1` annotation, not the Python schema-2 protocol. It binds source, configuration/script hashes, version, image/digest/platforms, predecessor, and notes hash/path. Fixed tagger identity/time and canonical JSON allow exact local reconstruction. Local refs are never overwritten; remote tag pushes are non-force. Existing old-format history is preserved, not adopted as new-format ownership.

Success prints the version, immutable image, latest alias, and release URL and returns zero. There is no automatic cleanup stage, so missing deletion evidence is not a post-publication failure in this workflow.

## Retry states

If both tag and release are absent, a retry may reuse verified staging. If staging was never recoverably published, an explicit retry may build again; there is no durable pre-build journal or exactly-once guarantee.

If both tag and release exist and match the complete current identity/body, verify the annotation-bound immutable digest and require `latest` to equal it. A missing or foreign staging alias is irrelevant: completed verification makes no staging lookup and performs no build, promotion, tag push, or release POST. Missing bound content, an old/foreign/missing final alias, changed source/config/scripts/notes, or newer publication evidence is a refusal, not repair authority.

Tag-only and release-only startup states are ambiguous and stop before builds or publication writes. Without a durable journal, the script cannot distinguish an interrupted first publication from a deleted completed record. Inspect the same source/config and exact remaining objects; any manual completion requires separate review. Do not delete records, rewrite tags/checkpoints, roll back source, or keep retrying with changed identity to force success.

A running fresh invocation can reconcile its own lost tag/promotion/release response against fresh matching remote evidence without repeating a confirmed write. It may continue from its own newly confirmed tag to first release creation; that in-memory evidence is unavailable to a new process. Byte-budget/input refusals stop, not becoming permission to continue writing after a truncated response. No failure trap performs remote rollback or deletion. Local immutable object recreation is not remote repair.

Tag confirmation is a one-way in-memory transition only after a fresh inventory proves the exact object and peeled source commit. Later promotion/release guards require that same tag to remain present. Disappearance, lightweight replacement, changed annotation, or wrong peeled evidence stops before the next write; it does not grant repush or release auto-tag authority. If promotion already succeeded, a later refusal leaves its accepted alias intact and sends no release POST. Startup ambiguity rules and the absence of a durable journal remain unchanged.

## Resource limits

The standard-library helper caps each Gitea response/OCI manifest/index at 4 MiB, OCI configuration/token responses at 1 MiB, notes and annotations at 64 KiB, and ref advertisements at 16 MiB. HTTP headers are capped at 64 KiB, status at 16 bytes, and stderr at 1 MiB without raw output relay. Data is bounded while receiving, before JSON parsing. Valid complete exact-limit bodies are accepted; one byte over is refused, never parsed as a prefix.

Each inventory scan shares limits of 1,002 API pages, 100,000 API/ref records, 64 MiB cumulative payload, and 600 seconds. API pages request 100 records and each listing must end with a confirmed empty page. Repeated pages/duplicate identities, exhausted budgets, or missing termination are incomplete evidence and block the next write. Individual reads time out after 60 seconds; a build has a separate 7,200-second timeout. These limits bound decoded helper output, not Docker build storage or arbitrary Git pack transfer size.

## Limits of authority

The workflow supports one image and two platforms, not arbitrary hooks, suites, archive attachments, managed upgrades, automatic tests of consumer applications, package linking, retention, local-image removal, or old-checkpoint migration. Run application tests separately before committing/pushing the release source. A pullable image can require separately authorized package association before appearing in a repository's Packages tab; this command never reassigns it.

Fresh version/source/alias checks detect conflicts but cannot make cross-service operations atomic or exclude writers in other checkouts. Keep operational writer exclusion through completion. No live 0.3.1 publication, runtime/emulation result, power-loss durability, storage behavior, or deletion safety follows from local fake-port tests. Earlier v0.2.5 live results remain historical.
