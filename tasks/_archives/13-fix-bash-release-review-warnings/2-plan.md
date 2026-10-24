# Plan

- [Plan](#plan)
  - [Scope](#scope)
  - [Implementation Plan](#implementation-plan)
    - [1. Make prerequisite read failures explicit](#1-make-prerequisite-read-failures-explicit)
    - [2. Enforce the confirmed-tag lifecycle](#2-enforce-the-confirmed-tag-lifecycle)
    - [3. Preserve effective Docker connection selection](#3-preserve-effective-docker-connection-selection)
    - [4. Add focused local regressions](#4-add-focused-local-regressions)
    - [5. Update version and documentation](#5-update-version-and-documentation)
    - [6. Verify and record results](#6-verify-and-record-results)
  - [Acceptance Criteria](#acceptance-criteria)
  - [Risks And Decisions](#risks-and-decisions)

## Scope

Fix B1–B3 from `tasks/12-simplify-bash-release-template/5-code-review.md`, reviewed through `9c25334` and committed as `13f7979`. The current 0.3.0 Bash workflow has a 297-test local baseline, but focused probes reproduced three gaps: a failed conditional registry read permits promotion, a confirmed tag can disappear without blocking later writes, and private auth setup can override a host-only Docker selection.

Keep the jq-free single-command interface, standalone standard-library helper, immutable image/tag/notes identity, conservative startup classification, bounded input/inventory rules, and absence of automatic cleanup. Limit production changes primarily to `scripts/release.sh` and `scripts/release-common.sh`, with small data/auth-helper changes only if necessary to preserve connection metadata. Prepare patch version 0.3.1 during implementation. Do not change identity/configuration schemas, introduce a checkpoint database, refactor the legacy engine, or implement unrelated features.

This task authorizes local implementation and fixture-based verification only when implementation is requested. It does not authorize live publication, source/tag pushes to production, actual Docker daemon operations, credential access, remote repair/reassignment/deletion, old-pin checkpoint adoption, or changes to home-web. This planning stage changes only this file.

## Implementation Plan

### 1. Make prerequisite read failures explicit

- Replace the promotion-time `if [[ $(data resolve ...) != "$prepared" ]]` with an explicitly status-checked read into a named variable, followed by validation and comparison of that same successful result. Use an assignment with an explicit failure branch; do not depend on global `set -e`, an ERR trap, or a command substitution inside a Boolean expression to enforce the read contract.
- Require the successful promotion-time result to be either the captured predecessor or the prepared digest. Promote only from the predecessor; skip a duplicate promotion when the result already equals the prepared digest. A newly observed foreign alias must stop, not merely compare unequal and trigger overwrite. Do not refresh the predecessor from this later read.
- Audit the other conditional substitutions and guard/helper call sites in these two shell files for the same error-to-success pattern. Keep the change narrow: existing final-verification comparisons that already refuse on failed reads may stay, but no prerequisite read may become a mutation decision through empty output or suppressed exit status. If factoring a checked-read helper, propagate failures explicitly even when a caller uses conditional shell syntax.
- Any transport failure, 401/500, malformed/null or contradictory response, byte overflow, or timeout at a prerequisite read stops before the next promotion/release write. An expected route-specific 404 may establish absence only where the current phase permits it; it is not a replacement for uncertain evidence. Keep bounded errors, failed-phase reporting, and private temporary cleanup.
- Preserve `attempt` solely for dispatched mutating commands whose lost responses can be reconciled from fresh matching evidence. Do not wrap failed reads in `attempt`, translate a resource refusal into a transport retry, repeat a confirmed write, or roll back accepted work.

### 2. Enforce the confirmed-tag lifecycle

- Add explicit in-memory tag-confirmation state initialized false for a fresh invocation, or split pre-push and post-confirmation guards with equivalent clear semantics. Set confirmation only after the existing post-push inventory verifies the exact intended object ID, peeled source commit, and expected absence of a release. Object creation, push command exit status, or a display phase string alone must not establish confirmation.
- Before confirmation, retain the existing fresh-publication absence policy and exact-identity conflict checks; do not broaden adoption of an unexpectedly appearing tag. After confirmation, every guard before promotion or release creation must require the exact recorded object and peeled commit. Missing, lightweight, foreign, changed, malformed, or uncertain tag evidence must stop before the next mutation.
- Guard calls must not clear confirmation or overwrite the intended object ID when `tag_state` observes absence. Keep intended identity separate from the freshly observed `remote_oid`/`remote_commit`. Keep source/config/script freshness, complete bounded inventories, release-state checks, and predecessor/prepared alias gates intact.
- An accepted-but-response-lost tag push may establish confirmation only through the same exact remote reconciliation, then proceed under the stricter invariant. A tag that later disappears must not be repushed, recreated by release POST, force-updated, or treated as a fresh publication opportunity. Local deterministic annotation reconstruction remains local only.
- Preserve startup behavior: matching completed tag/release verifies without staging/build/promotion; tag-only or release-only startup states remain ambiguous refusals. The new in-memory state is not a durable journal and grants no automatic recovery to a newly started process.

### 3. Preserve effective Docker connection selection

- Capture the original effective context/host environment before changing `DOCKER_CONFIG`. Treat private registry auth and Docker connection selection as independent concerns. Preserve `DOCKER_HOST`, `DOCKER_TLS_VERIFY`, `DOCKER_CERT_PATH`, and an explicit `BUILDX_CONFIG`, including their intended presence/values; do not replace them with defaults during auth setup.
- Fix the unconditional default-context export: when the caller selected a host without a nonempty `DOCKER_CONTEXT`, do not newly export `DOCKER_CONTEXT=default` over it. An empty context value must not silently become an explicit default override. Preserve an explicitly selected context, including explicit `default` when it intentionally takes precedence over a host value.
- When a non-default context was selected through the original Docker configuration rather than an environment variable, carry that captured selection into the private auth environment and retain its necessary context endpoint/TLS metadata. Keep builder selection and the original buildx directory usable. Do not copy registry auth inventories, credential helpers, or the original Docker config wholesale into the temporary auth directory.
- Ensure platform preflight, context discovery, login, build, and promotion address the same effective daemon/context and selected builder. Keep the caller's working-directory semantics for relative connection paths. No live endpoint may be used to prove this during implementation; fixture ports must model precedence and metadata resolution, not only print a hard-coded default context.
- Keep private permissions, password-stdin, no raw auth logging, bounded output, and normal/signal cleanup. If a named context cannot be safely preserved, refuse before publication mutations rather than fall back to another daemon.

### 4. Add focused local regressions

- Extend `tests/test_bash_release.py` and the owned `tests/fixtures/bash_release_ports.py` ports. Use one-shot faults and explicit injection events at the relevant post-tag/pre-promotion or pre-release I/O boundary. Assert the fault actually fired; do not let a generic earlier refusal make the test pass. Avoid relying exclusively on a hard-coded fifth lookup across the whole run; the review's fifth-lookup probe is a reproduction, not the public API.
- **B1:** Exercise overflow by one byte beyond the 4 MiB bound, malformed JSON, JSON null, 401, 500, transport exit failure, and timeout-equivalent failure at the promotion-decision read after a valid guard. Require nonzero exit, no success message, zero subsequent promotion/release POST, unchanged predecessor/latest, and no rollback/deletion. Include an already-prepared alias that skips promotion and a successful but foreign later alias that must not be overwritten. Preserve the existing post-write overflow case: if promotion already happened, later failure must leave that accepted alias intact and stop before release POST.
- **B2:** Use real owned local Git/bare-remotes. Allow push and its first exact confirmation, then remove only the fixture tag before the next promotion guard; require zero promotion/release POST after disappearance. Add the complementary removal after successful promotion but before the release guard; require no release POST, tag repair, repeated promotion, or rollback, with the prepared alias left intact. Cover a changed object, lightweight replacement, or wrong peeled commit as refusals. Record/assert operation ordering around the injection, immutable intent, and unchanged previously completed steps.
- **B3:** Teach the fake Docker port to derive effective selection from environment precedence and synthetic config/context metadata, then log only nonsecret selection identifiers. Test host-only selection with unset and empty context, non-default context from original config, explicit named context overriding a host, explicit default context overriding a host, and ordinary local default. Include synthetic TLS variables and explicit/default buildx paths. Assert the same effective endpoint/builder across preflight, login, build, and promotion, not merely that DOCKER_HOST remains somewhere in the environment.
- For named-context cases, create minimal test-owned endpoint/TLS metadata and an original config containing fake unrelated auth/helper sentinels. Verify needed connection metadata remains usable in the private directory while auth/helper sentinels are not copied, the token stays on stdin/private files rather than logs/arguments, and only run-owned temporaries are cleaned. Never read real Docker config, TLS keys, or the default token.
- Retain normal one-build/digest-promotion publication, same-identity completed retries without staging, unbound staging reuse, accepted-but-response-lost write reconciliation, strict config/notes, resource budgets, locks/signals, source/remote refusals, legacy installer separation, and zero automatic link/delete/prune operations. Add regressions before fixes and record meaningful failing-before/passing-after results for each warning.

### 5. Update version and documentation

- During implementation, bump root `VERSION` and `release_template.__version__` from 0.3.0 to 0.3.1. Add project-focused `docs/releases/0.3.1.md` with the matching version heading and TOC, and point `scripts/release.json` at it. Keep earlier notes, archived evidence, legacy examples, Dockerfile, and image name unchanged unless a narrowly necessary documented correction is discovered.
- Update the concise README version/release link, `docs/bash-publication.md` for explicit checked reads and post-confirmation tag invariants, `docs/bash-configuration.md` for host/context/TLS precedence preservation, and `docs/verification.md` for the actual new scenarios and test boundaries. Do not claim actual daemon routing or live 0.3.1 publication from fake-port results.
- Preserve Bash configuration schema 1 and `container-release-bash/1` serialization/fields, legacy formats and pin checks, bounded helper limits, and project-only release bodies. A changed source/config/script hash remains a different identity, not permission to adopt or rewrite an existing transaction.

### 6. Verify and record results

- Establish the current 297-test baseline before production edits. Run focused new regressions against the pre-fix behavior, then after each fix, followed by `python3 -B -m unittest discover -s tests -q`. Allow the full suite more than two minutes; the previous review took 144.222 seconds. Do not skip legacy or slow cases to hide failures.
- Run Python syntax checks, individual `bash -n` checks for every shell file, strict settings/version/note agreement, all six legacy example validations, Markdown TOC/file-link checks, and `git diff --check`. Run root Bash `--validate`, generic legacy validation, and Ubuntu legacy validation serially; test dependency-free help. ShellCheck is optional if already installed; record absence without installing anything.
- Confine token files, Docker settings/TLS placeholders, response streams, event logs, tag deletion/replacement, and fault injection to newly created owned temporary fixtures, preferably under `/tmp/opencode`. Do not access production credentials/services, run the real Docker daemon, prune this repository, modify preserved live checkouts, or invoke a real release.
- Write `tasks/13-fix-bash-release-review-warnings/4-implemented.md` mapping B1–B3 to code/tests, actual failing-before/passing-after evidence, final commands/counts, compatibility limits, preserved resources, and absence of live verification. Follow the implement workflow by creating a new branch named exactly `13-fix-bash-release-review-warnings`, updating relevant docs/version, and committing when implementation is requested. Do not change `todo.md`, old goals/reviews/results, or task 12's plan to make old evidence appear fixed retroactively.

## Acceptance Criteria

- B1: Every prerequisite read used to decide promotion/release creation has its status checked explicitly. Faults at the previously vulnerable conditional lookup cause nonzero exit and zero later publication writes; a fresh foreign alias is not overwritten. Confirmed prior writes are not rolled back.
- B2: After the exact tag is confirmed, subsequent promotion/release guards require that same object and peeled source commit. Disappearance or conflicting evidence stops before the next write, without implicit repush/repair/release auto-tag authority. Pre-push absence, exact lost-response reconciliation, and conservative startup behavior remain distinct.
- B3: Private auth isolation preserves the caller's effective host/context/TLS and builder selection. All configured fixture matrix cases use the same effective connection throughout, while keeping credentials private and avoiding original auth/helper inventory copying.
- Normal no-argument publication, immutable digest/notes/tag identity, completed no-write retry, single build/digest promotion, input/inventory bounds, legacy pin/installer refusal, and signal/private-temp cleanup regressions pass. No schema migration, new journal, automatic package reassignment, deletion, or privileged platform setup is introduced.
- Version/settings/docs agree on prepared 0.3.1. Local verification is recorded honestly; earlier release notes/evidence, live resources, historical checkouts, other projects, and `todo.md` remain untouched. This planning stage creates only this plan and its commit.

## Risks And Decisions

- Bash conditional contexts can suppress errexit across function calls, not only inside one substitution. Explicit status propagation is the safety boundary; adding more `set -e` options or traps is not a remedy. A read failure and an uncertain already-dispatched write need different handling.
- In-memory tag confirmation closes an observed-state gap without pretending cross-service writes are atomic. It does not survive process restart, enforce server-side exclusion, refresh predecessor authority, or make automatic repair safe. Operator-controlled single-writer exclusion remains necessary.
- Docker connection precedence is not equivalent to preserving environment strings: a newly exported default context can override an unchanged host. The fixture must model effective selection, including empty values and config-selected contexts, while never connecting to its synthetic endpoints.
- Extending the existing data helper is preferable to introducing a second auth/config framework, but only if required for this narrow fix. Keep the default jq-free and independent of the legacy engine; retain existing byte/page/time budgets and safe credential handling.
- Preparing a new patch pin does not make it compatible with already captured source/config/script identities. A future live 0.3.1 experiment requires separate explicit target/version/source/image/release approval; never substitute new code into an old checkpoint or alter published tags to force recovery.
