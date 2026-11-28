# Bash publication and recovery

- [Bash publication and recovery](#bash-publication-and-recovery)
  - [Sequence](#sequence)
  - [Retry states](#retry-states)
  - [Package association](#package-association)
  - [Resource limits](#resource-limits)
  - [Limits of authority](#limits-of-authority)
  - [Known limits](#known-limits)

## Sequence

After [setup](bash-configuration.md), run `./scripts/release.sh` from clean, already-pushed `main`. Exclude other repository/image/package writers through completion; `.template-operation.lock` protects only this checkout.

The command rejects old installation/checkpoint state, checks builder platforms, and verifies remote `main` and [Git destinations](bash-configuration.md#files-and-setup). It never pushes source. For a fresh version, it then:

1. Reads complete tag/release inventories and captures `latest` as the predecessor.
2. Reuses verified staging under the plain version tag or builds both platforms from a private committed snapshot with `--push`.
3. Verifies immutable manifests/configuration labels and pushes the exact deterministic annotated Git tag.
4. Promotes the verified digest to `latest` without rebuilding, then creates the notes-only Gitea release.
5. Verifies publication, links the configured package, and rechecks both before success.

Credentials stay outside the project; ignored/untracked files are not exported into the snapshot. Build and staging push are one operation, so staging may exist after a failed build response. See the [operator checklist](release-process.md) for progress and troubleshooting.

Fresh source, tag, and alias guards run before later writes. Failed, oversized, malformed, or conflicting evidence stops publication. An already-prepared alias skips duplicate promotion; no failure refreshes the predecessor or authorizes rollback.

The `container-release-bash/1` annotation binds source, configuration/script hashes, version, image/digest/platforms, predecessor, and notes hash/path. Canonical JSON and fixed tagger identity/time allow exact reconstruction. Local refs are not overwritten; remote tag pushes are non-force. Old-format publications are not adopted; preserve their original checkout/pin.

Success prints `Publication verified` with the version, immutable image, latest alias, and release URL, then returns zero. There is no image cleanup stage.

## Retry states

- **Tag and release absent:** a retry may reuse verified staging or build again if no recoverable staging exists. There is no durable pre-build journal or exactly-once guarantee.

- **Both present and matching:** verify the complete identity/body, bound immutable digest, and that both the plain version and `latest` resolve to that digest. No build, promotion, tag push, or release POST occurs. Only a missing [package association](#package-association) may be completed. Missing bound content, a wrong/missing final alias, changed inputs, or newer publication evidence stops the retry.

- **Only tag or release present:** stop before builds or publication writes. Without a durable journal, interruption and deletion are indistinguishable. Inspect the original inputs and exact remaining objects; manual completion needs separate review.

A running fresh invocation may reconcile its own lost tag/promotion/release response against fresh matching evidence without repeating a confirmed write. That in-memory authority does not survive restart. Input or byte-budget refusals stop; truncated responses never authorize continuation.

Once confirmed, the exact tag object and peeled source commit must remain present. Disappearance, lightweight replacement, or changed identity stops the next write without repushing the tag. An accepted promotion remains intact if later verification refuses release creation.

Before promotion confirmation, `latest` may equal the predecessor or prepared digest. After a successful read confirms the prepared digest, every later alias guard requires it exactly, including skipped/reconciled promotion paths. Reversion, disappearance, foreign content, or a read failure stops release creation; no reread erases conflicting evidence.

Failures preserve accepted state. Do not blindly retry, delete records, rewrite tags/checkpoints, roll back aliases/source, reassign packages, or change inputs to force adoption.

## Package association

Association is package-wide and affects all versions. The package name comes from the image setting and may differ from the repository name. After verifying publication, read:

- `GET /api/v1/repos/{owner}/{repo}`.
- `GET /api/v1/packages/{owner}/container/{name}/latest` — the literal `latest` tag, not `/-/latest`.

Require exact package owner/type/name/version, positive integer ID, and an explicit `repository` field. Repository evidence must match its positive integer ID, full owner/name, name, and owner login. Display URLs and the OCI source label are not association evidence.

- **Correct link:** read-only; no server-version check is needed.
- **Conflicting link:** stop without unlinking or reassigning.
- **Explicit JSON null:** a candidate for linking, not proof of no link. Gitea may hide inaccessible linked repositories as null.

The script does not query the server version. Automatic linking requires a link endpoint that refuses to replace an existing association, including a hidden one. The client cannot verify that behavior from a null repository or from readback after a write. If your server does not provide that guarantee, link the package manually before running publication. Missing packages or invalid/inaccessible evidence also stop linking.

Refresh repository/package evidence, then send one bodyless `POST /api/v1/packages/{owner}/container/{name}/-/link/{repo_name}`. Require empty HTTP 201 and exact readback. No other package is enumerated or changed. Linking requires package-write access, appropriate token scopes, matching owners, and target repository package-unit write permission.

A lost transport response permits one fresh package read, never another POST. Only the exact link allows continuation; input/resource/HTTP-status refusals are fatal. Publication and association are rechecked before success. Failures preserve accepted state. A new invocation may finish a missing link only after all completed-publication checks pass with unchanged identity.

Exclude other association writers, UI actions, and in-flight requests until completion. The existing-link check and database update are not atomic compare-and-set; neither preflight reads nor the checkout lock protect against external races. Do not write associations without this exclusion.

Contract evidence:

- Gitea v1.25.0: [routes](https://github.com/go-gitea/gitea/blob/v1.25.0/routers/api/v1/packages/package.go), [response fields](https://github.com/go-gitea/gitea/blob/v1.25.0/modules/structs/package.go), [hidden-link conversion](https://github.com/go-gitea/gitea/blob/v1.25.0/services/convert/package.go), and [existing-link refusal](https://github.com/go-gitea/gitea/blob/v1.25.0/services/packages/package_update.go).
- Gitea v28.2.0: commit `829b49c1ae96015e345f9d2a0eb1ea7acd5f31e1`, from annotated tag object `1dc1ecdddcdc60ab14ec14e30e7bb4d84242f21f`. Reviewed [routes/access](https://github.com/go-gitea/gitea/blob/829b49c1ae96015e345f9d2a0eb1ea7acd5f31e1/routers/api/v1/api.go), [GET/link handler](https://github.com/go-gitea/gitea/blob/829b49c1ae96015e345f9d2a0eb1ea7acd5f31e1/routers/api/v1/packages/package.go), [response fields](https://github.com/go-gitea/gitea/blob/829b49c1ae96015e345f9d2a0eb1ea7acd5f31e1/modules/structs/package.go), [repository identity](https://github.com/go-gitea/gitea/blob/829b49c1ae96015e345f9d2a0eb1ea7acd5f31e1/services/convert/repository.go), [hidden links](https://github.com/go-gitea/gitea/blob/829b49c1ae96015e345f9d2a0eb1ea7acd5f31e1/services/convert/package.go), [refusal/permissions](https://github.com/go-gitea/gitea/blob/829b49c1ae96015e345f9d2a0eb1ea7acd5f31e1/services/packages/package_update.go), and [non-conditional update](https://github.com/go-gitea/gitea/blob/829b49c1ae96015e345f9d2a0eb1ea7acd5f31e1/models/packages/package.go). Existing links return HTTP 400, denied permission 403, and success empty 201. Response `id` identifies the package version, not the package-wide association.

Before supporting another version, pin its source and review the same contract, including concurrency behavior. Run helper/full-entry regressions for existing, new, and unsupported versions. Source checks and fake-server tests do not certify a deployed server or its permissions.

If the gate refuses linking, inspect accepted publication/association read-only. Do not bypass the gate or HTTPS trust to force success. Review new compatibility separately; changed scripts cannot adopt historical publications.

## Resource limits

Receive limits apply before JSON parsing: Gitea responses/OCI manifests/indexes 4 MiB; OCI config/token responses 1 MiB; notes/annotations/HTTP headers 64 KiB; refs 16 MiB; HTTP status 16 bytes; stderr 1 MiB. Complete exact-limit data is accepted; one byte over is refused, never parsed as a prefix. Raw stderr is not relayed.

Each inventory scan allows 1,002 API pages, 100,000 API/ref records, 64 MiB total payload, and 600 seconds. Pages request 100 records; listings must end with a confirmed empty page. Repetition, duplicates, exhausted budgets, or missing termination block the next write. Reads time out after 60 seconds; builds after 7,200 seconds. Limits do not bound Docker storage or arbitrary Git pack transfers.

## Limits of authority

The workflow supports one image, two platforms, and one package association. It does not run application tests, hooks, archive attachments, managed upgrades, retention, local-image removal, or old-checkpoint migration. Run application tests before committing release source.

Checks detect observed conflicts but cannot make cross-service writes atomic. Keep other writers excluded and checkout/tool configuration unchanged through completion. No failure grants repair, rollback, deletion, or reassignment authority.

## Known limits

Verification is local and model-based, not certification of native Docker plugin/daemon/TLS behavior, deployed APIs/UI, runtime emulation, storage, power-loss durability, or a live 0.7.0 release. Earlier live results remain historical; see [verification](verification.md).

Docker config has deliberate [parsing restrictions](bash-configuration.md#credentials-and-prerequisites). Plugin search order is preserved, not executable contents; keep files/configuration stable. There is no distributed lock, durable journal, or SIGKILL cleanup. Live experiments require separate approval for target/source/version, resource scope, credentials, platforms, and writer exclusion.
