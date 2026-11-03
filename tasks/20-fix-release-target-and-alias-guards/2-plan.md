# plan

- [plan](#plan)
  - [Scope](#scope)
  - [Implementation Plan](#implementation-plan)
    - [Summary](#summary)
    - [1. Validate the complete effective push destination set](#1-validate-the-complete-effective-push-destination-set)
    - [2. Enforce the confirmed-promotion invariant](#2-enforce-the-confirmed-promotion-invariant)
    - [3. Add focused boundary regressions](#3-add-focused-boundary-regressions)
    - [4. Update current documentation and version metadata](#4-update-current-documentation-and-version-metadata)
    - [5. Verify and record results](#5-verify-and-record-results)
  - [Acceptance Criteria](#acceptance-criteria)
  - [Risks and Decisions](#risks-and-decisions)

## Scope

Implement the goal in `1-goal.md`: resolve F1 and F2 from `tasks/19-code-review/code-review.md`. Change only release destination validation, the post-promotion alias invariant, their test fixtures/regressions, and directly affected current documentation/version metadata. F3–F5, historical records, `todo.md`, live publication, and unrelated refactoring remain outside scope. This planning task changes no implementation code.

## Implementation Plan

### Summary

Reject unsupported Git push fan-out before any publication write. Track successful promotion confirmation as a one-way in-memory transition, after which every fresh alias guard requires the prepared digest. Preserve bounded reads, source/tag identity, conservative retries, accepted remote state, and no-repair/no-rollback behavior.

### 1. Validate the complete effective push destination set

- Update `source()` in `scripts/release-data.py` to obtain push destinations using `git remote get-url --push --all origin` through the existing bounded Git helper. Git must perform its normal `insteadOf`/`pushInsteadOf` expansion and fallback from absent push URLs to ordinary remote URLs.
- Require exactly one effective push URL before normalization. Reject empty output, multiple entries, duplicate entries, malformed output, and command/decoding failures; do not silently deduplicate or accept several matching destinations. This template supports one push endpoint, not distributed publication.
- Validate that single URL with the existing `remote_key()` rules and configured host/repository checks. Preserve credential-free HTTPS, supported SSH forms, `.git` normalization, and the existing independent SSH-port policy.
- Keep validation of the first effective fetch URL, since reads use that endpoint. Keep clean `main`, ignored-state checks, captured commit matching, and exact remote-main advertisement unchanged. Additional ordinary URLs cannot escape push validation when Git uses them as its fallback push set.
- Keep this validation inside `source()` so startup and subsequent `scan()` calls apply it. Refuse initial invalid configuration before credential preparation, staging lookup, build, or tag push; a later detected change must block the next publication write.
- Retain the existing non-force exact-object tag push. Do not change remote configuration, select a convenient URL from a larger set, print destination values, or send exploratory pushes.

### 2. Enforce the confirmed-promotion invariant

- Initialize `promotion_confirmed=false` alongside `tag_confirmed=false` in the fresh-publication path of `scripts/release.sh`. Keep it distinct from tag confirmation and diagnostic publication state.
- Capture and check the post-promotion `latest` read explicitly. Set `promotion_confirmed=true` only after a successful read proves equality with `prepared`, including when promotion was skipped because the alias already matched or a lost promotion response was reconciled. Never reset this flag during the invocation.
- Update `alias_guard()` in `scripts/release-common.sh`: before confirmation, retain predecessor-or-prepared permission; after confirmation, require exactly `prepared`. Keep a checked assignment with an explicit failure branch so failed reads cannot authorize continuation in conditional Bash callers.
- The existing `fresh_guard` before release POST must run the strict branch after confirmation. Its first observed predecessor, absent alias, foreign digest, or failed/malformed/oversized read must stop without a later permissive retry. Do not add a permissive read followed by a second read that could erase an observed contradiction.
- Preserve source/inventory/tag checks, pre-promotion alias selection, completed-publication verification, package association guards, and transport-only write reconciliation. A refusal must not refresh the predecessor, repromote, repush, delete, or roll back anything.

### 3. Add focused boundary regressions

- Extend `tests/test_bash_release.py` and `tests/fixtures/bash_release_ports.py` only as needed. Existing fake `get-url` handling always returns one URL, so add an opt-in fixture mode for complete push-list output, read failures, and a later configuration change without changing normal fixture behavior.
- Add real-Git helper tests using owned repositories and isolated Git configuration/environment. Run the actual destination-validation path with real `get-url` output; `source(..., remote=False)` may omit remote-main lookup for these offline cases. Cover two explicit push URLs, two ordinary URLs with no push URL, duplicate matching URLs, and an allowed first URL followed by an invalid/foreign URL. Do not replace destination enumeration with a mock in these tests.
- Verify real Git URL rewriting for `insteadOf` and `pushInsteadOf`, including a rewrite to a foreign target that must be refused. Keep positive single-destination HTTPS, SCP-style SSH, and SSH URL cases, with and without explicit push URLs. No network lookup is needed for URL expansion.
- Add full-entry refusal cases proving that invalid or failed push-list evidence causes nonzero exit, no success output, and no build, tag push, promotion, release POST, or package link. Assert owned remotes remain unchanged. Add a configuration-change injection after build but before tag dispatch; require no subsequent tag/promotion/release/link writes and preserve the already-built staging image.
- For F2, seed a nonempty predecessor and add a one-shot alias mutation at the release guard's first `latest` read after successful promotion verification, not before the confirmation read. Record a named injection event and require it to occur before refusal. Use a phase-local fixture counter/event rather than a global request number.
- Cover predecessor reversion, disappearance, foreign digest, and a representative failed post-confirmation read. Require nonzero exit, no success summary, zero release POST/package-link events after injection, exactly one tag push and promotion, unchanged intended tag annotation, no repairs, and preservation of the injected alias state and staging content.
- Cover confirmation without an actual promotion write: retain the existing already-prepared success case, and add a post-confirmation reversion case on that path. It must refuse with zero promotion writes and no release creation. Retain successful accepted-but-response-lost promotion reconciliation and completed read-only retry cases.
- Add small shell-helper checks for both phases and read failures, including calls inside a Bash conditional. Update their setup to provide the new phase state explicitly. Where an optional default is necessary for sourced helpers, default only to the pre-confirmation state; production must initialize and transition it explicitly.
- Replay the two primary new regressions against copies of the pre-fix scripts in owned fixtures. Require assertion failures demonstrating the original F1/F2 behaviors, not fixture setup errors. Do not modify tracked baseline files to perform this check.

### 4. Update current documentation and version metadata

- During implementation, prepare patch version `0.6.2`: update root `VERSION`, README version/release-note link, `scripts/release.json` notes path, and add `docs/releases/0.6.2.md`. Keep repository/image/login/token/platform settings unchanged.
- Update `docs/bash-configuration.md`, `docs/bash-publication.md`, `docs/release-process.md`, and `docs/verification.md` to describe the single effective push endpoint and strict post-confirmation alias guard. Update current-version references in active docs, including `docs/image-usage.md`, where needed.
- Remove current claims that N1/F2 remains unresolved only after its regressions pass. Replace stale references to two unresolved publication warnings with the remaining Buildx warning, F3/N2. Keep F4's early-diagnostics and F5's test-portability limitations explicit where the current review is summarized; do not imply all review findings were fixed.
- Document that script-hash changes prevent adoption of older publications; preserve original checkout/pin requirements. Do not alter archived reviews, old release notes, schema 1, annotation format, or Gitea association-version gates. Add/update table-of-contents links for every changed/new Markdown heading.

### 5. Verify and record results

- Run focused F1/F2 regressions first, then `python3 -B -m unittest discover -s tests -v`. The pre-change suite has 117 tests; the latest full run passed in 857.974 seconds, so allow sufficient execution time and report the actual new count/runtime.
- Run `for script in scripts/*.sh; do bash -n "$script" || exit; done`, Python AST parsing for current Python files, `./scripts/release.sh --validate`, and `git diff --check`. Check active documentation links/anchors/TOCs and version/README/configured-notes agreement.
- Use only temporary owned Git repositories, fake Docker/curl ports, and disposable tokens. Do not run the no-argument release command against this checkout, access production credentials, install tools, invoke real Docker, or perform privileged/live operations.
- Record changed behavior, regression results, baseline replay, known remaining F3–F5 limitations, and verification boundaries in `4-implemented.md` during the implementation workflow. Commit the scoped implementation and documentation through that workflow.

## Acceptance Criteria

- Exactly one effective push destination matching the configured target is required. Explicit/fallback fan-out, duplicates, foreign rewrites, and failed enumeration stop before the next write; initially invalid configurations send no publication writes.
- Supported single-target SSH/HTTPS configurations continue to validate and publish through local fixtures. Fetch/main identity checks and non-force tag behavior remain intact.
- Successful promotion verification creates a one-way state transition, including skipped and reconciled promotions. Thereafter the first contradictory alias observation stops release creation without repair or rollback.
- F2 regressions prove actual post-confirmation injection, zero later release/link writes, and preservation of accepted tag/image state. Positive publication, staging reuse, completed retry, and lost-response behavior remain covered.
- Focused tests, the complete suite, syntax checks, local validation, documentation checks, and diff checks pass. The primary regressions distinguish the pre-fix scripts from the fixed scripts.
- Prepared version metadata consistently uses 0.6.2. Historical evidence stays unchanged, and F3–F5 remain outside implementation scope. No live publication readiness is claimed.

## Risks and Decisions

- Rejecting all multiple effective push URLs, even identical or matching ones, is a deliberate compatibility restriction. It makes one-endpoint authority unambiguous rather than adding multi-repository reconciliation.
- Tests must isolate ambient Git configuration and use real URL expansion in addition to fake-port flow tests; otherwise the fixture can hide the same enumeration bug it is meant to detect.
- The promotion flag models verified evidence, not whether a Docker command ran. Binding it to a write event would leave skipped-promotion and reconciled-response paths unsafe.
- Repeated checks do not make Git/registry/Gitea operations atomic or prevent unseen configuration/alias changes after a read. Preserve operator-enforced writer and checkout-configuration exclusion through completion; this task rejects contradictory observed evidence, not every possible race.
- New script hashes intentionally change publication identity. Do not use the new implementation to repair or adopt a partial publication from old scripts. No durable journal, automatic recovery, or protocol expansion is introduced.
