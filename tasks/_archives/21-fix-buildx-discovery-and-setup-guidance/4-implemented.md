# Implementation results

- [Implementation results](#implementation-results)
  - [Changes](#changes)
  - [Verification](#verification)
  - [Baseline replay](#baseline-replay)
  - [Compatibility and limits](#compatibility-and-limits)

## Changes

Implemented the updated F3–F5 goal and P1 plan revision on new branch `21-fix-buildx-discovery-and-setup-guidance`, based on `a51ba8b`. Prepared version 0.6.3 without changing configured repository/image/login/token/platform settings.

- **F3:** private Docker auth includes only the target auth entry and ordered `cliPluginsExtraDirs`: original extra directories, then original config-local plugins, followed by Docker's native system fallback. Relative paths become absolute against the caller's working directory without resolving away symlink installations. Original auths, credential helpers, proxies, aliases, and plugin binaries are not copied. Context/TLS/builder-state handling remains intact.
- **P1:** bounded original config parsing rejects non-object, malformed, duplicate-key, oversized, nonregular, unreadable, or invalid discovery data. Case-fold-equivalent noncanonical discovery keys are explicitly refused before canonical lookup; canonical null/absence means no extra directories. The fake original-config decoder independently recognizes aliases and input order, so tests prove that preflight selection is not silently discarded by the new extractor.
- **F4:** fixed setup phases and `Next:` advice cover Python lock open/acquisition/child-start failures and shell inherited-lock/temporary-storage failures before ordinary traps exist. Raw `mktemp` stderr is suppressed. Lock descriptors close on failure; no lock is deleted/bypassed. Existing child status, descriptor inheritance, signal forwarding, private cleanup, and post-write uncertainty semantics are retained.
- **F5:** publication and Bearer tests share an owned temporary-directory factory that optionally prefers an existing `/tmp/opencode` and otherwise uses Python's standard parent. Controlled presence/absence cases run the actual Bearer assertions and publication setup with isolated environment/cache state, without creating or removing a global parent.
- **Documentation:** updated README and relevant configuration/publication/process/verification/image docs, root version, configured notes path, and new `docs/releases/0.6.3.md`. Historical notes, task evidence, goal, plan, and plan review are unchanged.

## Verification

- All 12 focused tests passed in 105.834 seconds, including 11 new tests and the strengthened existing lock-refusal test. Plugin publication exercises 11 independent installation/configuration variants; case-spelling tests cover aliases, both duplicate orders, equal/conflicting/null values, and Unicode case folding.
- `python3 -B -m unittest discover -s tests -v` passed all 142 tests in 1015.850 seconds: 5 interface/tree/version checks, 102 publication-flow cases, and 35 helper cases, retaining all 131 previous tests and the F1/F2 regressions.
- Both shell scripts passed `bash -n`; current Python files passed AST parsing. Local `./scripts/release.sh --validate` and `git diff --check` passed. Active README/docs/current release notes passed file-link, heading-anchor, and TOC checks. Version metadata agrees on 0.6.3 and other release settings match the base.
- Helper cases exercise exact/over-limit configuration, invalid shapes and field spellings, injected unreadable config, nonregular input, lock-open/acquisition/child-start failures, descriptor release, and child status/inheritance. Full-entry cases cover lock symlinks/contention, inherited descriptor/identity refusal, invalid temporary parents, and hostile temporary-creation stderr suppression with zero publication events.
- An independent follow-up probe confirmed that, after temporary setup refusal, restoring a valid parent lets a new invocation acquire the lock and reach a deliberately refused builder preflight with zero publication writes.
- Tests and probes used only owned repositories, synthetic plugin candidates/configuration, fake Docker/curl ports, and disposable tokens. No real Docker invocation, production credentials/config/TLS keys, privileged setup, image pull, live publication, rollback, or unrelated project mutation occurred. No tools were installed.

## Baseline replay

Replayed the original failures using copied scripts or the original Bearer test body from `a51ba8b` inside owned temporary fixtures:

- **F3:** the original scripts passed config-local preflight and registry login, then the fake Docker port logged `plugin-discovery-missing` and exited 2 before publication writes. The current scripts completed the same scenario with exit 0 and no missing plugin. The copied port's new private-config-shape assertion was disabled for both runs so it could not mask the old executable-discovery failure; ordinary token/auth-isolation checks stayed enabled.
- **F4:** the original scripts refused a nonexistent temporary parent with exit 1, zero publication writes, and no `Next:` advice. The focused current-code cases provide phase-specific guidance without exposing the parent path and prove lock release.
- **F5:** the copied original Bearer test raised the expected `FileNotFoundError` under a controlled absent-preferred-parent simulation. The current actual Bearer test passed its existing request/header/private-file assertions under the same simulation and owned fallback. No real global directory was removed or renamed.

The replay distinguishes the intended original behaviors from unrelated setup errors. Baseline Git writes targeted only owned temporary bare repositories; tracked source and historical files were not replaced.

## Compatibility and limits

Only canonical `cliPluginsExtraDirs` is supported; Docker-valid alternate casing is a deliberate safe refusal. Original Docker config is bounded to 1 MiB and strictly parsed rather than reproducing every permissive Docker decoder behavior. The actual extra/config-local/system precedence is modeled from reviewed Docker CLI source; no deployed binary or native plugin metadata protocol is certified.

Search-order preservation is not binary pinning against concurrent replacement. Keep plugin files, tool/checkout configuration, and publication/package writers stable through completion. Explicit production `TMPDIR` failures remain refusals, independent of the test factory's optional preferred parent. F1/F2 guards, schema 1, annotation format, package-link version gates, and conservative retry/no-repair/no-rollback authority are unchanged. New script/config hashes require preserved original checkout/pins for old publications. No live 0.6.3 deployment, UI, runtime emulation, power-loss, or cross-service atomicity guarantee is claimed. `todo.md` is untouched.
