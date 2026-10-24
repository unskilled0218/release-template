# plan

- [plan](#plan)
  - [scope](#scope)
  - [Implementation Plan](#implementation-plan)
    - [1. Define scoped package evidence](#1-define-scoped-package-evidence)
    - [2. Add guarded association](#2-add-guarded-association)
    - [3. Integrate publication and retries](#3-integrate-publication-and-retries)
    - [4. Extend local tests](#4-extend-local-tests)
    - [5. Update documentation and version](#5-update-documentation-and-version)
  - [Acceptance Criteria](#acceptance-criteria)
  - [Risks And Decisions](#risks-and-decisions)

## scope

Implement `1-goal.md` in the supported Bash release workflow. Link only the configured container package to the configured Gitea repository, using existing credentials and bounded HTTP helpers. Preserve build-once publication, immutable identity checks, and conservative refusal behavior. Do not restore the retired engine, add dependencies, publish live resources, delete or unlink packages, or fix unrelated publication warnings.

## Implementation Plan

### 1. Define scoped package evidence

- Add focused helpers and dispatch actions in `scripts/release-data.py`. Derive the owner and package name from the validated `image`; derive the repository name from `repository`. Package and repository names can differ, as they do in the current configuration. Quote each API path segment independently.
- Use `GET /api/v1/repos/{owner}/{repo}` to capture the intended repository's positive integer ID and exact owner/name. Validate returned identity rather than trusting a display URL.
- After publication verification, use `GET /api/v1/packages/{owner}/container/{name}/latest` to inspect the published `latest` package version. This is the ordinary package-version endpoint with the literal version `latest`, not the server's latest-version selection endpoint. Require matching owner, type, name, and version, and an explicit `repository` field. Only JSON null means unlinked; missing or malformed association evidence is a refusal.
- Compare linked repository ID and full owner/name against the validated target. A different association is a conflict, even when its display name resembles the target. Missing packages, unavailable endpoints, redirects, authentication failures, malformed JSON, and exhausted budgets must never count as unlinked evidence.
- Confirm these routes and response fields against the supported Gitea API contract before implementation. Upstream `routers/api/v1/packages/package.go` defines the association route and its empty HTTP 201 response; `modules/structs/package.go` defines package identity and repository fields. No request to `git.lan` is authorized by this plan.

### 2. Add guarded association

- Keep sequencing in Bash and parsing/I/O in Python. Expose separate read-only association verification and guarded ensure-association operations without adding configuration fields or CLI flags.
- If the package already links to the exact repository, return without a POST. If linked elsewhere, stop without unlinking or reassigning it. If explicitly unlinked, freshly validate the target and package immediately before sending exactly one `POST /api/v1/packages/{owner}/container/{name}/-/link/{repo_name}` with existing private `api.curl` credentials and no JSON payload.
- Accept the documented HTTP 201 empty response without parsing it as JSON, then perform a fresh package GET and require the exact association. Keep existing HTTP status restrictions for unrelated operations; the current helper already accepts 201, so do not broadly allow additional success statuses.
- Follow the existing `CommandFailed` versus `Refusal` distinction. A transport failure after POST may be reconciled by one fresh read; continue only if that read proves the exact association. Never automatically repeat the POST in the same invocation. Input, byte-budget, authentication, and HTTP-status refusals remain fatal. If reconciliation is unlinked, conflicting, or unavailable, report an incomplete or uncertain association and stop.
- Preserve response/time limits, same-origin credentials, disabled redirects, secret-safe diagnostics, and cleanup of only run-owned local temporary files. Do not introduce unlink, DELETE, or rollback calls.

### 3. Integrate publication and retries

- In `scripts/release.sh`, run the new association stage after the existing final tag, release, immutable-image, and `latest` verification, before `success`. Revalidate captured source/settings and current publication evidence before association mutation, and verify publication and association again before returning success.
- Apply the same association stage to the completed-publication branch only after its existing identity, release, image, and final-alias checks succeed. A correct association remains read-only. An explicitly unlinked package may receive the scoped link POST so a prior association failure can be completed without rebuilding, promoting, pushing tags, or posting releases.
- Keep tag-only/release-only startup ambiguity and all existing image/alias refusal rules unchanged. No association mutation is allowed when publication identity cannot be proved. Missing or foreign staging remains irrelevant to completed retries.
- Set a distinct package-association phase for error reporting. An association failure after publication leaves accepted image, tag, release, and any accepted link intact and returns nonzero. Print `Publication verified` only after both publication and package association pass.
- Extend the existing operator single-writer prerequisite to package association changes, including UI actions and requests still in flight. A local checkout lock does not serialize those writers.

### 4. Extend local tests

- Extend `tests/fixtures/bash_release_ports.py` with exact target-repository and package-version GETs, package-level association state, the link POST with its empty 201 body, request events, and explicit faults. Make unknown routes fail and update no-write assertions to include package-link writes.
- In `tests/test_bash_release.py`, verify an unlinked fresh publication makes one scoped link POST and a subsequent read proves it; an already-correct link makes none; a conflicting link remains unchanged and fails. Use different package/repository names and unrelated package records to catch scope mistakes.
- Test completed retries with correct, unlinked, and conflicting associations. Assert no build, promotion, tag push, release POST, or staging lookup occurs. After a post-publication association failure, an explicit retry may finish only the allowed missing link.
- Test accepted-but-response-lost linking without duplicate POSTs; failed POSTs; permission failures; missing package/repository; malformed, null, missing-field, and mismatched identities; verification failures; timeouts; and response overflows. Assert no success message, unlink, deletion, or rollback on failures and no further writes after failed prerequisite evidence.
- Add helper tests for strict association classification, exact repository identity, URL construction, empty 201 handling, transport-only reconciliation, and secret-safe errors. Exercise real receiving bounds through existing capture tests rather than claiming fake ports certify server behavior.
- Run `python3 -B -m unittest discover -s tests -v`, Bash syntax checks for `scripts/*.sh`, and `./scripts/release.sh --validate`. Inspect the diff for unrelated changes. Do not run the publishing command against real services.

### 5. Update documentation and version

- Update `docs/bash-publication.md` with the association stage, completed-retry write exception, no-reassignment behavior, partial failures, permissions, API support, and package-writer exclusion. Keep the two unrelated known warnings explicit.
- Update `docs/bash-configuration.md`, `docs/image-usage.md`, and `docs/verification.md` to explain required package/repository access, Packages-tab association, tested cases, and the absence of live server/UI certification. Keep README concise and maintain all affected tables of contents.
- When implementing, advance `VERSION` from `0.4.0` to `0.5.0` for the new release capability; update README, `scripts/release.json` notes path, and add `docs/releases/0.5.0.md` with matching release heading and a table of contents. Preserve historical notes and archived task records. Update version-sensitive tests as needed.

## Acceptance Criteria

- Successful fresh publication leaves only the configured package associated with the configured repository and verifies that association through the Gitea API.
- Correct links cause no association writes. Observed conflicting links cause refusal without reassignment. Missing or invalid evidence never authorizes a POST.
- Completed-publication retries can finish an unlinked package association but cannot republish or repair unrelated image, tag, alias, or release state.
- Association failure returns nonzero without deletion, unlinking, rollback, or a false success message. Accepted writes with lost transport responses are reconciled without duplicate writes in the same invocation.
- Local tests, syntax checks, configuration validation, current version metadata, and documentation agree. Implementation requires no new dependency, credential source, configuration field, or live operation.

## Risks And Decisions

- Gitea's link API does not expose a conditional compare-and-set in its documented contract. Read-before-write alone cannot guarantee no reassignment against concurrent external changes. The no-reassignment guarantee requires operator-enforced exclusive package-association writes through request completion; document this limit rather than claiming atomic safety. If that prerequisite is unacceptable, stop and obtain a different safety design before implementing writes.
- Association is package-wide, not limited to the current image tag. The configured package's versions share the link; never iterate over or relink other packages.
- The deployed Gitea version and token permissions may differ from upstream. Unsupported or inaccessible API behavior must fail closed; do not fall back to HTML scraping or assume the OCI source label proves association.
- Linking after publication deliberately allows a published-but-unlinked partial outcome. The verified completed-publication path provides a narrow retry route without weakening existing publication-repair restrictions.
- Script hashes are part of the annotated tag identity. Updated scripts cannot adopt old publications; use the new committed version/source and preserve original checkouts for historical transactions.
- Existing promotion and Buildx-plugin warnings remain out of scope. Local tests do not establish live Packages-tab rendering, storage behavior, distributed writer exclusion, or general publication readiness.
