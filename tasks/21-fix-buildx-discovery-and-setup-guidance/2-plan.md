# plan

- [plan](#plan)
  - [Scope](#scope)
  - [Implementation Plan](#implementation-plan)
    - [Summary](#summary)
    - [1. Preserve Docker plugin discovery during auth isolation](#1-preserve-docker-plugin-discovery-during-auth-isolation)
    - [2. Report early setup failures safely](#2-report-early-setup-failures-safely)
    - [3. Remove the harness-only test prerequisite](#3-remove-the-harness-only-test-prerequisite)
    - [4. Add focused regressions and baseline checks](#4-add-focused-regressions-and-baseline-checks)
    - [5. Update documentation and prepared version](#5-update-documentation-and-prepared-version)
    - [6. Verify and record implementation](#6-verify-and-record-implementation)
  - [Acceptance Criteria](#acceptance-criteria)
  - [Risks and Decisions](#risks-and-decisions)

## Scope

Implement the updated `1-goal.md`: fix F3, F4, and F5 from `tasks/_archives/19-code-review/code-review.md`. Retain task 20's destination and confirmed-promotion protections. Changes are limited to Docker plugin discovery, early setup diagnostics, portable test temporary storage, focused fixtures/tests, and relevant current documentation/version metadata. No implementation code is changed during this planning stage.

## Implementation Plan

### Summary

Preserve the original Docker plugin search order independently of private registry authentication. Give actionable, fixed-text guidance before the normal shell traps exist, including the Python lock bootstrap that replaces the shell. Use the same optional temporary-parent selection for publication and Bearer tests so `/tmp/opencode` is not a prerequisite.

### 1. Preserve Docker plugin discovery during auth isolation

- Extend private Docker configuration preparation in `scripts/release-data.py`, called by `auth()` while the original `DOCKER_CONFIG` is still active. Resolve the original config directory from a nonempty `DOCKER_CONFIG` or `$HOME/.docker`, relative to the caller's original working directory, not the project root.
- Read the original `config.json` through the existing bounded JSON helpers, using `CONFIG_LIMIT`. Treat an absent file as an empty configuration. Reject unreadable, oversized, malformed, duplicate-key, or non-object configuration without relaying its contents or paths. Extract only `cliPluginsExtraDirs`; validate a list of nonempty, control-free path strings. An absent or JSON-null field means no extra directories, matching Docker's empty slice behavior; wrong types are refused.
- Construct an ordered absolute list containing the original configured extra directories, followed by the original config directory's `cli-plugins`. Resolve relative entries lexically against the caller's working directory; do not expand arbitrary shell syntax, change directory, or reinterpret them relative to `DOCKER_CONFIG`. Preserve order and symlink-based installations rather than copying plugin binaries or flattening directories.
- Add that list as `cliPluginsExtraDirs` to the existing minimal private Docker `config.json`. Retain only the target's minimal `auths` entry plus this explicit discovery field; do not copy original auths, `credsStore`, `credHelpers`, proxy settings, aliases, or unrelated configuration. Leave the private `cli-plugins` directory absent so it cannot introduce a new candidate.
- Preserve the original extra-directory and config-local precedence; Docker's native system plugin directories remain the fallback. This keeps a config-local Buildx ahead of a system alternative and preserves an extra-directory override ahead of config-local Buildx. A default/system-only installation still works without copying system directories or probing the daemon for plugin metadata.
- Retain current host/context/TLS handling, context metadata copying, `BUILDX_CONFIG`, explicit builder selection, bounded command capture, and secret suppression. Do not install plugins, fall back silently to another builder, or treat preserved builder-state strings as proof of preserved executable selection.
- Contract evidence read during planning: Docker CLI v29.0.0 [plugin manager](https://github.com/docker/cli/blob/v29.0.0/cli-plugins/manager/manager.go) and [configuration structure](https://github.com/docker/cli/blob/v29.0.0/cli/config/configfile/file.go). The actual `getPluginDirs` implementation orders extra directories before config-local and system directories; use the code rather than the inconsistent ordering comment. These source checks do not certify a deployed Docker binary.

### 2. Report early setup failures safely

- In `scripts/release.sh`, initialize the no-publication diagnostic state and explicit setup phase before inherited-lock checking and temporary-directory creation. Add phase-specific advice in `scripts/release-common.sh` for checkout locking/verification and temporary storage.
- Check `data lock-check` explicitly and route refusal through fixed guidance to inspect or wait for the active lock owner and verify checkout filesystem support. Do not delete, recreate, bypass, or steal a held lock. Preserve inode/device checks, `O_NOFOLLOW`, nonblocking `flock`, and inherited descriptor validation.
- Check `mktemp` creation explicitly before installing cleanup traps. Suppress raw `mktemp` stderr and give a fixed message advising a valid writable temporary parent, sufficient space, and permissions. Do not echo `TMPDIR`, token paths, or arbitrary OS exception text. Do not silently replace an invalid caller-selected `TMPDIR` with another directory.
- Install owned-directory cleanup and existing ERR/INT/TERM handling immediately after successful creation. Cleanup must tolerate the setup state without deleting an uninitialized or caller-owned path. Preserve umask 077, nonzero refusal, lock release, signal forwarding, and no-remote-effects behavior for `--validate`/`--help`.
- Handle lock bootstrap errors inside Python's `locked` action; moving a shell trap before `exec` cannot handle errors after replacement. Add a small setup-specific reporting path carrying fixed phase/message/advice fields, with a dedicated exception or equivalent local reporter. Cover lock-file open/acquisition and locked-child startup failures; close an acquired descriptor on every failure and preserve normal child exit/signal behavior.
- The Python setup reporter and shell setup guards must emit a recognizable setup phase, `Next:` advice, and the existing no-publication-writes statement without raw exception details or duplicate success claims. Keep general data-helper failures and post-write uncertainty reporting unchanged. Distinguish lock contention advice from storage/setup access advice where the failure is known.

### 3. Remove the harness-only test prerequisite

- In `tests/test_bash_release.py`, introduce a small test-only temporary-directory factory or parent selector shared by `BashPublicationTests.setUp()` and `BashDataTests.test_same_origin_bearer_challenge_retries_with_private_token`.
- Prefer the approved `/tmp/opencode` parent only when it exists; otherwise use Python's standard temporary parent. Preserve owned private directories, cleanup, and the existing synthetic-token/file assertions. Do not create a global parent, require elevated permissions, or weaken Bearer assertions.
- Keep generic portable temporary-directory uses unchanged unless sharing the helper improves the directly affected setup. This is test infrastructure only; production's explicit `TMPDIR` refusal in F4 remains a separate contract.

### 4. Add focused regressions and baseline checks

- Extend `tests/fixtures/bash_release_ports.py` with an opt-in plugin-discovery model using the actual active config's ordered extra directories, config-local path, then owned synthetic system directories. Create distinct executable fixture markers for candidate Buildx installations and log the selected absolute path/identity for each Buildx operation. Do not call real Docker or enumerate the host's actual plugin locations.
- Cover config-local-only Buildx, config-local versus system shadowing, ordered extra directories versus config-local/system candidates, system-only fallback, missing original config, unset/empty `DOCKER_CONFIG`, relative config/extra paths, paths containing spaces, and symlink-installed plugins. Require the same candidate at preflight, build, and promotion. Check that login does not remove `cliPluginsExtraDirs`; retain context/host/TLS/builder-state assertions.
- Add helper boundary cases for malformed, oversized, unreadable, wrong-shaped configuration and invalid extra-directory fields. Require safe refusal before any publication write and no raw original auth, config contents, or path leakage. Verify unrelated auth/helper sentinels never enter the minimal private config or command output.
- Extend the existing held-lock and lock-symlink cases; add invalid inherited-descriptor/identity checks and missing/unusable temporary-parent cases. Assert the intended failure is reached, nonzero exit, setup phase, useful `Next:` advice, no publication writes or success summary, no secret/path leakage, preserved lock/target contents, and safe cleanup. Use controlled errors for permission/full-storage conditions rather than privileged host changes.
- Cover Python lock-open/acquisition and child-start reporting with narrow injected failures, including descriptor closure after failure. Retain the existing full-entry signal/cleanup test and verify a subsequent invocation can acquire the lock after setup refusal. No test should recommend lock deletion or rely on arbitrary sleeps for ownership.
- For F5, simulate both preferred-parent presence and absence without renaming or deleting the real `/tmp/opencode`. Run the actual Bearer test and publication setup under the absent-parent simulation, with a guard that rejects accidental creation beneath that missing parent. Isolate and restore `TMPDIR` and Python's cached temporary parent, supplying an owned writable fallback so the simulation does not accidentally select the harness path again. Require the Bearer flow's existing request/header/private-file assertions to execute successfully, not merely a successful parent-selection return value.
- Replay three primary regressions against copied pre-fix scripts or test setup from the implementation base: config-local plugin loss/selection change, held-lock or invalid-parent missing guidance, and unconditional Bearer temporary-parent failure. Require the expected behavioral assertion failures or the known F5 `FileNotFoundError`, not unrelated setup errors. Keep all baseline copies and mutations inside owned temporary fixtures.

### 5. Update documentation and prepared version

- During implementation, prepare patch version `0.6.3`: update root `VERSION`, README version/release-note link, `scripts/release.json` notes path, and add `docs/releases/0.6.3.md`. Preserve all configured target/login/token/platform settings and old release notes.
- Update relevant parts of `docs/bash-configuration.md`, `docs/bash-publication.md`, `docs/release-process.md`, `docs/verification.md`, and current-version references in `docs/image-usage.md`. Explain preserved plugin search precedence, relative-path semantics, safe setup diagnostics, portable test setup, and the distinction between model-based checks and native Docker certification.
- Remove current unresolved-F3/F4/F5 claims only after their regressions pass. Keep writer exclusion, unchanged checkout/tool configuration through publication, historical checkout/pin rules, no repair/rollback, and lack of live certification explicit. Do not edit archived findings to erase their history or imply all possible publication defects have been eliminated.
- Add/update TOCs and links for every new/changed Markdown heading. Keep README short and detailed behavior in dedicated docs.

### 6. Verify and record implementation

- Run new focused F3/F4/F5 cases first, then `python3 -B -m unittest discover -s tests -v`. The current suite contains 131 tests; its latest implementation run passed in 882.564 seconds. Allow enough time and record actual counts/runtime rather than claiming the prior result as current verification.
- Run `for script in scripts/*.sh; do bash -n "$script" || exit; done`, Python AST parsing, `./scripts/release.sh --validate`, and `git diff --check`. Verify active Markdown links/anchors/TOCs and version/README/configured-notes agreement.
- Rerun existing F1/F2 regressions, source/tag identity, staging reuse/completed retries, lost responses, credential isolation, Docker connection matrix, and signal cleanup through the full suite. No privileged installation, real Docker invocation, image pull, production credential access, no-argument root publication, or live resource mutation is authorized.
- Record changes, focused/full/baseline results, remaining limitations, and local-only verification boundaries in `4-implemented.md`; commit through the implementation workflow on a new branch exactly matching this task directory.

## Acceptance Criteria

- Auth isolation preserves the original effective Buildx discovery order across preflight/build/promotion, including config-local, extra-directory, relative/symlink, shadowing, and system-only cases, without inheriting unrelated auth/helpers.
- Invalid discovery configuration refuses safely before publication. Endpoint/context/TLS/builder-state behavior and private credential cleanup remain intact.
- Known early lock, inherited-lock, temporary-storage, and bootstrap-start failures return nonzero with fixed setup phase, actionable advice, and no-publication guidance. They leak no raw paths/secrets and neither bypass nor damage locks.
- The affected tests run with and without a pre-created `/tmp/opencode`, and the absent-parent scenario reaches the real Bearer assertions. No global directory is removed or provisioned by tests.
- All focused tests, baseline sensitivity checks, the full suite, syntax/local-validation checks, documentation checks, and diff checks pass. F1/F2 protections remain covered.
- Prepared metadata agrees on 0.6.3. Historical evidence and `todo.md` remain unchanged. No live-release or native Docker certification is claimed.

## Risks and Decisions

- Preserve search directories rather than copy executables or manually reimplement Docker's plugin metadata protocol. This retains native candidate validation and precedence while isolating authentication. Keep plugin files/configuration stable through the invocation; this is not executable pinning against concurrent filesystem replacement.
- Adding original config-local discovery as the final explicit extra directory preserves its position before system fallback. Do not prepend it ahead of existing configured overrides or import the original config wholesale.
- Bounded strict parsing may refuse malformed or oversized Docker configs that the CLI previously warned about or partially tolerated. Refusal is preferable to silently selecting a different plugin; use fixed diagnostics and document the boundary.
- Early diagnostics span Python bootstrap and Bash child processes. Preserve descriptor lifetime and child exit status; do not rely on shell traps after `exec` or broad exception handling that masks publication errors.
- F5's optional test parent is independent of production `TMPDIR`: portable tests may choose the standard parent, while production must report an invalid explicitly selected parent rather than silently changing it.
- Script hashes will change, so new scripts cannot adopt old publications. No schema/annotation change, package-version gate expansion, automatic host setup, repair machinery, or publication-policy redesign is required.
