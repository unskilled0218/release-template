# Implementation

- [Implementation](#implementation)
  - [Changes](#changes)
  - [Safety adjustment](#safety-adjustment)
  - [Verification](#verification)
  - [Limits](#limits)

## Changes

- Created task branch `15-link-container-package` before implementation. Added strict package/repository identity checks, escaped scoped API routes, and separate `package-ensure` and read-only `package-check` helper actions using existing private credentials and bounded transport.
- Added a shared association stage after fresh and completed-publication verification. Publication is checked before linking and again afterward; final association verification is required before success. Correct links remain unchanged, observed conflicts fail, and completed retries can finish only the configured package's missing link without republishing or consulting staging.
- Link dispatch accepts the documented empty HTTP 201 response. A lost transport response permits one read-back, never an automatic duplicate POST. Failed prerequisites and input/resource/HTTP refusals stop without unlinking, deleting, or rolling back accepted publication or association state.
- Extended local service ports and tests for scoped package names distinct from repository names, untouched unrelated packages, correct/unlinked/conflicting/hidden associations, refreshed identity checks, failed and uncertain writes, post-link verification, conditional-shell failure propagation, and completed retries.
- Advanced `VERSION` to `0.5.0`, updated the configured release notes path and README, added versioned release notes, and updated configuration, publication, image usage, and verification documentation. No new dependency, credential source, configuration field, or CLI flag was introduced.

## Safety adjustment

Implementation-time inspection of Gitea v1.25.0 [`services/convert/package.go`](https://github.com/go-gitea/gitea/blob/v1.25.0/services/convert/package.go) showed that `repository: null` can also mean an existing association hidden by permissions. Null alone is therefore not proof that a package is unlinked, contrary to the plan's initial assumption. The v1.25.0 [`services/packages/package_update.go`](https://github.com/go-gitea/gitea/blob/v1.25.0/services/packages/package_update.go) refuses linking an already-linked package server-side.

To preserve the goal's no-reassignment requirement, new association writes require `GET /api/v1/version` to report a stable `1.25.x` version before refreshing target/package evidence and dispatching. Other version families, development versions, malformed responses, or failed version reads cannot authorize writes. Existing correct links stay read-only without a version check. A permission-hidden conflicting link is preserved when the supported server refuses the attempt. This conservative compatibility restriction and its tests/documentation are a justified safety refinement, not authorization to upgrade or contact the deployed server.

## Verification

- The earlier sequential discovery run passed 93 tests in 518.037 seconds before the final safety/test additions. Implementation commit `c746ecd` was made at the user's request while final verification was pending. The final complete suite subsequently passed all 99 tests in 194.0 seconds using four isolated subprocess workers with workspace-backed temporary directories. Worker results were 25, 25, 25, and 24 passing tests, with no failures or errors.
- The final data-helper subset passed all 28 tests before resuming implementation.
- Static comparison against the committed baseline confirms all 75 existing test methods remain, with 24 added methods and 99 total. Parallel verification uses `unittest.defaultTestLoader.discover("tests", top_level_dir=".")` and distributes every discovered test ID across four isolated `python3 -B -m unittest -v` subprocesses; no tests are skipped.
- `bash -n scripts/release.sh scripts/release-common.sh` passed.
- Python AST syntax checks passed for all four Python source/test files without writing bytecode.
- `./scripts/release.sh --validate` passed without credentials or remote operations.
- `git diff --check` passed.
- A local Markdown check validated 39 relative links and anchors across README and the five changed/new documentation files. No live external links were exercised by that check.
- The first temporary parallel-test launcher used unqualified module names and failed imports before running tests. Its discovery root was corrected to produce `tests.test_bash_release` module names; no production or test code change was needed for that launcher issue.
- The corrected `/tmp/opencode` run stalled in fixture cleanup: its remaining worker had no child commands and was blocked in kernel `wrap_directory_iterator`, with open directory descriptors for its owned temporary project. That invocation was stopped rather than reported as passing. Verification was restarted with a runner-only `tempfile.TemporaryDirectory` override to `/home/container/workdir`, which is backed by a separate ext4 mount rather than the container overlay filesystem. Test methods and product code were unchanged by this environmental accommodation; a six-minute worker timeout was added to the temporary launcher.

## Limits

No live publication, package mutation, deployed-server compatibility check, or Packages-tab UI verification was performed. Source-contract inspection and synthetic local tests do not certify account permissions, distributed exclusion, Docker routing/TLS/plugins, storage behavior, or power-loss durability.

Association is package-wide. Operator-enforced exclusion of other package/repository publication and association writers, including UI actions and requests still in flight, remains required through completion. The server's existing-link check is not an atomic compare-and-set. Supporting another server family requires reviewing its link refusal semantics, not relaxing the version gate blindly. Existing promotion and config-local Buildx-plugin warnings remain unchanged and explicitly documented.
