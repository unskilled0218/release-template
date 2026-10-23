# Implementation results

- [Implementation results](#implementation-results)
  - [Outcome](#outcome)
  - [Changes](#changes)
  - [Verification](#verification)
  - [Limits and operational gates](#limits-and-operational-gates)
  - [Version and repository workflow](#version-and-repository-workflow)

## Outcome

Implemented the approved plan on the new branch `2-fix-release-review-warnings`. Both original branch-review warnings have code changes and regression coverage: preserved references protect their manifest dependencies, and verification classifies every runnable image instead of filtering to supported architectures. P1 transaction-relative survivors and P2 immutable checkpoint identity are covered explicitly. No consumer project or live service was changed.

## Changes

- Added `release_template/oci.py` as a shared pure classifier for publication and cleanup. Runnable image classification no longer depends on the configured architecture allowlist. Explicit supported Buildx attestations and empty-config OCI artifacts remain distinguishable from images; malformed or contradictory evidence fails closed.
- Extended registry graph evidence with immutable manifest identities, configurations, incoming descriptor contexts, platform/media-type evidence, and subject relationships. Shared-node fetch deduplication retains incoming edges. Verification checks the complete runnable platform multiset, rejects duplicates/extras, validates descriptors, and checks source/version/revision labels. Subject-only dependencies stay reachable without adding publication platform members.
- Refactored cleanup into inventory collection, eligibility classification, survivor graph protection, candidate selection, and fresh saved-inventory validation. Preserved aliases, uncertain digest roots, and same-name records outside repository deletion authority protect complete graphs, including content from completed older runs. Unknown or unavailable protection evidence cannot authorize deletion.
- Bound deletion authority to exact pending candidates rather than general retention eligibility. Newly introduced older aliases, recreated completed references, and changed candidate identities cannot silently expand a saved transaction. Fresh checks run before saved-plan processing and between operations; aliases retire before backing digests even for differently ordered saved inventories. Confirmed absence and lost deletion responses remain retryable.
- Applied all-runnable ownership/version checks to historical digest eligibility, including subject dependencies. Artifact-only, malformed, missing-label, foreign-source, or non-older evidence cannot be accepted by checking only the AMD64/ARM64 subset.
- Kept `State` identity checks, workflow identity construction, stable launcher, and Bash bootstrap unchanged. CLI regressions verify that upgraded template revisions reject old-pin checkpoints without registry login, checkpoint changes, or remote mutation; same-revision cleanup retries remain supported. Legacy-shaped inventory fixtures do not claim cross-revision adoption support.
- Updated the fake registry to use real platform/label verification and evidence records. Added realistic loopback OCI fixtures and 24 regression test methods spanning both warnings and both plan-review findings.
- Updated README plus configuration, retention, verification, installation, and publication documentation. Documented supported artifact forms, transaction-relative protection, checkpoint upgrade boundaries, and the unchanged live deletion gate.

## Verification

- Before implementation, three focused regression methods failed against the previous code, producing ten failures including subtests: extra runnable architecture acceptance, skipped-alias backing-digest selection, and saved-plan deletion despite a newly introduced older alias.
- After implementation, `TMPDIR=/tmp/opencode python3 -B -m unittest discover -s tests` passed all 83 tests in 19.387 seconds. This includes existing publication/recovery, source/tag identity, pagination, staging, abandonment, installer/update, locking, and credential-isolation coverage.
- New retention checks cover both inventory orders; complete older checkpoints; unknown/prerelease/newer/external-staging aliases; nested real OCI graphs and attestations; uncertain digest roots; foreign/missing associations; old-shaped matching-identity inventories; aliases introduced before and between digest deletions; recreated completed references; changed pending aliases; malformed/unavailable inventories; lost alias-deletion responses; and positive unreferenced-digest deletion controls.
- New OCI checks cover extra or unlabeled runnable architectures, missing/unknown platforms, missing/conflicting labels, duplicate platforms/descriptors, shared-node descriptor conflicts, OCI artifacts, explicit Buildx attestations, contradictory markers, subject-only dependencies, and Docker schema-2 images. Cleanup ownership tests include foreign, missing, and newer labels outside the supported architecture subset.
- CLI checks distinguish old-pin rejection for `resume`, `cleanup-plan`, and `cleanup` from successful idempotent same-revision staging retirement. Checkpoint bytes and remote state remain unchanged on revision rejection.
- `bash -n scripts/release.sh` and `git diff --check` passed. All Python sources under `release_template`, `scripts`, `tests`, and `examples/hooks` parsed successfully without generating bytecode.
- All five example configurations passed credential-free launcher validation: Cargo, explicit, Node, suite, and version-file. Validation selected a nonexistent fixture token path and did not read credentials.
- `VERSION`, `release_template.__version__`, and README agree on `0.1.1`. A diff check confirmed no changes to `scripts/launch.py`, `scripts/release.sh`, `release_template/state.py`, or `release_template/workflow.py`.

## Limits and operational gates

- Tests use disposable local repositories/checkpoints, loopback HTTP, and synthetic adapters. No real Docker build, Forgejo publication, push, remote creation, package deletion, or installation into an existing consumer project was performed. These tests do not establish live Forgejo deletion behavior or runtime multi-platform execution.
- Destructive cleanup still requires independently verified same-server disposable-test evidence. No production attestation was supplied or generated. Local locks and fresh checks still require operational single-publisher serialization across hosts.
- Artifact support is deliberately conservative. Unsupported encodings can stop verification or preserve historical content. Additional evidence reads and retained ambiguous records are intentional safety costs.
- Upgrading a pin does not migrate an old revision-bound checkpoint. Preserve its original state/provenance for separately reviewed handling; no identity rewrite, old-code cleanup workaround, or cross-revision adoption command was added.
- Existing goal, plan, and review artifacts were not changed during implementation. The unrelated untracked `todo.md` was left untouched and is not part of the implementation commit.

## Version and repository workflow

Created the new branch with the exact task-directory name, `2-fix-release-review-warnings`, rather than reusing an existing branch. Updated patch version `0.1.0` to `0.1.1` according to the existing version-file, module, and README convention. The implementation commit contains only scoped code, tests, documentation, version updates, and this results file; no remote publication is authorized or performed.
