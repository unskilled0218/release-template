# Plan

- [Plan](#plan)
  - [Scope](#scope)
  - [Implementation Plan](#implementation-plan)
    - [1. Establish the baseline and classify coverage](#1-establish-the-baseline-and-classify-coverage)
    - [2. Remove unsupported tooling without weakening refusal boundaries](#2-remove-unsupported-tooling-without-weakening-refusal-boundaries)
    - [3. Retain and adapt current-workflow tests](#3-retain-and-adapt-current-workflow-tests)
    - [4. Simplify active documentation](#4-simplify-active-documentation)
    - [5. Prepare the version and release notes](#5-prepare-the-version-and-release-notes)
    - [6. Verify and record implementation](#6-verify-and-record-implementation)
  - [Acceptance Criteria](#acceptance-criteria)
  - [Risks And Decisions](#risks-and-decisions)

## Scope

Remove legacy Python release support from the current source tree, following `1-goal.md` and `~/workdir/command.md`. Delete the old engine, examples, managed installer/launcher, and legacy-only tests/documentation. Keep the supported single-command Bash workflow, standalone Python standard-library data helper, root Dockerfile, explicit settings, and root `VERSION` as the sole project version source.

This is a deliberate removal of supported tooling, not a migration of existing installations or transactions. Prepare version 0.4.0 during implementation to distinguish this removal from the prepared 0.3.1 patch. Preserve archived tasks, historical release notes, dashboard history, published resources, and original pinned checkouts/checkpoints. N1 and N2 in `tasks/_archives/13-fix-bash-release-review-warnings/5-code-review.md` remain separate unresolved work: post-promotion alias reversion can still precede release POST, and private auth can lose config-local Buildx plugin discovery. Do not fix or claim closure of either warning in this task.

This stage writes only this plan and commits it. Future implementation is local code/test/documentation work only: no real credential/config/TLS-key access, live publication, real Docker daemon operations, source or tag pushes to production, remote deletion, package reassignment, old-pin adoption, privileged setup, foreign-project changes, or `todo.md` changes.

## Implementation Plan

### 1. Establish the baseline and classify coverage

- When implementation is requested, create a new branch named exactly `14-remove-legacy-release-support` through the implement workflow. Inspect status before editing and preserve unrelated user work.
- Run `python3 -B -m unittest discover -s tests -q` before deletion with sufficient time for the current suite, approximately five minutes. The preceding review passed 322 tests; that is historical evidence, not a substitute for this baseline. Inventory the current 65 Bash methods so their retention can be checked after cleanup.
- Classify the remaining 257 methods by supported behavior, not solely by filename or historical origin. The 13 other test modules import the old engine or exercise old hooks/installers. Record which behaviors are already protected by the Bash family, which useful supported behaviors need migration, and which concern retired capabilities only.
- Preserve current coverage for immutable tag/notes/source binding, literal historical blob reads, exact platform/label evidence, checked read failures, confirmed-tag lifecycle, completed no-write retries, response-loss reconciliation, staging reuse, bounded inputs/inventories/subprocesses, private auth, Docker connection selection, locks/signals, and refusal of unsafe source/credentials/old state.

### 2. Remove unsupported tooling without weakening refusal boundaries

- Remove tracked files under `release_template/` and `examples/`, plus `scripts/legacy-release.sh`, `scripts/launch.py`, and `scripts/update.py`. Remove only tracked project assets within this scope; do not recursively erase local checkpoints, ignored state, preserved checkouts, or unrelated untracked files. Stop and investigate any unexpected user-owned contents before removing a directory.
- Retain `scripts/release.sh`, `scripts/release-common.sh`, `scripts/release-data.py`, `scripts/release.json`, root `Dockerfile`, and the active source-snapshot/build behavior. Python 3.11+ standard library remains a runtime dependency; this is not a Python-free rewrite.
- Replace the unsupported-argument pointer in `scripts/release.sh` with a bounded usage message describing only the supported no-argument, `--validate`, and `--help` interface. Unknown/old options must still exit nonzero before credentials or external effects, rather than being silently reinterpreted.
- Keep rejection of `release-template.lock.json`, `scripts/release-template`, `.template-transaction`, and same-version `.release-template/<tag>.json`, including existing symlink checks. Change only the misleading instruction to use the now-deleted local legacy wrapper: direct users to the preserved original checkout/pin and refuse migration or repair. Retain `.template-operation.lock` and the existing old-state ignore rules; a guard naming an unsupported marker is not a runtime dependency on the removed implementation.
- Keep Bash settings schema 1, `container-release-bash/1` fields/canonical serialization, credential protections, source/config/script freshness, resource budgets, immutable intended identity, conservative startup classification, and mutation ordering unchanged. In particular, do not use cleanup as a reason to alter alias guards or plugin discovery for N1/N2.
- Remove active imports/version checks tied to `release_template.__version__`; do not create a replacement package or duplicate version constant. Root `VERSION` continues to drive the configured tag and release notes contract.

### 3. Retain and adapt current-workflow tests

- Keep `tests/test_bash_release.py`, `tests/fixtures/bash_release_ports.py`, and `tests/__init__.py`. Retain all 65 existing Bash methods and behavior claims; rename/adapt the obsolete legacy-entry-pointer test to assert unsupported-option refusal and useful current usage instead. Strengthen that scenario in an owned publication fixture so missing credentials and zero fake-command events prove refusal happens early.
- Retain old-install/checkpoint refusal coverage rather than deleting it with the engine. Cover all supported markers, including `scripts/release-template`, and assert no build/tag/promotion/release writes. Check that diagnostics no longer point to a deleted local script. Keep original source-main and symlink refusal cases.
- Before removing `tests/test_adapters.py` and `tests/test_publication_notes.py`, map their overlapping useful cases to retained Bash tests. Add focused standard-library-helper or owned Bash-fixture tests for still-supported behavior not already covered: successful same-origin Bearer challenge/token/retry, allowed 404 absence versus HTTP/auth/parser/digest failure, literal committed-note validation and narrow newline normalization, and deterministic annotation creation/inspection with conflicting identity refusal. Use existing coverage where it already establishes a case; do not duplicate entire old protocol suites.
- Exercise current production code in migrated tests, importing the standalone helper through the existing `helper_module()` seam or running the Bash entry. Do not copy the removed engine into fixtures or rewrite its assertions to accept a weaker safety rule. Use private disposable tokens, synthetic Docker/context files, fake curl/Docker, and owned local Git/bare-remotes. Shared test utilities must not depend on the removed package.
- Remove legacy-only modules after the coverage mapping: `test_adapters.py`, `test_cli.py`, `test_core.py`, `test_evidence_time.py`, `test_gitea_absence.py`, `test_gitea_migration.py`, `test_local_images.py`, `test_package_linking.py`, `test_publication_notes.py`, `test_retirement.py`, `test_ubuntu_hello.py`, `test_update.py`, and `test_workflow.py`. Remove `tests/support.py` once its old-engine consumers are gone; move any necessary generic test utility into the retained tests without importing legacy policy.
- Add a small regression check for the supported footprint: removed packages/examples/launchers are absent, remaining executable Python/tests have no imports from the removed package, and root `VERSION`, README, configured notes path, and notes heading agree without loading module metadata. Do not ban historical text or safety-marker names globally.
- Report the final retained/new test count and the explicit retirement of legacy-only tests. A lower count is expected; it must not be described as retaining all 322 tests or as unchanged coverage of removed capabilities.

### 4. Simplify active documentation

- Keep README concise and update its version, supported entry point, root-version convention, and prerequisites. Remove the current link advertising a legacy workflow in this checkout. State briefly that historical transactions require their original preserved checkout/pin; do not offer a current wrapper or managed upgrade path.
- Retain and update `docs/bash-configuration.md`, `docs/bash-publication.md`, and `docs/verification.md` for the actual supported files, supported options, old-state refusal, standalone-helper prerequisites, local test commands, and honest verification limits. Remove legacy validation/example commands, deleted test-file references, claims that retired tests still run, and instructions for removed hooks/installer/cleanup capabilities. Keep old live results explicitly historical, with references to existing archived task evidence if needed; do not rewrite history as verification of 0.4.0.
- Remove the legacy-only active pages `docs/configuration.md`, `docs/credentials.md`, `docs/gitea-migration.md`, `docs/installation.md`, `docs/legacy-release.md`, `docs/local-images.md`, `docs/package-linking.md`, `docs/publication.md`, `docs/retention.md`, and `docs/ubuntu-release-test.md`. Their original content remains available in Git history and preserved pins; do not duplicate a legacy manual into a new active guide.
- Retain `docs/image-usage.md` and `docs/platform-preparation.md` because image consumption and platform prerequisites still apply. Remove old fixture/local-finalization/retention/linking instructions and links to deleted pages. Explain only current behavior, immutable references, administrator-owned optional emulation preparation, and separate live-verification approval. Do not execute any documented privileged/runtime commands.
- Preserve every existing file under `docs/releases/` and `tasks/_archives/` byte-for-byte, plus `.brooks-lint-history.json`. Historical command/path mentions are intentional evidence, not active dependencies to rewrite. Scope link checks to README and active nonhistorical docs; explicitly record that historical records can refer to retired files. Require TOCs for every header in new/updated active Markdown.
- Remove obsolete `release_template`/`examples` entries from `.dockerignore` if they no longer serve a current purpose. Keep all secret/state exclusions and do not change the root Dockerfile, image name, target repository, or build context semantics.

### 5. Prepare the version and release notes

- During implementation, update root `VERSION` from 0.3.1 to 0.4.0 without introducing another authoritative version file. Update README's prepared version and release-note link, add `docs/releases/0.4.0.md` beginning `# Release v0.4.0` with a matching TOC, and change only the `notes` path in `scripts/release.json` to that new file.
- Describe removal of the legacy engine, examples, managed tooling, and old CLI support in project-focused release notes. State that Bash still uses a Python standard-library helper, historical transactions stay on original pins, verification is local only, and the two previously recorded warnings remain unresolved. No migration, repair, deletion, deployment, or compatibility certification is implied.
- Keep old release notes and the existing `git.lan/dev/container-release-template-hello` image/`dev/container-release-template` target unchanged. A new source/version/config/script identity does not grant authority to adopt an old publication or alter its tag/body/checkpoint.

### 6. Verify and record implementation

- Run focused interface/old-marker and migrated-helper regressions, then the complete retained `python3 -B -m unittest discover -s tests -q` suite. Preserve the 65-method Bash baseline except intentional naming/assertion updates; add coverage without skips that conceal a failure. Do not invoke the old legacy entry or validate removed example configurations after deletion.
- Run `bash -n` individually for every remaining shell script and Python AST syntax checks for remaining scripts/tests. Run root `./scripts/release.sh --validate` with a nonexistent `GIT_TOKEN` override and dependency-free help with an empty environment and `PATH=/nonexistent`. These must not create publication state, read credentials, or contact services.
- Check root version/README/notes-path/notes-heading agreement, strict Bash settings, active Markdown TOCs/file links, and `git diff --check`. Use ShellCheck only if already installed; record absence without installing tools.
- Search active scripts/tests/README/nonhistorical docs for removed imports, commands, links, examples, and module-version dependencies. Distinguish permitted historical notices, old-state marker refusals, archived tasks, and old release notes from stale active instructions. Confirm no retained test imports `tests/support.py` or removed packages and no current command points to missing tooling.
- Compare archived tasks, all preexisting release notes, dashboard history, root Dockerfile, protected state/ignore rules, and image/target settings against the implementation branch base. Verify that only the explicitly allowed source/docs/test/version/notes changes occurred and no live resource or original checkout/pin was touched.
- Write `4-implemented.md` in this task directory with the exact removal list, coverage-retirement/migration map, retained/new counts, actual commands/results, version decision, historical preservation, unresolved N1/N2, and absence of live verification. Commit through the implement workflow when requested; do not push or merge implicitly.

## Acceptance Criteria

- `release_template/`, `examples/`, the three legacy scripts, legacy-only test/support files, and listed legacy-only active documentation are gone from the supported source tree. Remaining scripts/tests have no removed-package imports or executable/version dependencies; no active command/link points to a deleted file.
- `./scripts/release.sh` remains the sole public release entry, supports only no arguments/`--validate`/`--help`, and retains the standalone Python 3.11+ helper without jq or third-party packages. Unsupported arguments refuse early with current usage, not a pointer to a deleted legacy entry.
- Old installation/checkpoint marker and symlink refusals remain effective before publication writes. Existing transactions are neither adopted nor rewritten; original preserved pins/checkouts, published resources, historical notes, archived task records, dashboard history, and `todo.md` remain unchanged.
- All 65 current Bash behavior tests remain represented, with intentional legacy-pointer assertion/name updates, and useful supported legacy-test behaviors are retained or migrated with an explicit coverage map. The full retained suite passes; removed legacy-only capabilities are not falsely described as still tested.
- Root `VERSION` is the sole project version source. Prepared 0.4.0, README, configured notes path, and new notes heading agree. Settings/identity schemas, source/digest/notes invariants, resource limits, credentials, target/image, Dockerfile, and conservative retries remain unchanged apart from removal-facing diagnostics and version identity.
- Active documentation describes only the supported workflow, accurately separates historical evidence, and passes scoped TOC/link checks. Verification is local and credential-free. No live publication, Docker daemon operation, push, privileged setup, remote deletion, package reassignment, or foreign-project change occurs.
- N1 and N2 remain explicitly unresolved and separate from this removal. No alias-lifecycle or plugin-discovery fix is introduced or claimed as a cleanup side effect.

## Risks And Decisions

- Removing current-tree Python support is a compatibility break, so 0.4.0 is deliberate. Preserved immutable pins/history remain the only supported way to operate historical transactions; removing their current-tree tooling does not authorize checkpoint migration or source rollback.
- Retiring 257 old-engine test methods can hide loss of relevant protection if done by filename alone. The coverage map, retention of the 65 Bash methods, and targeted migration of current-helper scenarios are required; legacy-only cleanup/linking/journal/suite/installer behavior does not need a replacement framework.
- Historical references to removed paths will remain in immutable task/release evidence. A repository-wide zero-match rule would force destructive history edits or weakened marker checks. Audit active dependencies and current instructions separately from allowed historical and refusal-only references.
- Removing old-state guards or ignore patterns would make the smaller tree less safe. Keep those small defensive boundaries even though the corresponding engine is no longer shipped. Keep snapshot secret exclusions and lock behavior intact.
- Python remains necessary for strict JSON, bounded I/O, hashing, credentials, source export, and locks. Do not equate removing the Python engine/package with replacing the standalone helper or introducing shell JSON parsing.
- N1/N2 limit publication readiness independently of tree size. Local tests neither certify native Docker plugin/routing/TLS behavior nor authorize a live 0.4.0 experiment. Keep those warnings visible without extending this task into unrelated fixes.
