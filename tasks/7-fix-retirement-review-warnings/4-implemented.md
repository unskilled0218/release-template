# Implementation Results

- [Implementation Results](#implementation-results)
  - [Outcome](#outcome)
  - [Changes](#changes)
  - [Verification](#verification)
  - [Plan Decisions and Deviations](#plan-decisions-and-deviations)
  - [Remaining Limits](#remaining-limits)

## Outcome

Implemented D1 and D2 on the new branch `7-fix-retirement-review-warnings`, created from `bef17df`. Version is `0.2.2`. Abandonment now records completion only after consistent package/registry absence, and deletion authorization validates verification timestamps against explicit UTC freshness limits.

## Changes

- `release_template/cleanup.py`: added `validate_evidence_time` with inclusive 30-day maximum age and 300-second future tolerance. It accepts only valid `YYYY-MM-DD` or `YYYY-MM-DDTHH:MM:SSZ` values, treats dates as midnight UTC, reads the default clock at call time, and supports explicit time for deterministic tests. Invalid dates, expired evidence, and excessive future skew raise bounded errors without echoing supplied content. Validation runs before the runtime version request and deletion through the existing evidence gate.
- `release_template/cleanup.py`: extracted `retire_abandoned_alias` to always consult the scoped package endpoint, enforce existing digest/association checks, reject inconsistent presence, and require package plus registry absence after DELETE. Both-absent retries reconcile without DELETE. Any uncertain confirmation stops subsequent aliases and leaves the affected checkpoint unmarked; each completed run retains independent durable progress.
- Existing outputs, staging digests, operations, cleanup metadata, publication state, and graph-protection rules are preserved. Existing abandonment flags do not bypass fresh remote validation. No raw-digest retirement, rebuild, cross-pin adoption, or checkpoint repair path was added.
- `tests/test_evidence_time.py`: added nine test methods covering exact UTC formats, valid/invalid calendar values, inclusive age/skew limits and one-second failures, bounded errors, runtime clock lookup, gate rejection before version requests/deletion/checkpoint writes, expired saved-plan retry, exact-version binding, unchanged evidence bytes, and evidence-free read-only planning.
- `tests/test_gitea_absence.py`: added fourteen abandonment test methods using real Gitea status/JSON decoding over injected transport. Cases cover no-op successful deletion, invalid/null/non-object/raw malformed confirmation, authentication/server/connectivity errors, inconsistent API/registry views, changed digest/association, lost responses, checkpoint interruptions, repeated invocation, existing abandonment flags, multi-alias stopping/retry, multi-run progress, graph preservation, and no duplicate confirmed deletion or image rebuild. The transport now supports raw bytes for malformed-JSON faults without replacing production decoding.
- `tests/test_cli.py`: added a nonzero abandonment-confirmation failure regression retaining the publication-success/cleanup-incomplete diagnostic and selected checkpoint.
- `tests/support.py`: synthetic evidence now uses a fresh UTC-second timestamp, with an explicit verification-time override for boundary scenarios. No production attestation is generated.
- `VERSION`, `release_template/__init__.py`, and `README.md`: updated consistently to `0.2.2`. Relevant retention, migration, verification, and publication documentation now describes freshness rules, confirmation/retry behavior, and operational limits.

## Verification

- Passed `python3 -B -m unittest tests.test_evidence_time tests.test_gitea_absence tests.test_cli -v`: 39 tests in 3.232 seconds after correcting test placement during development.
- Passed `python3 -B -m unittest discover -s tests -v`: 165 tests in 41.142 seconds. This includes all 141 original test methods and 24 additions; no baseline test method was removed.
- Passed `bash -n scripts/release.sh`.
- Passed `python3 -B scripts/launch.py validate --config examples/explicit.json`: configuration valid, with no credentials or remote operations.
- Passed `git diff --check`.
- Passed explicit version agreement and changed-document table-of-contents anchor checks, excluding fenced code examples from heading detection.
- Confirmed unchanged bootstrap/updater scripts and unchanged state, policy, workflow, and adapter modules. Production changes are limited to cleanup behavior and release version metadata; configuration, evidence, checkpoint, and retirement schemas remain unchanged.

## Plan Decisions and Deviations

Implemented the reviewed freshness policy as proposed: 30 × 86,400 seconds maximum age and 300 seconds maximum future skew, both inclusive. Freshness is checked when entering the cleanup/abandon evidence gate, not before every DELETE. Date-only evidence retains compatibility with the existing format but expires relative to midnight UTC.

Used the plan's permitted dedicated `tests/test_evidence_time.py` module rather than extending migration tests with the full timestamp matrix. Added a narrow raw-byte test transport seam as identified in plan review. There are no material scope or behavioral deviations from the plan.

## Remaining Limits

- Live Gitea/Docker publication, storage deletion semantics, registry read-after-write behavior, platform runtime pullability, and filesystem power-loss durability remain unverified. Faults are local transport/fake-registry simulations and abrupt exceptions, not deployment certification.
- Strict package/registry agreement may block on eventual consistency; explicit retry after convergence is required. There is no polling, automatic force bypass, rollback, or atomic transaction across aliases/runs.
- Timestamp freshness cannot prove operator claims or detect storage changes. Expiry requires new disposable verification results rather than redating old evidence, and storage changes require immediate reverification even inside the age window.
- Exact-pin checkpoint refusal remains in force. Old falsely completed checkpoints are not repaired automatically; preserve provenance for separately reviewed recovery.
- No live servers, real tokens, existing consumer installations, Git pushes, image/release publication, or remote deletion were used. `todo.md` remains untouched and excluded from this commit.
