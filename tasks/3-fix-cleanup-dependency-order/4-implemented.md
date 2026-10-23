# Implementation results

- [Implementation results](#implementation-results)
  - [Outcome](#outcome)
  - [Changes](#changes)
  - [Verification](#verification)
  - [Limits and operational gates](#limits-and-operational-gates)
  - [Version and repository workflow](#version-and-repository-workflow)

## Outcome

Implemented B1 remediation on the new branch `3-fix-cleanup-dependency-order`. Cleanup now durably records dependency-aware retirement order before its first deletion and retires authorized referring manifests before candidate dependencies. Removal-aware tests demonstrate completion and restart without the missing-child traversal failure. Current publication, survivor protection, immutable checkpoint identity, and the independent live deletion gate remain intact.

## Changes

- Added focused pure retention helpers inside `release_template/cleanup.py` for immutable candidate projections, deterministic referring-manifest-first topological sorting, retirement fingerprints, and nested schedule validation. Candidate keys include image name and digest. Transitive membership/subject reachability includes intermediates without package records; shared children wait for every candidate parent. Cycles, malformed identities, duplicate nodes, and bounded-input violations stop retirement.
- Added nested `cleanup.retirement` metadata with `schema`, `run`, `fingerprint`, `graphs`, and `order`. Its fingerprint binds immutable candidate identities and reachability, not mutable completion flags. Read-only planning returns the proposed schedule without writing state; apply durably saves inventory and schedule before alias, release, or digest deletion. Existing schedules are validated and preserved rather than silently replaced after progress.
- Separated package record collection and exact absence checks from graph traversal. Confirmed-absent candidates can complete without another DELETE or traversing a retired parent. Package DELETE success is confirmed absent through the scoped API before completion flush. Dependency retirement additionally requires recorded parents to be complete and absent from the fresh inventory.
- Preserved full fresh graph collection, publication verification, ownership/version checks, unfinished-run protection, and transaction-relative survivors between destructive operations. Live pending raw graphs must match approved reachability. Saved topology never substitutes for survivor evidence or grants additional candidate authority.
- Added conservative initialization for intact matching-identity old-shaped inventories without retirement metadata. Missing/completed raw candidates or broken graphs require explicit operator recovery; alias-only inventories use an empty schedule. Cross-revision checkpoint adoption is still unsupported. `State`, workflow identity construction, OCI classification, and stable bootstrap files are unchanged.
- Added `tests/test_retirement.py` with six pure policy tests and 21 removal-aware local integration methods. The fixture uses the real loopback registry adapter, durable `State`, and scoped synthetic package deletion that actually removes manifest content. Existing workflow tests now explicitly construct reversed saved candidates and derive unrelated deletion order from the schedule rather than assuming planner array positions.
- Updated README and retention/publication/verification documentation, including the exact nested metadata contract, bounds of 10,000 candidates and 100,000 stored reachability references, safe retries, and legacy-state limitations.

## Verification

- Before the fix, the new child-first regression failed with `Required registry content is absent` after child removal. Its companion fixture test passed by proving that deleting a child genuinely makes an undeleted parent unreadable. This reproduces B1 without the permissive workflow fake.
- Final `TMPDIR=/tmp/opencode python3 -B -m unittest discover -s tests`: all 110 tests passed in 32.642 seconds, including all 83 preceding tests and 27 new retirement tests. Existing publication/recovery, platform verification, staging, abandonment, credential isolation, installer/update, and identity-bound CLI retry tests remain passing.
- Dependency coverage includes child-first/reversed/shuffled inventories, nested indexes, shared children, unlisted intermediates, subject relationships, preserved attestations, independent nodes, image-scoped identical digests, and cycle/shape/bound rejection.
- Restart coverage injects lost deletion responses, termination before completion flush, and termination after completion flush at each of four related digest deletions, for 12 fault/restart scenarios. Each reopens durable state, retains the exact approval metadata, completes without duplicate DELETE for confirmed-absent targets, and re-verifies current publication. Separate tests interrupt before and after initial schedule persistence with zero premature deletions.
- Safety coverage includes malformed metadata, internally consistent but incomplete reachability compared against actual graphs, recreated completed parents, new unknown/older/foreign survivors, changed association, authentication failure, inconsistent absence, intact legacy initialization, alias-only legacy state, and rejection of ambiguous partial legacy inventories without checkpoint modification.
- Python syntax checks passed for sources under `release_template`, `scripts`, `tests`, and `examples/hooks`. All five example configurations passed credential-free launcher validation with a nonexistent fixture token path. No credential read was required by validation.
- `bash -n scripts/release.sh`, `git diff --check`, Markdown header/table-of-contents checks for README and documentation, and version consistency checks passed. `VERSION`, `release_template.__version__`, and README agree on `0.1.2`.
- A diff check confirmed no modifications to `scripts/launch.py`, `scripts/release.sh`, `release_template/state.py`, or `release_template/workflow.py`. Previous goal, plan, and plan-review artifacts were not modified during implementation.

## Limits and operational gates

- Tests use disposable files, loopback HTTP, and synthetic scoped deletion. No real Docker build, Forgejo publication/deletion, remote creation, push, production credential access, or installation into an existing consumer project occurred. Simulated termination exceptions are not filesystem power-loss or real server contract tests.
- The same-server disposable-verification attestation gate is unchanged. No production attestation was generated or supplied. Local locking and fresh checks still require operational single-publisher serialization across hosts.
- Saved topology is local checkpoint evidence, not a signature or proof of current ownership. Fresh survivors can stop previously approved progress. Unavailable/inconsistent API evidence and already-broken legacy graphs remain fail-closed; no deleted content is reconstructed automatically.
- Template upgrades still cannot load old revision-bound checkpoints. Original identity/provenance must be retained for separately reviewed handling; no identity rewrite, automatic adoption, or vulnerable old-code cleanup workaround was added.
- The unrelated untracked `todo.md` was left untouched and is excluded from the implementation commit.

## Version and repository workflow

Created a new branch whose name exactly matches the task directory, `3-fix-cleanup-dependency-order`, without reusing an existing branch. Updated patch version `0.1.1` to `0.1.2` using the existing version-file/module/README convention. The implementation commit includes only scoped code, tests, documentation, version updates, and this results file. No remote publication is performed.
