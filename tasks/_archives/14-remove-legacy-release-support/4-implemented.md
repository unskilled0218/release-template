# Implementation

- [Implementation](#implementation)
  - [Outcome](#outcome)
  - [Removed Files](#removed-files)
  - [Supported Workflow And Documentation](#supported-workflow-and-documentation)
  - [Coverage Retirement And Migration](#coverage-retirement-and-migration)
  - [Verification](#verification)
  - [Compatibility And Unresolved Warnings](#compatibility-and-unresolved-warnings)
  - [Preserved Resources](#preserved-resources)

## Outcome

Implemented task 14 on new branch `14-remove-legacy-release-support`, created from plan-review commit `da45c00`. Prepared 0.4.0 with root `VERSION` as the sole project version source. The supported release entry remains `./scripts/release.sh`, backed by its standalone Python standard-library helper; Python 3.11+ is still required. No live publication, real Docker daemon operation, production credential access, push, or remote deletion was performed.

## Removed Files

Removed 52 tracked files within the approved scope, not local transaction state or old checkouts:

- All 13 engine files under `release_template/`: `__init__.py`, `adapters.py`, `cleanup.py`, `cli.py`, `config.py`, `core.py`, `git.py`, `linking.py`, `local.py`, `oci.py`, `policy.py`, `state.py`, and `workflow.py`.
- All 12 example files under `examples/`: `cargo.json`, `consumer.gitignore`, `explicit.json`, `hooks/cargo_version.py`, `hooks/dependent_build.py`, `node.json`, `project-notes.md`, `suite.json`, `ubuntu-hello/Dockerfile`, `ubuntu-hello/release.json`, `ubuntu-hello/verify.py`, and `version-file.json`.
- The three legacy scripts: `scripts/launch.py`, `scripts/legacy-release.sh`, and `scripts/update.py`.
- The 13 old-engine test modules named in the coverage map below, plus `tests/support.py`, whose shared fixtures imported the retired engine. Kept `tests/__init__.py`, `tests/test_bash_release.py`, and `tests/fixtures/bash_release_ports.py`.
- The ten legacy-only active docs: `docs/configuration.md`, `docs/credentials.md`, `docs/gitea-migration.md`, `docs/installation.md`, `docs/legacy-release.md`, `docs/local-images.md`, `docs/package-linking.md`, `docs/publication.md`, `docs/retention.md`, and `docs/ubuntu-release-test.md`.

Inspected both retiring source directories for unexpected contents before deletion. Three ignored CPython caches were found under `release_template/__pycache__/`; their magic and recorded source filenames confirmed they were generated from this checkout. Preserved them byte-for-byte outside the source tree at `/tmp/opencode/task14-retired-bytecode-r3c6jfl7` before removing now-empty directories. A direct rename initially failed across filesystems without moving data; verified copy-before-unlink preserved the three files. No broad cache deletion or recursive checkpoint removal was used.

## Supported Workflow And Documentation

The only changes to retained production execution code are two diagnostics in `scripts/release.sh`: unsupported options now print supported usage, and old-install state now points to the preserved original checkout/pin instead of a deleted local launcher. The marker/symlink refusals, same-version checkpoint refusal, lock, publication sequence, resource limits, schemas, credential protections, and source/config/script identity checks are unchanged. `scripts/release-common.sh`, `scripts/release-data.py`, and the external-command fixture port remain byte-identical to the branch base.

Updated `VERSION`, README, and the configured notes path for 0.4.0, with new project-focused `docs/releases/0.4.0.md`. Removed no prior release notes and introduced no replacement package/version constant. The settings change only the notes path; image, origin, repository, login, platform list, and token-file setting remain unchanged. Removed only obsolete engine/example entries from `.dockerignore`; all secret/state exclusions, `.gitignore`, and the root Dockerfile remain intact.

README and five active guides now describe the supported Bash/helper workflow, current tests, prerequisites, historical-pin refusal, and local verification limits. Image usage and administrator-owned platform preparation remain, without deleted fixture/cleanup/linking instructions. Active links/TOCs are checked separately from historical references in old notes and archived tasks. Current publication/configuration docs and README explicitly identify the unresolved N1/N2 boundaries.

## Coverage Retirement And Migration

The baseline had 322 methods. Retained all 65 Bash methods and their behavior claims, with one intentional rename from `test_old_options_point_to_explicit_legacy_entry` to `test_old_options_refuse_with_supported_usage`. Expanded the existing marker test to include the old managed-code directory and current diagnostics. Added ten methods: two interface footprint/version checks, five owned-Git/publication checks, and three helper transport checks. The current inventory is 75 methods in one test module, not 322 retained methods. No legacy capability coverage is claimed after retirement.

The following maps all 257 retired methods to current protection, required migration, or explicitly removed capability:

- `test_adapters.py` (21): pagination, source/remotes, advertised platforms, committed snapshots, private auth, and connection preservation remain covered by existing Bash cases. Added current-helper same-origin Bearer challenge/token/retry and status/parser/digest/refusal checks. Nested image/attestation graph traversal, retention ownership, and package routes belong to the removed protocol, not the supported two-member index contract.
- `test_cli.py` (16): current help/validation/unsupported options, preflight, ambiguous-state and changed-source refusals remain in Bash tests. Old publish/resume/cleanup modes, local finalization, link windows, and durable old-pin checkpoint CLI handling are retired; current old-state rejection remains.
- `test_core.py` (9): current strict versions/paths/configuration, token privacy/symlinks, alias checks, and input rejection remain covered. The new root-version/settings/README/notes check replaces module-version agreement. Old durable schema/state helpers are retired.
- `test_evidence_time.py` (9): evidence freshness and deletion authority are retired with remote cleanup; current publication does not consume those attestations.
- `test_gitea_absence.py` (19): current null/malformed/HTTP inventory refusals, response-loss publication reconciliation, and no-later-write checks remain. Added direct allowed-404 versus HTTP/auth/parser/digest failure checks, including rejection of a null image index. Abandonment and post-delete reconciliation are retired.
- `test_gitea_migration.py` (24): schema-2 migration, package/server-version gates, old environment aliases, and deletion contracts are retired. Current strict settings/credentials and notes-only payload/body checks remain in Bash cases; added standalone-helper HTTP/Bearer cases without reintroducing old transport code.
- `test_local_images.py` (25): local ownership journals, daemon/store inventories, guarded removal, and no-prune cleanup are retired. The current command performs no local-image removal; connection/private-auth tests remain.
- `test_package_linking.py` (23): owner-scoped linking, operator-window snapshots/expiry, and link-retry journals are retired. No replacement linking framework or new package POST is added.
- `test_publication_notes.py` (32): existing Bash tests retain exact source/notes binding, completed retry, local-tag/body conflicts, source drift, confirmed-tag loss, response-loss reconciliation, and historical blob independence. Added real local Git tests for literal filenames, narrow normalization, invalid UTF-8/NUL/size/content, deterministic canonical annotation roundtrip, conflicting identity, and local-tag refusal. Old schema-2 multi-image metadata, pending-journal recovery, and pruning-based legacy transaction recovery are retired.
- `test_retirement.py` (28): old graph schedules, protected survivors, removal ordering, and checkpointed deletion reconciliation are retired with retention, not replaced by unsafe deletion code.
- `test_ubuntu_hello.py` (5): the old runtime hook and owned pull/removal journal are retired with examples. Root Dockerfile remains unchanged; image/platform guides retain separately approved consumption/preparation instructions, not a claim of current runtime tests.
- `test_update.py` (12): managed installation, bootstrap inventories, destination update recovery, and installed launchers are retired. Current checkout locks and old-install marker/symlink rejection remain tested.
- `test_workflow.py` (34): current one-build/digest-promotion/notes-only publication, staging reuse, completed no-write retry, lost-response reconciliation, source/tag/inventory/alias conflicts, and preflight are covered by retained Bash tests. Source pushing, hooks/suites, automatic cleanup, abandonment, and durable old-engine recovery are retired.

New tests execute current production code through real Bash/local Git or the existing standalone-helper import/capture seams. They do not copy the retired engine into fixtures. The three helper transport methods inject captured status/header/body evidence into the real `http`/`registry` logic; they are not real HTTPS handshakes. Existing bounded-receiving tests retain the subprocess/pipe boundary independently.

## Verification

- **Baseline:** `python3 -B -m unittest discover -s tests -q` passed all 322 tests in 263.387 seconds before implementation edits.
- **Failing before removal/diagnostic changes:** A four-method focused run selecting supported usage, footprint, early unsupported-option refusal, and the expanded old-marker test failed as expected in 0.105 seconds. Failures identified the existing directories/imports and stale launcher pointers, not setup errors. Subtests produced 13 failure records across the four selected methods.
- **Migrated behavior before removal:** Six focused notes/annotation/registry methods passed against the unchanged standalone helper in 0.383 seconds, establishing characterization rather than changing production behavior to satisfy them.
- **Focused after removal:** Fourteen interface/marker/symlink/notes/annotation/registry methods passed in 1.918 seconds, including missing-token early refusal and zero subsequent fake publication writes.
- **Full retained suite:** `python3 -B -m unittest discover -s tests -q` passed all 75 tests in 218.444 seconds, with no skips. Static AST comparison confirms all 65 original Bash methods are represented after the single intentional rename, plus ten new methods. The 257 old-engine methods were explicitly retired, not counted as passing or retained.
- **Static/local checks:** Remaining Python AST syntax and individual shell syntax passed. Strict settings/root-version/README/notes checks passed; config differences are limited to the notes path. Active README/docs/new-notes TOC, file links, and cross-file fragments passed. Root validation passed with a nonexistent token override; dependency-free help passed with an empty environment and `PATH=/nonexistent`. These calls left the existing checkout lock unchanged. Exact 52-file removal-scope, directory-absence, active-import, implementation-report TOC, and `git diff --check` checks passed. ShellCheck is unavailable and was not installed or run.
- **Preservation checks:** Archived tasks, every preexisting release note, dashboard history, task 14 goal/plan/review, root Dockerfile, `.gitignore`, publication guard/helper, and fake command port match the branch base byte-for-byte. Active scripts contain no retired import/command/version dependency. Remaining test references to removed paths are negative footprint/diagnostic assertions, not imports or executable legacy instructions.

## Compatibility And Unresolved Warnings

Version 0.4.0 deliberately retires current-tree legacy support. Historical transactions remain bound to their preserved original checkout/pin; unchanged schemas or a new version do not grant adoption, migration, rollback, repair, or deletion authority. Configuration schema 1 and `container-release-bash/1` fields/canonical serialization remain unchanged, but source/version/config/script hashes represent a distinct identity.

N1 and N2 from the archived task 13 review remain unresolved: a post-promotion guard still accepts the captured predecessor alias before release creation, and auth isolation can lose config-local Buildx executable discovery. Their code boundaries were not changed. Local test success is not a claim of publication readiness, native plugin/daemon/TLS behavior, live 0.4.0 publication, runtime emulation, deployed server/storage semantics, deletion safety, or power-loss durability. Operational writer exclusion and separately approved live verification remain necessary.

## Preserved Resources

No real credentials, Docker config/TLS keys, production services/images/packages, published tags/bodies, original pinned checkouts/checkpoints, foreign projects, or `todo.md` were accessed or modified. Git pushes/ref/object operations in tests targeted only newly owned local fixture repositories. Test token/TLS/auth files are disposable placeholders; Docker/curl publication ports are fake. No live command, privileged setup, package reassignment, remote/local image deletion, broad Git pruning, or source push was run. Archived evidence remains historical, even when it mentions retired paths; it was not rewritten to resemble current support or verification.
