# plan

- [plan](#plan)
  - [Scope](#scope)
  - [Current behavior](#current-behavior)
  - [Implementation Plan](#implementation-plan)
    - [1. Establish status-aware lookup contracts](#1-establish-status-aware-lookup-contracts)
    - [2. Cover every absence-sensitive operation](#2-cover-every-absence-sensitive-operation)
    - [3. Preserve valid absence recovery](#3-preserve-valid-absence-recovery)
    - [4. Document and verify the patch](#4-document-and-verify-the-patch)
  - [Acceptance Criteria](#acceptance-criteria)
  - [Risks And Decisions](#risks-and-decisions)

## Scope

Fix B1 from `tasks/4-migrate-forgejo-to-gitea/5-code-review.md`: successful malformed Gitea JSON must not establish remote absence, authorize release creation, or falsely complete retirement. Keep the repair at the existing adapter boundary and add regression coverage for its publication/cleanup callers. This stage writes and commits only this plan. Implementation, live server operations, credential access, consumer adoption, remote changes, and pushes are not authorized by planning.

## Current behavior

- `Gitea.get()` in `release_template/adapters.py:150-152` returns `None` for HTTP 404 and JSON `null` from HTTP 200. The new `release()` object guard accepts either source of `None`.
- `Workflow.publish()` interprets `None` as permission to POST a release. Cleanup interprets it as confirmed absence before deletion, after deletion, and when reconciling a candidate omitted from the package listing. Explicit abandoned-run retirement uses the same optional lookup.
- The review reproduced `cleanup_complete == True` with zero DELETEs while a staging package remained listed and resolvable. Existing malformed-release tests omit JSON `null`; direct fakes cannot distinguish an invalid successful response from a legitimate absence.
- All optional `get(..., absent=True)` calls in the current engine are object lookups: release lookup and package-version lookup. Paginated collection reads use `absent=False` and must continue accepting arrays. The version endpoint remains independently object/full-version validated.
- The recorded baseline is 132 passing tests, version `0.2.0`, schema-2 Gitea configuration, and default token path `~/.config/git/token`. The preceding user's path correction overrides the older migration plan's default.

## Implementation Plan

### 1. Establish status-aware lookup contracts

- First add failing loopback regressions in `tests/test_gitea_migration.py` for HTTP 200 JSON `null` on release and package-version lookups. Test `Gitea.get()` directly as well as `release()` so a wrapper-only check cannot conceal the package bug.
- In `Gitea.get()`, return `None` only for an explicitly allowed HTTP 404. For successful HTTP 200, decode JSON once and reject decoded `None` with a bounded `ReleaseError`, including when `absent=False`. Never log response bodies, tokens, or raw remote values in validation errors.
- Define the existing `absent=True` branch as an optional-object lookup: require an object on HTTP 200 and reject arrays, strings, numbers, and booleans. Keep `release()` consistent with that contract. Do not globally require objects for all GET responses; collection arrays must remain valid for `pages()`.
- Preserve existing release/package paths, URL encoding, token headers, allowed status codes, pagination exhaustion/repetition bounds, JSON decoding failures, and 401/403/server/connectivity error handling. A disallowed 404 must still fail rather than return `None`.
- Do not change the shared OCI `json_response()` contract to solve this Gitea-specific absence issue. Do not introduce provider abstractions, a new checkpoint representation, or a general response-schema framework. Existing ownership/identity checks still validate the fields of object-shaped lookup results; an empty object is not evidence of absence.

### 2. Cover every absence-sensitive operation

- Exercise the real `Gitea` decoder/validation path through loopback HTTP or an injected HTTP transport that supplies actual status and JSON bytes. Do not reproduce the fixed behavior by mocking `Gitea.get()` or `release()` to return `None`: that bypasses the boundary and still means legitimate absence after the fix. Keep registry/runner fakes where they isolate unrelated systems; never use actual credentials or Docker.
- **Publication:** Inject a malformed successful current-release lookup at the release decision in `Workflow.publish()`. Assert a bounded failure, no release POST, no release-operation completion, and no transition of an unpublished run to `published`. Existing source/build/tag/promotion work may precede that lookup under the current protocol; preserve its durable intent and do not claim that the entire invocation had zero earlier writes or roll anything back. Verify a later valid retry still reconciles prepared output without rebuilding.
- **Listed cleanup candidate:** With valid fixture evidence, verified publication, and an owned staging candidate still listed/resolvable, return HTTP 200 `null` for its pre-delete lookup. Assert zero DELETEs, the candidate remains pending in durable state, publication remains successful, and cleanup is not marked complete. Reopen state to verify the persisted result, not only in-memory flags.
- **Omitted candidate:** Begin with an approved saved inventory, omit the pending package from the current complete listing, and return HTTP 200 `null` from its direct scoped lookup. Assert reconciliation does not mark it absent/complete and no DELETE follows. Preserve the approved retirement fingerprint/order.
- **Post-delete confirmation:** Let a valid lookup and one authorized package DELETE succeed, then return HTTP 200 `null` from the confirmation GET. Assert the outcome remains uncertain: no completion flush for that candidate, no dependent/later DELETE, and no cleanup-complete transition. Preserve the accepted remote deletion; do not attempt rollback or reconstruction.
- **Release retirement:** For an older release candidate, malformed successful release lookup must stop before that release's DELETE and leave its candidate pending. Current-publication verification must remain valid so the test reaches the intended older-release lookup.
- **Abandoned runs:** With a valid selected old unpublished checkpoint and a still-resolving staging alias, malformed successful package lookup must stop before DELETE and before setting that checkpoint's `abandoned` flag. Preserve its state and graph protection.
- Use fresh temporary state per scenario or explicit resets to avoid progress from one parameterized case affecting another. Include representative non-object HTTP 200 shapes alongside `null` at the adapter layer; operational cases may focus on `null`. Assert diagnostics do not expose a fixture secret embedded in malformed response content.

### 3. Preserve valid absence recovery

- Add paired HTTP 404 cases proving optional release/package lookup returns `None`, while required reads still reject 404. Keep successful object lookups and collection arrays working; include `200 []` as a valid exhausted page, not a missing object.
- Verify a real 404 at the publication lookup still permits exactly one release POST, followed by valid verification. Keep text-only release identity and forward-only alias guards intact.
- After a simulated accepted deletion with uncertain confirmation, retry with a consistent listing and real 404 scoped lookup. Assert the saved candidate becomes complete without another DELETE or fetching its already retired raw manifest graph. Keep dependency-safe continuation and existing lost-response/removal-aware fixtures intact.
- Preserve 204/404 DELETE idempotence, 401/403/error distinctions, exact product/origin/full-version evidence gating, repository association checks, survivor protection, saved retirement topology, and unchanged template/config/source checkpoint identity refusal. Do not weaken any guard to make the new tests pass.

### 4. Document and verify the patch

- On later authorized implementation, create a fresh branch exactly named `5-fix-gitea-null-response` according to the implementation workflow. Do not reuse the current task-4 branch as its implementation branch.
- Bump `VERSION`, `release_template.__version__`, and README consistently from `0.2.0` to patch version `0.2.1`. Update README briefly and relevant retention/verification documentation to state that only actual allowed 404 establishes lookup absence, and malformed successful responses stop progress. Explain that uncertainty after accepted DELETE is recoverable by verified absence, not automatic repetition or rollback.
- Preserve historical task goals/plans/reviews/results and prior health records. Leave `GIT_TOKEN`, `GIT_USERNAME`, `~/.config/git/token`, schema 2, disabled-by-default live cleanup, and stable bootstrap bytes unchanged. No credential-file migration or checkpoint adoption is included.
- Run focused adapter/migration/workflow/retirement/CLI tests, then `TMPDIR=/tmp/opencode python3 -B -m unittest discover -s tests`. Retain all 132 baseline safety cases and record the actual expanded count rather than predetermining one.
- Run `bash -n scripts/release.sh`, all five credential-free example validations through `scripts/launch.py`, Python syntax/version consistency checks, changed Markdown contents/local-link checks, and `git diff --check`. Confirm state/OCI/bootstrap/updater protocol files and unrelated files have no unintended diff.
- Record the changes, failed-before/passed-after null-response tests, final verification, and live-test limitations in this task's `4-implemented.md`; commit scoped implementation changes without pushing. Never stage or modify `todo.md`.

## Acceptance Criteria

- HTTP 200 JSON `null` never produces the missing-object sentinel. Only explicitly allowed HTTP 404 returns `None`; required 404 reads still fail.
- Optional release/package successful lookups require objects; non-object payloads fail with bounded credential-free errors. Valid pagination arrays, including empty pages, and valid version objects retain their existing behavior.
- Malformed release lookup cannot cause release POST or falsely complete publication. Malformed package/release retirement lookup cannot authorize DELETE or advance the affected pending completion/abandonment flag. Confirmed prior side effects and durable intent remain intact.
- Malformed post-delete confirmation stops later/dependent deletions and leaves the affected candidate pending. A later verified-404 retry reconciles absence without duplicate DELETE or dependency reconstruction.
- Regression tests exercise actual status/JSON decoding rather than only returning Python `None` from a fake. Publication and cleanup assertions cover remote requests plus persisted state, and preserve successful publication when cleanup stops.
- All existing safety cases and the expanded suite pass. Schema, credentials/default path, checkpoint/publication identities, retirement metadata, bootstrap bytes, history, unrelated work, remotes, and actual consumers remain unchanged except for the documented patch version and scoped tests/docs.
- No live deployment verification, credential access, real Docker operation, remote mutation, consumer installation outside disposable fixtures, or push occurs. Fresh authorized same-server evidence is still required for live cleanup.

## Risks And Decisions

- `None` remains the optional-object absence sentinel, but its source becomes strictly HTTP 404. Rejecting successful null is preferable to normalizing it or adding a new sentinel throughout the workflow.
- Object-shape enforcement is limited to optional object lookups. This avoids breaking list endpoints without adding path-based heuristics or a speculative type system. Required version shape and lookup object fields retain their existing caller validations.
- A malformed response can arrive after legitimate earlier effects. Fail-closed means no authority derived from that response and no false completion; it does not promise atomic publication, a rollback, or zero preceding writes. Post-delete tests must expect the one already authorized DELETE.
- The fix repairs future uncertainty handling; it cannot automatically discover and repair checkpoints already falsely marked complete by earlier code. Preserve affected provenance for separately reviewed operator handling; do not rewrite identities or silently adopt old-pin state.
- Tests with fake service return values alone would repeat the original coverage illusion. At least the null-sensitive operation paths must traverse the production Gitea decoding/shape validation seam. Local fixture success is not proof of a particular deployed Gitea/storage environment.
