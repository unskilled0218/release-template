# Implementation

- [Implementation](#implementation)
  - [Outcome](#outcome)
  - [Changes](#changes)
  - [Plan Adjustments](#plan-adjustments)
  - [Verification](#verification)
  - [Compatibility And Limits](#compatibility-and-limits)
  - [Preserved Resources](#preserved-resources)

## Outcome

Implemented the simplified 0.3.0 release workflow on new branch `12-simplify-bash-release-template`, created from `de5bda6`. The default command is `./scripts/release.sh`: Bash coordinates one two-platform image, exact annotated tag, digest promotion, and a notes-only Gitea release. Root Dockerfile and explicit settings retain this project's existing Hello World image name. No release command was executed against production.

## Changes

- Added root `Dockerfile` and `.dockerignore`, `scripts/release.json`, `scripts/release-common.sh`, and standalone `scripts/release-data.py`. The default entry supports no arguments, `--validate`, and `--help`; explicit old CLI arguments point to `scripts/legacy-release.sh`. The new path imports no legacy engine and needs no jq, Node, or pip packages.
- Added strict configuration/UTF-8/JSON/duplicate-field handling, committed-note loading by exact regular Git blob, immutable version/source/destination checks, protected external token files, private curl/Docker auth with selected context/builder preservation, and a nonblocking no-follow destination lock. Source is already-pushed clean main; the command never pushes main or installs emulation.
- Added one committed-context multi-platform build into release-specific staging, immutable index/member/configuration-label verification, exact deterministic `container-release-bash/1` annotation, non-force tag push, same-digest latest promotion, Gitea release creation, and final independent identity/body/alias verification. Failed phases report incomplete/uncertain publication instead of claiming success or undoing accepted writes. The new path never invokes archive uploads, package-link POSTs, local-image removal, remote retention, or rollback.
- **P1:** Requested tag/release startup classification happens before staging. Matching completed publications verify their bound digest and final alias without looking up staging or rebuilding; tag-only/release-only states and missing/foreign completed content/aliases refuse without repair or predecessor refresh. Only the fresh branch may build. Lost accepted responses reconcile this running invocation's exact operations without duplicate confirmed writes.
- **P2:** Concurrent selector-based bounded capture limits stdout, stderr, HTTP body/header/status pipes, and stdin waits; overflow/timeout terminates and reaps the owned process group before returning a bounded error. API/OCI/ref/tag readers enforce their planned byte limits before parsing. Inventory scans share page/item/byte/time budgets, detect repeated/duplicate evidence, and require explicit terminal pages. Resource/input refusals cannot be swallowed as reconcilable transport failures or permission for later writes.
- Kept legacy source/launchers/examples/checkpoints intact. Added an explicit legacy wrapper and an updater guard that rejects new Bash source revisions before destination lock creation or managed writes. Installer tests freeze the original compatible wrapper rather than changing old bootstrap checksums to fit new code.
- Updated version files to 0.3.0, README, configuration/publication/credential/installation/verification guidance, and separate Bash/legacy documents. Added project-focused committed 0.3.0 notes. Task 11's convenience-wrapper objective is superseded by this broader task; its original goal is unchanged.

## Plan Adjustments

The first implementation attempt stopped because jq was absent. The user asked whether jq could be avoided, received the standard-library helper alternative, and then requested implementation. Updated task 12's plan on this implementation branch to record that alternative: Python 3.11+ handles strict data and bounded I/O rather than introducing a third-party dependency or parsing JSON in shell. Bash still owns the publication state machine, and `release_template/` is not imported. The helper also supplies flock, hashing, timeout/capture, and safe archive primitives instead of a FIFO/coreutils implementation. The earlier plan-review report remains historical and unchanged.

## Verification

- **Baseline:** Before implementation changes, `python3 -B -m unittest discover -s tests -q` passed 256 tests in 47.521 seconds.
- **Failing-before evidence:** Added three entry-point regressions before changing implementation. `python3 -B -m unittest tests.test_bash_release -q` failed all three: old help did not describe a no-argument release, `--validate` still required an explicit mode, and old-style publication did not direct users to a separate legacy entry. Those same interface checks pass in the new suite.
- **Incremental verification:** The first 18 Bash tests passed in 45.444 seconds; an expanded 34-test Bash run passed in 87.439 seconds. Full intermediate runs passed 291 tests in 135.425 seconds and 296 tests in 143.367 seconds. Direct bounded-data tests passed after adding concurrent stdin/deadline handling.
- **Final full suite:** After the final phase-reporting changes, `python3 -B -m unittest discover -s tests -q` passed all 297 tests in 143.506 seconds; an earlier full 297-test pass took 143.268 seconds. Static inventory confirms 40 new Bash entry/data tests and one additional installer refusal test, retaining the original 256 methods. No test was skipped to hide the default-interface change.
- **Local behavioral coverage:** Real Bash entry subprocesses use PATH-injected Docker/curl ports and exclusively owned local Git/bare-remotes. Tests exercise one-build/digest-promotion/notes-only publication, staging-independent completed retry, ambiguous startup refusal, response loss, unbound staging reuse, missing bound content/final aliases, identity/body/local-tag conflicts, source changes, wrong remotes/platforms/credentials, strict config, metadata mismatch, ignored-secret exclusion, safe archive refusal, predecessor drift, post-write overflow refusal, locks, and real signal cleanup.
- **Resource boundaries:** Data-helper tests exercise exact production byte limits and one-byte overflow, unending stdout/stderr, blocked stdin deadlines, descendant termination/reaping, strict JSON/version handling, OCI label/platform refusal, and explicit inventory counter/time/termination rules. Counter-limit tests substitute in-process constants only; there is no production environment override. Real CLI fixture output has no Content-Length requirement and still passes through bounded receiving pipes.
- **Static/local checks:** All Bash scripts passed `bash -n` individually. Python AST parsing, all six preserved legacy example validations, root/module version agreement, Markdown TOC anchors/link files, and `git diff --check` passed. Root `./scripts/release.sh --validate` and explicit legacy configuration validation passed with their no-credentials/no-remote-operations messages. ShellCheck is not installed and was not run or installed.
- **Unchanged safety/history:** Compared against `de5bda6`: legacy adapters/Git/linking/state/cleanup/local modules, `scripts/launch.py`, all examples, historical 0.2.4/0.2.5/0.2.6 notes, and archived tasks have no changes. Only Python module version metadata and the intentionally guarded updater change on the legacy side.

## Compatibility And Limits

This is a new default command/identity protocol, not an automatic managed upgrade. Python managed installs and checkpoints remain bound to their original immutable source/config/template pin. Changing `VERSION` or providing an explicit legacy wrapper does not allow an old publication to resume under this new revision. The preserved Ubuntu fixture's old notes path must not be published with a newer root version; use its captured original checkout for historical work.

The Bash workflow has no durable pre-build journal or power-loss guarantee. An explicit rerun may rebuild before any recoverable staging result exists. A newly started process refuses ambiguous tag-only/release-only states; operator inspection and separately reviewed recovery are needed, not blind repair. Matching completed identity requires the current final alias to match exactly and does not grant rollback/repromotion authority. A checkout lock and predecessor checks do not enforce server-wide exclusion or make cross-service requests atomic; one operator-controlled writer remains required.

No automatic consumer test hooks, suites, image export archives, attachment uploads, package reassignment, retention, local removal, or checkpoint migration are supplied. Advertised Buildx platforms are not proof of runtime emulation. Decoded-response budgets do not cap Docker's own build storage or arbitrary Git pack transfer. Normal signals clean private temporaries; SIGKILL can leave private run-owned directories requiring careful inspection. Local fake-port verification is not live server/storage/deletion certification.

## Preserved Resources

No real token file, production Gitea/registry endpoint, Docker daemon image, foreign project, captured live checkout/checkpoint, published tag/body, package association, or deletion attestation was accessed or changed. Home-web was a read-only design reference; none of its code or credentials was used at execution time. Git pushes, fetches, branch/ref changes, temporary symlink/file modifications, and signal injection in tests affected only newly created owned fixtures. No Git pruning was needed. `todo.md`, task 11, the task 12 goal/review, and historical evidence remain unchanged. Preparing 0.3.0 is not authorization for a live release.
