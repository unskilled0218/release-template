# Implementation results

- [Implementation results](#implementation-results)
  - [Outcome](#outcome)
  - [Changes](#changes)
  - [Regression evidence](#regression-evidence)
  - [Verification](#verification)
  - [Preserved boundaries and limits](#preserved-boundaries-and-limits)

## Outcome

Implemented the approved B1 repair on fresh branch `5-fix-gitea-null-response`. Template version is `0.2.1` in `VERSION`, `release_template.__version__`, and README. Successful null JSON no longer establishes Gitea lookup absence; only an explicitly allowed HTTP 404 returns `None`.

## Changes

- `Gitea.get()` now decodes successful JSON once, rejects decoded null for required and optional reads, and requires object-shaped successful optional lookups. Errors are fixed, bounded messages without remote response content. Existing HTTP status enforcement still rejects required 404 reads.
- Valid collection arrays, including empty pagination pages, remain supported. Shared OCI JSON decoding, release/package paths, header authentication, DELETE status handling, and caller identity/ownership checks are unchanged. Empty objects remain objects, not absence evidence.
- Added three loopback contract tests in `tests/test_gitea_migration.py`, five operation regressions in `tests/test_gitea_absence.py`, and one removal-aware post-delete recovery test in `tests/test_retirement.py`. The new operation fixture replaces only HTTP transport and returns status plus JSON bytes to production Gitea methods; it does not substitute high-level lookup return values for decoding.
- Updated README and retention/verification documentation to describe malformed lookup failure, uncertainty after an accepted DELETE, verified-404 retry, and the lack of automatic repair/adoption for older falsely completed checkpoints.

## Regression evidence

- Before the adapter change, the two negative contract tests and five operation tests failed with 24 assertion/subtest failures: successful null/non-object reads were accepted; listed/omitted packages, older release retirement, and abandoned-run processing accepted null as absence; publication actually POSTed a release before its later verification failed. A separate removal-aware regression also failed because null confirmation allowed cleanup to continue rather than stop. These expected failures established the defect through actual status/JSON decoding.
- After the adapter change, the focused migration/operation/new-retirement selection passed all 29 tests.
- Publication now stops at malformed current-release lookup without POST, release-operation completion, or a false published transition. Earlier legitimate preparation and durable intent remain. A later actual-404 retry publishes exactly once without rebuilding.
- A still-listed staging candidate remains pending in reopened durable state after malformed lookup, with zero DELETEs, successful publication retained, and its alias still listed/resolvable. An omitted saved candidate cannot acquire absence authority from null; checkpoint bytes and approved retirement metadata remain unchanged.
- Older-release malformed lookup stops before DELETE and leaves its saved candidate pending. Malformed abandoned-package lookup preserves the selected checkpoint bytes, abandonment flag, and staging alias.
- In the removal-aware case, one authorized parent DELETE really removes its registry content. Null confirmation leaves both candidate completions pending, stops before deleting the child, and retains successful publication. After reopening durable state, a consistent listing and actual-404 lookup confirm parent absence without a repeated parent DELETE or fetching its retired graph; child retirement then completes under the unchanged approval fingerprint/order.
- Paired positive controls preserve allowed 404 absence, required 404 failure, successful objects, valid empty collection pages, and existing 204/404 DELETE idempotence. Malformed string/array responses containing a fixture token do not leak it in diagnostics.

## Verification

- `TMPDIR=/tmp/opencode python3 -B -m unittest tests.test_adapters tests.test_gitea_migration tests.test_gitea_absence tests.test_workflow tests.test_retirement tests.test_cli`: 121 tests passed in 34.883 seconds.
- `TMPDIR=/tmp/opencode python3 -B -m unittest discover -s tests`: 141 tests passed in 38.833 seconds. All 132 baseline tests remain, with nine additional test methods.
- `bash -n scripts/release.sh` passed. Python AST syntax checks passed for engine, scripts, tests, and example hooks. Version consistency checks passed for `0.2.1`.
- All five examples passed credential-free validation through `scripts/launch.py`. Changed README/docs passed table-of-contents and local-link checks. `git diff --check` passed.
- Verified no diff in state/OCI/workflow/cleanup/configuration code, scripts/bootstrap/updater, archives, prior health history, task-4 records, or this task's goal/plan/review. Implementation changes are confined to the adapter guard, version declarations, scoped tests/docs, and this results file. Untracked `todo.md` remains untouched and excluded from the commit.

## Preserved boundaries and limits

Schema 2, `GIT_TOKEN`, `GIT_USERNAME`, `~/.config/git/token`, exact source/config/template checkpoint identity, publication metadata, nested retirement authority, and stable installation protocol remain unchanged. Tests exercise local loopback and injected HTTP transport, disposable state, fake Git/Docker operations, and the existing removal-aware registry fixture. No actual credentials were accessed, private deployment probed, real Docker login/build performed, consumer migrated, remote reconfigured, live release/package mutated, or source pushed. The implementation commit is local only.

This repair prevents future malformed-response absence decisions; it does not automatically identify or repair older falsely completed checkpoints or adopt old-pin state. Preserve provenance for separately reviewed recovery. Actual deployed Gitea version, permissions, linkage, and storage/deletion semantics remain unverified. Fresh authorized same-server, exact-version evidence is still required before live destructive cleanup.
