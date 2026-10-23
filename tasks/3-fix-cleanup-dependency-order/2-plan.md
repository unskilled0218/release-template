# plan

- [plan](#plan)
  - [Scope](#scope)
  - [Current behavior](#current-behavior)
  - [Implementation Plan](#implementation-plan)
    - [1. Reproduce destructive dependency-order failures](#1-reproduce-destructive-dependency-order-failures)
    - [2. Calculate deterministic referring-manifest-first order](#2-calculate-deterministic-referring-manifest-first-order)
    - [3. Persist the approved retirement schedule](#3-persist-the-approved-retirement-schedule)
    - [4. Reconcile progress without weakening survivor protection](#4-reconcile-progress-without-weakening-survivor-protection)
    - [5. Handle legacy inventories conservatively](#5-handle-legacy-inventories-conservatively)
    - [6. Document and verify the patch](#6-document-and-verify-the-patch)
  - [Acceptance Criteria](#acceptance-criteria)
  - [Risks And Decisions](#risks-and-decisions)

## Scope

Resolve B1 from `tasks/2-fix-release-review-warnings/5-code-review.md` in this template only. Schedule authorized referring manifests before their dependencies, persist that schedule before deletion, and prove interruption/retry behavior with removal-aware OCI fixtures. Preserve all existing reference protection, ownership checks, publication identity, and live deletion gates. This planning stage creates only this file and commits it; it does not modify implementation, run live operations, alter consumers, or touch `todo.md`.

## Current behavior

- `release_template/cleanup.py:98-119` fetches complete graphs for all same-name package records. `validate_inventory()` repeats this before and between destructive operations.
- `cleanup.apply()` orders aliases before releases before raw digest records, but retains arbitrary inventory order within the digest group. Deleting a child before its pending index makes the next graph scan fail with `Required registry content is absent`; retry encounters the same broken pending index.
- `Registry.graph()` already supplies immutable node identities, membership/subject edges, and full reachable manifest sets. Cleanup currently discards enough of that evidence that it cannot schedule referring candidates first.
- `FakeRegistry.graph()` generates synthetic dependency evidence without checking dependent-manifest availability. Existing loopback graph coverage is read-only, while destructive tests mainly check aliases and independent digest roots. The preceding review recorded 83 passing tests despite B1.
- State is durably flushed and bound to source/configuration/template identity. That guard must remain intact: compatibility with an old-shaped inventory under matching identity is not cross-revision adoption.

## Implementation Plan

### 1. Reproduce destructive dependency-order failures

- Extend the existing loopback OCI test setup with a small removal-aware Forgejo fixture that lists exact package records and removes only the selected alias or manifest. Use the real `Registry` adapter and durable `State` under `/tmp/opencode`; verify a separate current publication through actual fixture content before and after cleanup.
- First reproduce the review's child-first inventory: an owned older image manifest, an older index referring to it, and both records eligible for deletion. Assert complete cleanup succeeds without breaking current content. Run this against the current implementation and record the expected failure before fixing it.
- Add nested indexes, two parents sharing a child, and deliberately shuffled/reversed package inventories. Include a candidate parent reaching a candidate descendant through an intermediate manifest without a separate package record. Assert referring candidates disappear before affected candidate dependencies, not an incidental total ordering of unrelated records.
- Cover subject relationships with classifiable owned image manifests and preserve explicitly ineligible artifact/attestation roots. A preserved subject-bearing root must continue protecting its dependencies; it must never acquire deletion eligibility merely to simplify ordering.
- Inject termination and accepted-but-response-lost faults after each authorized digest deletion, before completion flush, and after completion flush. Reopen checkpoint state and resume with freshly read fixture inventories. Assert no duplicate DELETE for confirmed-absent targets, no rebuilding, no stalled parent traversal, and eventual completion when no external conflict exists.
- Do not rely on the permissive workflow fake as the oracle for B1. Keep existing small workflow tests, and add a fixture assertion that deleting a child makes an undeleted parent graph genuinely unreadable. If adapting shared fake support is necessary, do not synthesize deleted dependencies back into existence.

### 2. Calculate deterministic referring-manifest-first order

- Add a focused pure ordering helper in `release_template/cleanup.py`; do not introduce a generic graph framework or reuse build ordering with reversed, ambiguous semantics.
- Retain each candidate root's reachable manifest evidence during package discovery. Key raw digest candidates by image name and immutable digest, never just digest or list position, so identical content across image namespaces does not merge deletion authority.
- After survivor protection has removed unsafe digest candidates, derive ordering constraints only among the remaining exact authorized candidates. If candidate A reaches candidate B through membership or subject relationships, A must retire before B. Include transitive relationships through intermediates that are not package candidates; never add those intermediates as new deletion targets.
- Use a bounded deterministic topological sort with stable image/digest tie-breaking. Shared children wait for every candidate parent. Independent candidates may use any stable tie order. Reject cycles, duplicate candidate identities, malformed evidence, and unknown ordering schemas before any deletion.
- Keep all authorized aliases ahead of raw digest retirement; preserve current release eligibility checks. A digest whose referring root survives remains protected rather than being made deletable by ordering. The ordering helper consumes validated evidence and performs no filesystem, HTTP, or Docker operations.
- Unit-test chains, shared descendants, disconnected candidates, same digest in different image names, transitive edges, malformed input, and cycles using small explicit graph fixtures. Update existing saved-order tests to construct deliberately reversed candidate lists rather than depend on the planner placing a digest at a particular array index.

### 3. Persist the approved retirement schedule

- Keep the outer checkpoint identity/schema unchanged. Add explicitly versioned nested retirement metadata to the cleanup inventory, for example `retirement` with its own `schema: 1`, exact raw-candidate identity projection, dependency constraints, and ordered stable candidate keys. Document the final field names alongside their validation tests.
- Bind metadata to the cleanup run and a canonical fingerprint of immutable candidate identities, excluding mutable completion flags. Do not use candidate array offsets as identifiers. Metadata may order or restrict existing authority; it cannot add candidates or broaden ownership/version eligibility.
- Generate the schedule from fully fetched, digest-validated evidence before the first deletion, including before earlier alias/release deletions. Flush the candidate inventory and retirement metadata together using existing durable state writes. A read-only `cleanup-plan` may return the proposed schedule but must not write a checkpoint or perform deletions.
- On retry, validate metadata shape, uniqueness, image scoping, complete candidate coverage, fingerprint binding, and order/edge consistency before using it. Preserve the approved schedule instead of silently replacing it after partial retirement. Persist no credentials, authentication headers, or unrelated registry content.
- Test rejection of missing keys, altered candidate identities, unsupported nested schemas, duplicate keys, omitted nodes, reversed dependency constraints, and interrupted initial schedule persistence. Fail before DELETE if valid ordering authority cannot be established.

### 4. Reconcile progress without weakening survivor protection

- Execute raw candidates in the persisted dependency order, retaining existing per-candidate durable completion markers. Referring candidates must reach confirmed retirement before a dependent candidate can proceed. A failed parent deletion stops progress toward all affected dependencies.
- Reconcile a lost DELETE response against exact candidate absence through the scoped package API and fresh inventory. Confirmed absence can complete that recorded operation durably; authorization, connectivity errors, inconsistent listings, or unreadable evidence are not absence. Never retry an already confirmed-absent deletion blindly.
- Separate completed/confirmed-absent candidate reconciliation from graph collection so an absent retired parent is not traversed just because its completion response was lost. Remaining live pending roots must still have complete fresh graphs: correct ordering ensures their dependencies have not yet been deleted by this transaction.
- Keep current publication verification, same-name inventory collection, exact ownership/digest checks, all-runnable version/source checks, unfinished-run protection, and transaction-relative survivor graph protection. Recompute survivor evidence before each destructive operation; saved topology only schedules approved deletions and is never a substitute for fresh safety evidence.
- Treat a completed parent record that reappears as a survivor, not renewed deletion authority. Newly introduced or retargeted aliases/roots absent from pending authority must protect their full graphs even when policy otherwise allows their deletion. Stop before dependency retirement if these fresh references require it.
- Add tests introducing a preserved alias or same-name foreign root between parent and child deletion, recreating a completed parent, changing a pending identity, and returning HTTP/authentication failures during reconciliation. Assert no unsafe follow-up deletion, unchanged publication success, and retained pending state for inspection.

### 5. Handle legacy inventories conservatively

- Preserve exact source/configuration/template identity validation. An upgraded pin still cannot load an old revision-bound checkpoint. Do not modify `State` identity checks, stable bootstrap, release identity metadata, or CLI adoption permissions.
- For a matching-identity cleanup inventory without retirement metadata, initialize a schedule only when every raw candidate is still present with full validated evidence and no raw candidate is already marked complete. Keep the exact recorded candidate set, including its existing completion flags for non-digest operations; do not discover extra deletion authority while initializing metadata.
- If a raw candidate is already absent/completed, a pending graph is broken, or evidence cannot prove a safe pre-deletion schedule, stop with a bounded operator-facing cleanup-incomplete explanation. Do not infer old deletion order, reconstruct missing manifests, erase state, rewrite identities, or adopt cached unverified evidence. Inventories with no raw candidates can use an empty retirement schedule without changing alias/release policy.
- Test intact old-shaped inventories under matching identity, alias-only inventories, already-partial child-first inventories, and old-pin/new-pin CLI rejection. Legacy-shaped fixture tests must not be described as cross-revision recovery support.

### 6. Document and verify the patch

- Update `docs/retention.md` with referring-manifest-first retirement, shared/subject dependency handling, persisted schedule validation, absence reconciliation, and the distinction between scheduled progress and fresh survivor protection.
- Update `docs/publication.md` and `docs/verification.md` with safe retry behavior, deliberately fail-closed legacy partial states, and removal-aware fault coverage. Keep live Forgejo/Docker verification limits and the single-publisher requirement explicit. Preserve the existing checkpoint upgrade warning in installation/publication documentation.
- During implementation, bump `0.1.1` to `0.1.2` consistently in `VERSION`, `release_template/__init__.py`, and the short README version statement. Do not change stable launcher bytes or introduce automatic migration commands.
- Run the focused new regression tests before and after the fix, then `TMPDIR=/tmp/opencode python3 -B -m unittest discover -s tests`, `bash -n scripts/release.sh`, credential-free validation for all five example configurations, Python syntax/version consistency checks, Markdown table-of-contents checks, and `git diff --check`.
- Record actual implementation changes, observed test results, and remaining operational limits in this task's `4-implemented.md` when implementation is authorized. Commit only scoped code, tests, documentation, version updates, and implementation results on a new task-named implementation branch. Existing project adoption and live operations remain unauthorized.

## Acceptance Criteria

- Child-first, reversed, and shuffled inventories cannot make cleanup delete a candidate dependency before every candidate referring manifest retires. Nested indexes, shared descendants, transitive relationships, and subject edges are accounted for without expanding the candidate set.
- A valid schedule is durably bound to the exact cleanup transaction before its first deletion. Unknown, malformed, mismatched, cyclic, or incomplete scheduling evidence stops deletion rather than falling back to inventory order.
- Restart after every successful or lost-response deletion completes from the same approved authority when the fixture remains consistent. Absent retired parents are reconciled without being traversed, and live pending parents never lose dependencies through this transaction's ordering.
- Fresh preserved-reference and unfinished-run protection remains mandatory before destructive operations. New unscheduled roots, changed identities, recreated completed records, or uncertain remote evidence stop unsafe progress, irrespective of the saved schedule.
- Intact matching-identity old-shaped inventories may acquire a verified schedule; ambiguous partially retired inventories remain fail-closed. Cross-revision checkpoint adoption, source/config/template identity relaxation, and implicit candidate expansion are not introduced.
- The full existing suite and new removal-aware apply/retry tests pass. Read-only planning, publication, platform/label verification, staging retirement, credential isolation, installer/update behavior, and text-only releases retain their existing guarantees.
- No production token reads, real Docker builds, live mutations, consumer migrations, or fabricated production deletion evidence occur during implementation or tests. The independent live deletion gate remains unchanged.

## Risks And Decisions

- Ordering is the reverse of construction: referring manifests retire before dependencies. A topological cycle or contradictory graph cannot be resolved by arbitrary tie-breaking; cleanup stops before mutation.
- Saved topology is not a claim that old content is still present or safe to delete. Digest validation binds fetched graph evidence, while fresh inventory, ownership, and survivor checks continue controlling actual authority.
- Legacy partial transactions may already contain the defect's irreversible missing-child state. This patch prevents new occurrences and refuses ambiguous recovery rather than claiming it can repair deleted content automatically.
- The nested metadata contract is internal and versioned independently, but immutable template identity still prevents ordinary cross-pin recovery. Retain original checkpoint provenance for separately reviewed operator procedures.
- Additional topology persistence and removal-aware tests add bounded retention-specific complexity. Reuse existing graph evidence and durable state rather than creating a general workflow engine, separate database, or new external dependency.
- Local locks and revalidation do not provide cross-host compare-and-swap. Keep operational single-publisher serialization and independently verified same-server deletion semantics; synthetic scoped deletion does not establish real Forgejo behavior.
