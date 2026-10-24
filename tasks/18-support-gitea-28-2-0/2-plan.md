# plan

- [plan](#plan)
  - [Scope](#scope)
  - [Implementation plan](#implementation-plan)
    - [1. Establish the version-specific contract](#1-establish-the-version-specific-contract)
    - [2. Extend the guarded version check](#2-extend-the-guarded-version-check)
    - [3. Add regression coverage](#3-add-regression-coverage)
    - [4. Update reusable reference documentation](#4-update-reusable-reference-documentation)
    - [5. Validate and record results](#5-validate-and-record-results)
  - [Acceptance criteria](#acceptance-criteria)
  - [Risks and decisions](#risks-and-decisions)

## Scope

Support new package association writes on exact stable Gitea `28.2.0` while retaining existing stable `1.25.x` support and all current association safeguards. Changes belong in `scripts/release-data.py`, existing association tests/fixtures, and active reference documentation. Do not change publication ordering, credentials, configuration schema, unrelated projects, archived evidence, or `todo.md`. This planning stage modifies only this document and commits it; it performs no implementation changes or live writes.

## Implementation plan

### 1. Establish the version-specific contract

- Review the upstream `v28.2.0` tag before implementation and record its resolved commit and permanent source references in `docs/bash-publication.md`. Check `routers/api/v1/api.go`, `routers/api/v1/packages/package.go`, `modules/structs/package.go`, repository identity conversion, `services/convert/package.go`, `services/packages/package_update.go`, and `models/packages/package.go` for routes, middleware/permissions, response fields, and association semantics.
- Planning inspection found that [`LinkToRepository`](https://github.com/go-gitea/gitea/blob/v28.2.0/services/packages/package_update.go) rejects nonzero `RepoID`, requires matching owners, and checks package-unit write permission. The [API handler](https://github.com/go-gitea/gitea/blob/v28.2.0/routers/api/v1/packages/package.go) maps an existing-link refusal to HTTP 400 and returns empty HTTP 201 on success. The [converter](https://github.com/go-gitea/gitea/blob/v28.2.0/services/convert/package.go) can hide an inaccessible repository as null. The [model update](https://github.com/go-gitea/gitea/blob/v28.2.0/models/packages/package.go) does not condition its write on an unlinked row. Preserve operator-enforced exclusion of all other association writers, including UI actions and in-flight requests.
- Confirm the current helper's repository/package identity checks and bodyless POST followed by exact read-back match that contract. Keep the named container version `/latest`, not the separate `/-/latest` endpoint. If further inspection contradicts any required safety assumption, stop before widening the gate and record the blocker instead of bypassing it.
- The earlier live version response was `28.2.0`; the planning-time unauthenticated GET to `https://git.lan/api/v1/version` failed to connect. Treat neither that historical response nor upstream source as proof of current deployed package behavior. Do not access real tokens or perform authenticated live experiments under this plan.

### 2. Extend the guarded version check

- Update the narrow check inside `package_association` in `scripts/release-data.py` to accept existing stable `1.25.x` strings or exact `28.2.0`. Keep strict object/string validation and whole-string matching. Do not allow all `28.x`, `28.2.x`, newer versions, development builds, suffixes, or arbitrary numerically greater versions.
- Update the nearby safety comment and bounded refusal message to name both supported contracts without echoing server-controlled values. Keep `1.25.x` validation unchanged, including rejection of leading-zero patch numbers.
- Preserve the early read-only return for a correct association, the `ensure` requirement, refreshed repository/package evidence, one POST at most per invocation, transport-loss reconciliation, and exact post-link read-back. Never unlink, reassign, delete, roll back accepted publication, or turn failed/malformed reads into permission to write.

### 3. Add regression coverage

- Extend `BashDataTests` in `tests/test_bash_release.py` to exercise supported versions through actual `package_association` control flow rather than testing only a version predicate. Cover exact `28.2.0` and representative existing `1.25.x` values, including empty 201 success and accepted-but-lost transport reconciliation. Assert request order, bodyless POST route, refreshed evidence, and one POST at most.
- Expand unsupported-version cases to include `28.2.1`, `28.1.0`, `28.3.0`, `29.0.0`, `28.2`, `v28.2.0`, `28.2.00`, `28.2.0-dev`, `28.2.0+custom`, whitespace, non-string values, and malformed documents, alongside existing `1.24.6`, `1.26.0`, and `1.25.x` lookalikes. Assert no POST and no raw remote value in diagnostics.
- Parameterize or extend `BashPackageAssociationTests` to run the meaningful association safety scenarios on `28.2.0` as well as retained `1.25.0`: fresh unlinked publication, existing correct/conflicting links, permission-hidden foreign links, completed missing-link retry, lost POST response, refreshed identity failures, and post-link verification failure. Assert foreign links remain unchanged, no unlink/delete occurs, and retries do not repeat build, promotion, tag push, or release creation.
- Verify unknown servers still allow an already-correct association without requesting server version, while unlinked packages on those servers cannot authorize a POST. Update the existing error-message assertion without weakening its safety assertions.
- Reuse `gitea_version` in `tests/fixtures/bash_release_ports.py`; retain explicit coverage of both supported contracts rather than changing the default and silently dropping old-version coverage. Add fixture behavior only if the reviewed source requires it. Describe fake-server refusal behavior as a model of the upstream contract, not independent live proof.

### 4. Update reusable reference documentation

- Update the active support statements in `README.md`, `docs/bash-configuration.md`, `docs/bash-publication.md`, `docs/release-process.md`, and `docs/verification.md` to say stable `1.25.x` and exact stable `28.2.0`, not unrestricted `28.x` support.
- Keep README concise. Put source references, permission-hidden null behavior, package-wide link effects, HTTP 400 existing-link refusal, empty 201/read-back expectations, and the non-atomic concurrency limitation in the existing dedicated publication/configuration documentation.
- Explain how downstream projects should review an exact server contract, extend a narrow allowlist, run regressions, and distinguish local tests from separately approved deployment checks. Explain unsupported-version recovery without recommending a blind gate removal, TLS bypass, package reassignment, or an unapproved retry after uncertain writes.
- Preserve historical release notes and archived task records. If the implementation workflow requires a version bump, update root `VERSION`, README, configured notes path in `scripts/release.json`, and new versioned release notes together; do not change them during planning or claim a release was published.

### 5. Validate and record results

- Run `python3 -B -m unittest discover -s tests -v`, syntax-check each `scripts/*.sh` with `bash -n`, run `./scripts/release.sh --validate`, and run `git diff --check`. Use owned temporary fixtures and no real credentials, Docker daemon, or publication.
- Check active Markdown links/TOCs and search active code/docs for obsolete exclusive `1.25.x` support claims, excluding historical notes and task archives. Inspect the final diff for unexpected settings, safety, or publication-sequence changes.
- Record changed files, exact source provenance, commands/results, and any unresolved blockers in this task's `4-implemented.md` during implementation. Report local fixture coverage separately from upstream source inspection and live evidence. Do not claim live API, permissions, Packages-tab UI, or writer-exclusion verification without a separately authorized experiment.

## Acceptance criteria

- Exact stable `28.2.0` can authorize one new association only after valid identities, explicit nullable association evidence, the supported-version check, and refreshed prerequisites. Stable `1.25.x` behavior remains supported.
- Every other version and invalid version response fails closed for a new link. Already-correct links remain read-only without a version gate.
- Visible and permission-hidden foreign links are never reassigned. Null alone does not authorize writes on an unsupported server. One invocation never repeats an uncertain POST; accepted publication and associations remain intact after failures.
- Both supported contracts have explicit local regression coverage for successful association and safety-critical refusal/recovery behavior. All local checks pass.
- Active documentation names exact support boundaries, links version-specific source evidence, retains concurrent-writer exclusion, and states that deployed behavior remains unverified by local tests.

## Risks and decisions

- Support `28.2.0` exactly; do not infer compatibility for other `28` releases. Keep the existing `1.25.x` policy rather than broadening or removing it.
- Upstream source evidence supports a compatibility extension, not certification of an identically versioned customized server. A later approved live check must establish the actual target, source/version, credentials/permissions, disposable package/repository scope, and writer exclusion before mutations.
- Existing-link refusal is not an atomic compare-and-set. Client read-back and the checkout lock cannot prevent concurrent external reassignment. Writer exclusion remains an operator prerequisite, not a new guarantee supplied by this change.
- Association currently happens after publication. A rejected or unavailable server can leave publication accepted but linking incomplete; preserve that ordering and existing recovery rather than expanding this task into preflight or rollback redesign.
