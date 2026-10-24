# Implemented

- [Implemented](#implemented)
  - [Changes](#changes)
  - [Source contract evidence](#source-contract-evidence)
  - [Verification](#verification)
  - [Limits](#limits)

## Changes

- Created new branch `18-support-gitea-28-2-0` from `42f9a7c` and implemented the reviewed plan. Corrected test ownership from review P1 is reflected in the use of existing `BashPublicationTests`.
- `scripts/release-data.py` now accepts exact stable `28.2.0` alongside the unchanged stable `1.25.x` version policy. Other versions, suffixes, development builds, malformed responses, and failed reads remain fail-closed for new links. The fixed diagnostic names both contracts without interpolating remote data.
- Preserved strict repository/package identity evidence, correct-link read-only returns, refreshed prerequisites, visible/hidden foreign-link refusal, one POST per invocation, transport-only reconciliation, and exact read-back. No publication ordering, credentials, configuration schema, unlink, reassignment, deletion, or rollback behavior changed.
- `tests/test_bash_release.py` retains original association cases on fixture-default `1.25.0` and generates 12 named `28.2.0` counterparts in the same test class, each with its own standard unittest setup/cleanup lifecycle. Coverage includes fresh/correct/conflicting/hidden links, completed retries, lost responses, prerequisite faults, post-link failures, and publication changes after linking. Existing `gitea_version` fixture support was sufficient; no fixture behavior was changed.
- Helper tests exercise accepted `1.25.0`, `1.25.1`, `1.25.123`, and `28.2.0` through actual association control flow, including empty 201 and lost-response reconciliation. Expanded unsupported-version/document cases assert zero POSTs and fixed diagnostics. A new correct-link case proves unknown server contracts need no version request or mutation.
- Updated README and dedicated configuration, publication, process, verification, and image-usage documentation with exact support boundaries, permanent source references, downstream review/recovery instructions, and live-verification limits. Existing release notes, archived tasks, prior review evidence, and `todo.md` remain unchanged.
- Prepared patch version `0.6.1` in root `VERSION`, README, `scripts/release.json` notes path, and new `docs/releases/0.6.1.md`. No release was published.

## Source contract evidence

Resolved upstream annotated tag `v28.2.0` through GitHub's ref/tag API: tag object `1dc1ecdddcdc60ab14ec14e30e7bb4d84242f21f`, commit `829b49c1ae96015e345f9d2a0eb1ea7acd5f31e1`. This records source provenance, not signature verification or deployed-binary identity. Permanent links are in [package association](../../docs/bash-publication.md#package-association).

- `routers/api/v1/api.go` registers the named package-version GET and bodyless package-link POST under authenticated package-scope/access middleware, with write access required for linking.
- `routers/api/v1/packages/package.go` selects the package and repository within the owner scope, maps existing-link refusal to HTTP 400 and denied permission to HTTP 403, and returns empty HTTP 201 on success.
- `modules/structs/package.go` exposes the explicit nullable `repository` field. `services/convert/package.go` supplies version ID, owner, type/name/version, and permission-filtered repository identity; hidden linked repositories can appear as null.
- `services/convert/repository.go` supplies positive repository ID, owner, name, and full name used by existing helper identity validation. An initial lookup of guessed `services/convert/repo.go` returned HTTP 404; directory discovery located the actual file, which was then reviewed at the pinned commit.
- `services/packages/package_update.go` rejects an existing nonzero `RepoID`, requires the same owner, and checks target repository package-unit write permission. `models/packages/package.go` updates by package ID without an unlinked-row condition. Existing-link refusal is therefore not an atomic compare-and-set; operator exclusion of competing writers remains mandatory.

## Verification

- `python3 -B -m unittest tests.test_bash_release.BashDataTests -v`: 29 tests passed in 0.999 seconds.
- The initial full-suite run exceeded the tool's 120-second timeout before completion; completed cases shown in its log passed. A fresh run without a tool timeout completed successfully: `python3 -B -m unittest discover -s tests -v` passed all 117 tests in 836.205 seconds. This includes the 12 independently instantiated `28.2.0` association cases and retained `1.25.0` scenarios.
- `bash -n` for each `scripts/*.sh`: passed.
- `./scripts/release.sh --validate`: passed, reporting that configuration is valid without credentials or remote operations.
- Local Markdown link/anchor check: passed for all 16 README/docs Markdown files, including TOC targets and the new release notes.
- Active documentation search found no obsolete exclusive `1.25.x` support claim outside historical release notes. Current version references were updated to `0.6.1`; historical `0.6.0` notes remain intact.
- `git diff --check`: passed before this report. Final diff inspection confirms the production control-flow change is limited to the version guard/comment/diagnostic; other changes are tests, version/notes metadata, documentation, and this result record.

## Limits

All association execution evidence is local and hermetic: disposable Git/token fixtures, fake command ports, and injected helper transport. The fake server models source-reviewed refusal semantics; it is not independent certification of a deployed API. No production requests, real credentials, Docker daemon operations, privileged preparation, publication, link writes, or UI checks were performed during implementation. The earlier observed server version and planning-time connection failure remain historical context, not fresh deployment validation.

Operator-enforced exclusion must cover other association writers, UI actions, and in-flight requests through completion. Customized binaries with the same version string are not certified. Existing promotion and config-local Buildx-plugin warnings remain unresolved and outside scope. Historical publications require their preserved original script identities; these changed scripts cannot adopt them.
