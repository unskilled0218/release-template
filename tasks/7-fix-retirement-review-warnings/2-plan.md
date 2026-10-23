# Plan

- [Plan](#plan)
  - [Scope](#scope)
  - [Implementation Plan](#implementation-plan)
    - [1. Define deletion-evidence time validity](#1-define-deletion-evidence-time-validity)
    - [2. Confirm abandonment before checkpoint completion](#2-confirm-abandonment-before-checkpoint-completion)
    - [3. Add deterministic regression coverage](#3-add-deterministic-regression-coverage)
    - [4. Update documentation and release metadata](#4-update-documentation-and-release-metadata)
    - [5. Verify and record implementation results](#5-verify-and-record-implementation-results)
  - [Acceptance Criteria](#acceptance-criteria)
  - [Risks And Decisions](#risks-and-decisions)

## Scope

Resolve D1 and D2 from `tasks/6-code-review/code-review.md`, following `1-goal.md`. Limit implementation to abandonment confirmation, evidence-time validation, related tests, and documentation/version updates. Preserve publication identities, cleanup scheduling, checkpoint schemas, credential handling, and graph protection. This planning commit changes no implementation code.

## Implementation Plan

### 1. Define deletion-evidence time validity

- Add a small validator in `release_template/cleanup.py` for the `verified_at` field, invoked by `deletion_evidence` before any runtime version request or deletion. Keep timestamp validation separate from the existing structural guard.
- Proposed policy: verification may be at most 30 days old and at most 5 minutes in the future. Use named constants measured in seconds. Both limits are inclusive; exceeding either limit refuses evidence. These are explicit planning assumptions, not existing requirements or measured server guarantees.
- Accept exactly `YYYY-MM-DD` for compatibility with current attestations and `YYYY-MM-DDTHH:MM:SSZ` for precise UTC timestamps. Interpret a date-only value as midnight UTC. Require exact lexical shape and a valid calendar/time value; reject whitespace, implicit local time, offsets, fractions, impossible dates, and non-string values. Do not normalize the stored evidence or alter its identity fields.
- Use timezone-aware UTC arithmetic. Give the validator an optional numeric `now` value for deterministic tests; obtain the current epoch time at call time when omitted. Do not bind a clock result as a default argument or use local timezone conversion.
- Raise bounded `ReleaseError` messages distinguishing invalid timestamps, expired evidence, and excessive future skew. Do not echo attestation contents or silently refresh verification dates.
- Keep schema 2, product/origin binding, exact full server-version matching, disposable-repository requirements, and successful-result assertions unchanged. Apply the same time gate through existing `deletion_environment` callers for normal cleanup, retries, and abandonment. Read-only `cleanup-plan` remains evidence-free.

### 2. Confirm abandonment before checkpoint completion

- Refactor the per-staging-alias path in `abandon` only as needed to make lookup, deletion, and confirmation explicit. Preserve selected-run validation, minimum age, exact tag/digest ownership, current publication checks, and repository association checks.
- Always perform the scoped Gitea package lookup, even if `registry.resolve` reports an absent alias. Registry absence alone must not bypass package evidence. Continue using `Gitea.get(..., absent=True)` so only an allowed HTTP 404 becomes absence.
- For a present registry alias, require its captured digest. A present package also requires existing repository/name ownership checks. If registry and package presence disagree, stop without issuing DELETE or recording abandonment; retry after the two views converge rather than infer deletion authority.
- If both views are absent, reconcile that alias without DELETE. If both are present and owned, reverify current publication immediately before deletion, then delete the exact selected staging package.
- After DELETE returns, require scoped package absence and registry alias absence. A still-present package/alias, malformed lookup, authentication failure, or unavailable response stops the operation. Do not mark the affected run abandoned or process subsequent aliases after uncertain confirmation.
- Persist `abandoned = True` only after every staging alias in that run has confirmed absence. Keep existing per-run persistence rather than promise an atomic transaction across selected runs. Earlier confirmed deletions or completed runs remain legitimate progress after a later failure.
- On accepted-but-response-lost DELETE or interruption before saving the checkpoint, leave the run unmarked. A later invocation must reconcile both absent views without repeating DELETE. Do not require fetching retired alias graphs to reconcile absence.
- Preserve all captured outputs, staging digests, run identity, operation records, and `cleanup_complete` values. Do not remove abandoned runs from `protected_graph`, delete raw digests, rebuild images, or introduce cross-revision checkpoint adoption. Do not trust an existing `abandoned` flag as a reason to skip fresh checks.

### 3. Add deterministic regression coverage

- Add focused evidence-time tests in `tests/test_gitea_migration.py` or a dedicated small test module. Cover accepted date-only and UTC-second forms; valid leap days; invalid calendar dates; whitespace and wrong shapes/types; the review examples `1900-01-01`, `not-a-date`, and `2999-01-01`; exact age/skew limits and values one second outside each limit.
- Exercise invalid, stale, and future evidence through both `apply` and `abandon`, not only the validator. Assert zero DELETE calls, unchanged checkpoint bytes, preserved publication, and no runtime version request after local evidence rejection.
- Replace the hard-coded verification date in `tests/support.py:evidence` with a fresh synthetic UTC timestamp evaluated at fixture creation. Allow an explicit verification-time override for boundary tests. These remain test-only attestations, never production evidence. Freeze or inject clocks where exact limits matter; avoid sleeps and dependence on the calendar date of execution.
- Extend `tests/test_gitea_absence.py` so abandonment uses real Gitea status/JSON decoding through its injected transport. Cover a successful no-op DELETE; present, null, non-object, malformed JSON, HTTP 401/403/500, and connectivity failure during post-delete confirmation; and package/registry disagreement in either direction before deletion.
- Add accepted-but-response-lost and interruption-before-checkpoint-save cases. Reopen the selected checkpoint from disk, retry with consistent verified absence, and assert no duplicate DELETE and no image rebuild. Also cover interruption after the checkpoint save and idempotent subsequent invocation.
- Include multiple aliases in one selected run: a later uncertain deletion must leave that run unmarked while retaining earlier remote progress; retry must skip confirmed-absent aliases. Include multiple selected runs to document per-run progress rather than all-or-nothing behavior.
- For all abandonment failures, check the affected persisted `abandoned` flag, unchanged approval/identity/output records, retained current publication, absence of raw-digest DELETE, and continued graph protection. Retain current null pre-lookup, unknown ownership, digest-conflict, age, and exact-version regressions.
- Add a CLI abandonment regression in `tests/test_cli.py` confirming nonzero status and the existing publication-success/cleanup-incomplete diagnostic when confirmation fails. Keep credentials and external tools mocked at established seams.

### 4. Update documentation and release metadata

- Update `docs/retention.md` with exact timestamp forms, UTC interpretation, inclusive 30-day age and 5-minute skew limits, and date-only midnight behavior. Describe blocked confirmation, disagreement between API and registry views, per-run progress, and retry without duplicate deletion.
- Update `docs/gitea-migration.md` and `docs/verification.md` to distinguish exact-version binding, time freshness, operator-attested product/storage identity, and actual live test results. Update `docs/publication.md` only where retry diagnostics or evidence instructions need clarification.
- Explain that expiry requires real reverification, not editing the date on old results. Storage changes still require immediate reverification even inside the age window; timestamps cannot detect those changes or prove test results truthful.
- Keep README concise; update its version/summary only as needed. During implementation, bump `VERSION`, `release_template.__version__`, and README consistently from `0.2.1` to `0.2.2`. Keep bootstrap bytes, configuration schema 2, evidence schema 2, and checkpoint/retirement schemas unchanged.
- Preserve exact-pin checkpoint refusal and its documented upgrade limitations. Do not suggest running vulnerable old cleanup code, rewriting checkpoint identity, or discarding state as a workaround.

### 5. Verify and record implementation results

- Run targeted abandonment, evidence-gate, and CLI tests while developing, then run `python3 -B -m unittest discover -s tests -v`. All existing 141 tests and the new regressions must pass.
- Run `bash -n scripts/release.sh`, `python3 -B scripts/launch.py validate --config examples/explicit.json`, and `git diff --check`. Check agreement among release version values and table-of-contents links in changed Markdown files.
- Inspect the diff for unintended changes to bootstrap checksums, schemas, cleanup approval metadata, credentials, and graph protection. Do not contact real servers, read real tokens, publish images/releases, install into consumers, or edit `todo.md`.
- Write actual test results, deviations from this plan, and remaining live-verification limits to `4-implemented.md` during implementation. Commit only authorized task changes; this plan does not execute them.

## Acceptance Criteria

- D1: no affected run is newly marked abandoned until all selected staging aliases have consistent, status-aware package and registry absence evidence.
- A successful DELETE with persistent or malformed confirmation fails safely. Accepted-but-response-lost or interrupted deletion resumes from disk without repeating a confirmed-absent DELETE, rebuilding images, or losing graph protection.
- Registry absence cannot conceal a present or invalid Gitea lookup. Changed identities, foreign ownership, and inconsistent views cannot authorize deletion.
- D2: malformed, over-age, and excessively future-dated evidence stops normal cleanup and abandonment before DELETE; local timestamp failures occur before runtime version requests or checkpoint mutation.
- Proposed timestamp formats and exact inclusive age/skew boundaries have deterministic tests. Existing valid date-only schema-2 evidence remains usable when inside the age window.
- Publication success, immutable identities, retirement order, schema boundaries, and same-pin retry behavior remain intact. `cleanup-plan` requires no evidence.
- Tests pass, documentation matches enforced behavior, and release version metadata agrees. No live verification is claimed or performed without separate approval.

## Risks And Decisions

- D2 offers either enforced freshness or operator-only freshness. This plan selects enforced freshness to make the current safety guarantee concrete. The proposed 30-day maximum age and 5-minute skew are reviewable policy choices; resolve objections during plan review before implementation rather than silently choosing new limits in code.
- A valid date-only attestation expires relative to midnight UTC, not the unknown time tests finished. Precise UTC timestamps avoid that conservative loss of usable hours. No timezone or date guessing is allowed.
- The time gate runs at invocation entry, matching existing environment/version validation. This task does not add a continuously refreshed lease or guarantee an attestation cannot expire during a long cleanup. Document this boundary rather than imply per-DELETE freshness enforcement.
- Strict two-view absence may stop on eventual consistency. Refusal and later explicit retry are safer than success based solely on DELETE status; this task adds no polling, automatic retries, or force bypass.
- New confirmation checks cannot undo earlier remote deletion. Keep checkpoints and graph evidence intact on failure; do not promise rollback or atomic completion across aliases/runs.
- Clock validation cannot prove a trusted operator's claims or detect storage changes. It supplements, rather than replaces, same-server disposable tests and operational serialization of external publishers.
- Existing falsely marked checkpoints are not repaired automatically. Any migration, live deletion test, deployment certification, or consumer adoption remains a separate task.
