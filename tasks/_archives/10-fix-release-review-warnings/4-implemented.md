# Implementation

- [Implementation](#implementation)
  - [Scope And Outcome](#scope-and-outcome)
  - [Changes](#changes)
  - [Verification](#verification)
  - [Compatibility And Limits](#compatibility-and-limits)
  - [Preserved Resources](#preserved-resources)

## Scope And Outcome

Implemented B1–B3 from the approved task 10 plan on the new branch `10-fix-release-review-warnings`, created from `55546c1`. Prepared patch version `0.2.6`. All 256 local tests pass. No new live publication, real credential access, production probe, remote mutation, Docker daemon operation, or live resource cleanup was performed. This is an implementation result, not a live deployment or deletion-safety attestation.

## Changes

- **B1 — Dispatch-time package-link authority:** `release_template/linking.py` now separates bounded strict record loading, UTC interval validation, deployed-version validation, and active-window checks. Each mutation attempt reads one canonical authority snapshot, performs server/association I/O, records that same snapshot/digest in separate durable attempt evidence, and then performs a fresh pure time check immediately before POST. Expiry during lookup or persistence cannot borrow renewed on-disk authority. Matching links still reconcile without a window or duplicate POST; valid dispatches can be confirmed after expiry without rollback.
- **B2 — Exact annotated-object recovery:** `Workflow.tag_source` validates existing operation shape/ID/status and exact tag/commit/identity/object details, then invokes the existing deterministic `Git.create` before inspecting the local annotation. Its result must equal the stored object ID exactly. This recreates pruned local bytes without changing intended identity, checkpoint details, local tag refs, or remote tags. Matching accepted remote tags complete pending intent without another push. Malformed/conflicting intent, object-store errors, local/remote tag conflicts, and disappeared completed tags remain refusals. No private-ref subsystem or broad Git-error-as-absence fallback was added.
- **B3 — Commit-local notes:** Added the pure `core.git_path` validator and reused it in identity policy and `Runner.git_blob`. Historical reads use `git --literal-pathspecs ls-tree -z` against the requested commit, require an exact regular blob entry, and read by object ID. Current symlinks, removed paths, or directory replacements cannot supply bytes or invalidate valid historical notes. Captured symlinks, intermediate symlinks, gitlinks, directories, unsafe paths, and invalid note bytes remain rejected. Filesystem-aware `child()` checks are unchanged for real destinations.
- **Tests:** Added 26 methods across package-linking and publication-note suites, replacing the earlier third-helper-call expiry test with I/O-boundary clock behavior. New cases cover authority replacement/renewal and UTC boundaries, lookup/flush expiry, late/lost responses, blocked later writes with prepared-build reuse, real Git pruning before and after push acceptance, unchanged intent/object recovery, malformed operations and conflicts, commit-local note paths, literal filenames, and a successor publication using real local Git with injected Docker/API effects.
- **Version and docs:** Updated `VERSION`, `release_template.__version__`, and README to 0.2.6. Added project-focused `docs/releases/0.2.6.md` and pointed the opt-in Ubuntu fixture's notes setting at it. Updated package-linking, publication, configuration, and verification documentation for actual guarantees, recovery, and test boundaries. The fixture update is preparation only, not authorization to publish.

## Verification

- **Baseline:** `python3 -B -m unittest discover -s tests -q` passed the original 230 tests in 45.335 seconds before changes.
- **Failing-before evidence:** Added six focused regression scenarios before modifying production code. Running those scenarios against the original behavior produced two assertion failures and four expected operational errors: stale authority returned after version lookup, implicit renewal from a replaced file, a later invalid file replacing an already captured record, missing pruned annotations before push and after lost response, and rejection of valid historical notes because of a current symlink. These results reproduce all three reviewed defects rather than only asserting new helper wiring.
- **Passing-after evidence:** Reran those same six scenarios after the fixes; all six passed in 0.393 seconds. The command targeted `PackageLinkTests.test_window_validation_rechecks_time_after_version_lookup`, `test_replacement_file_cannot_renew_expired_captured_authority`, `test_authority_snapshot_is_used_even_if_file_is_replaced_during_validation`, and `GitNotesTests.test_pending_annotation_is_recreated_after_pruning_before_push`, `test_pruned_annotation_with_accepted_remote_tag_needs_no_second_push`, `test_historical_regular_notes_survive_current_clean_symlink`.
- **Full suite:** Final `python3 -B -m unittest discover -s tests -q` passed 256 tests in 47.444 seconds. This includes unchanged retention, CLI credential isolation/read-only behavior, exact-pin refusal, legacy identity, local-image protection, and remote deletion-gate regressions.
- **Real local Git:** Recovery fixtures verify the tag object actually becomes absent after `git prune --expire=now` in their exclusively owned temporary source repository, then require exact same-object recovery through reopened workflow state. The local bare remote is used only as a fixture. A lost accepted push is reconciled without another push. Two-commit historical-note and successor tests preserve old body/tag identity while current paths change. No real Docker build/run or live Gitea operation is used.
- **Static/documentation checks:** Python AST syntax checks, all six bundled example configuration validations, root/module/README version agreement, Ubuntu notes-path agreement, Markdown heading/table-of-contents anchors, `bash -n scripts/release.sh`, and `git diff --check` passed.
- **Serial launcher validation:** `python3 -B scripts/launch.py validate --config examples/explicit.json` and then `python3 -B scripts/launch.py validate --config examples/ubuntu-hello/release.json` each passed with the no-credentials/no-remote-operations message. They were not run concurrently because the launcher shares a destination lock.
- **Unchanged safety implementation:** Compared against `55546c1` and confirmed no changes to bootstrap scripts, `state.py`, `cleanup.py`, `local.py`, previously published 0.2.4/0.2.5 notes, or task 9 results/evidence. No broad cleanup or checkpoint repair was introduced.

## Compatibility And Limits

Configuration remains schema 2, publication identity remains schema 2, outer checkpoint and retirement metadata remain schema 1, and nested local ownership remains schema 2. Canonical tag bytes, tagger identity/epoch, and public project-note rendering are unchanged. Existing source/config/template pin equality remains mandatory: the new binary does not adopt or rewrite a captured old-pin transaction, even when schemas match.

The window record retains its schema and fields. One loaded snapshot governs one attempted dispatch; replacing its file is not an implicit renewal, redirection, or revocation protocol. A mutating retry loads fresh authority. Start is inclusive, expiry exclusive, and the maximum interval is unchanged. The final clock decision follows blocking validation and persistence, but cannot make network completion atomic with UTC expiry. Actual operator-established exclusion must continue through in-flight completion; the JSON assertion and checkout-local lock do not enforce server-wide serialization.

Deterministic reconstruction restores only the exact expected annotation object. It does not force-update tags, repair a completed tag's disappearance, refresh predecessor ownership, rebuild images to escape conflicts, or treat authentication/transport/object-store errors as absence. Corrupt or conflicting intent remains an explicit stop.

Lexical committed-path validation does not follow current symlinks or inspect their targets. Regular-file validation is tied to the requested tree, not relaxed globally. Active configuration and mutable working-tree/build/update destinations still use filesystem-aware protections. Runtime/store behavior, package-link replacement semantics, operator exclusion, power-loss durability, and live v0.2.6 operation are not certified by these local tests.

## Preserved Resources

Published v0.2.3/v0.2.4/v0.2.5 source tags, release descriptions, remote main/latest, registry/package records, associations, and production deletion evidence were not accessed or changed for this task. Preserved task 9 live checkouts/checkpoints and local Docker content remain untouched. Earlier approved live evidence stays historical; this task creates no replacement attestation or new live evidence file.

Only test-owned temporary Git repositories were pruned or had fixture refs/files/symlinks changed. No pruning was run against this project repository or preserved release checkouts. `todo.md`, the task goal/plan/review, and task 9 records remain unchanged. A live 0.2.6 experiment requires separate explicit target/version/source/image/release approval and must not substitute new code or identity into an old checkpoint.
