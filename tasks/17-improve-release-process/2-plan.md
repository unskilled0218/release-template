# plan

- [plan](#plan)
  - [scope](#scope)
  - [Implementation Plan](#implementation-plan)
    - [1. Document the operator sequence](#1-document-the-operator-sequence)
    - [2. Add safe progress reporting](#2-add-safe-progress-reporting)
    - [3. Make failures actionable](#3-make-failures-actionable)
    - [4. Extend local regression coverage](#4-extend-local-regression-coverage)
    - [5. Verify and record the changes](#5-verify-and-record-the-changes)
  - [Acceptance Criteria](#acceptance-criteria)
  - [Risks And Decisions](#risks-and-decisions)

## scope

Improve release documentation for projects adopting this template, with narrowly scoped progress and failure-message changes in the existing Bash workflow. Preserve configuration, CLI options, authentication isolation, bounded command capture, publication identity rules, retry classification, and all existing write guards. This task does not introduce another release engine or a separate preflight command.

## Implementation Plan

### 1. Document the operator sequence

- Add `docs/release-process.md` with a table of contents and a short ordered checklist: configure the consumer project and run application tests; check required tools and credentials; verify the selected Docker connection and both build platforms; verify source/server readiness through existing checks; build and publish; verify final outputs.
- Explain why installed tools must be checked before invoking Docker or contacting servers, even though platform readiness appeared first in the original request.
- List Bash, Python 3.11+, Git, curl, Docker with Buildx, standard Linux utilities, trusted HTTPS, clean already-pushed `main`, versioned committed notes, and exclusive publication/package writers. Link detailed configuration rather than duplicating it.
- Define server connectivity as distinct Docker builder access, Git remote access, authenticated Gitea API access, and registry access. Explain which existing operation checks each service; ping, an open port, or one successful API call does not establish publication permissions.
- Explain that builder-advertised `linux/amd64` and `linux/arm64` support does not prove every Dockerfile compiles or that runtime emulation works. Link separately approved runtime checks in `docs/platform-preparation.md`.
- Include `docker run --privileged --rm tonistiigi/binfmt --install amd64,arm64 && docker buildx inspect --bootstrap` only as an optional administrator instruction after verifying the relevant Docker host. Native builder nodes are an alternative; no privileged setup runs automatically.
- Describe the actual build/push boundary: `docker buildx build --push` builds and publishes staging together, followed by immutable verification, Git tag publication, digest-only `latest` promotion, release creation, package association, and final verification. Do not promise a separate local build-then-push phase.
- Add troubleshooting entries for missing tools, inaccessible Docker/builder, absent platforms, dirty/unpushed source, invalid credentials, DNS/TLS/service failures, build failures, and ambiguous partial publication. Give safe next steps and link existing retry rules.
- Add a short recommendations list covering application tests before release, native ARM64 nodes where practical, protected credential storage, and operator-enforced writer exclusion. Distinguish recommendations from implemented checks.
- Keep `README.md` short by adding one process link. Align `docs/bash-configuration.md`, `docs/platform-preparation.md`, and `docs/bash-publication.md` with the checklist without duplicating detailed protocol descriptions.

### 2. Add safe progress reporting

- Add a small shared stage-reporting helper in `scripts/release-common.sh` that updates `phase` and emits fixed, human-readable text to stderr. Replace direct phase assignments in `scripts/release.sh` and package association where appropriate.
- Report prerequisite checks, builder/platform readiness, source verification, credential preparation, remote inventory, staging lookup/reuse, registry login, build-and-staging-push start/completion, tag publication, promotion or skip, release creation, completed-publication verification, package association, and final verification at their actual boundaries.
- Ensure start messages precede long operations and completion messages follow successful checks. A build-start message must say that staging may be pushed during the build; do not announce success before immutable evidence is verified.
- Keep diagnostic messages on stderr so command substitutions and helper stdout remain parseable. Preserve the existing final `Publication verified` summary as the only publication-success announcement.
- Do not relay raw subprocess stdout/stderr, HTTP bodies, command arguments, auth files, or credential paths. Keep `set +x`, existing output limits, and timeouts. Document that phase logs provide milestone visibility, not live Docker build output or continuous progress percentages.

### 3. Make failures actionable

- Improve missing-command messages with explicit installation/setup advice for Git, curl, Docker, and Python. Use the existing builder invocation to distinguish an unavailable/unusable Buildx builder from missing advertised platforms; do not install software or change the builder selection.
- Add a platform-specific refusal hint pointing to `docs/platform-preparation.md`, the required platforms, and optional administrator preparation. A generic Docker connectivity failure must not recommend privileged emulation as its remedy.
- Give stage-specific, fixed recovery guidance for source checks, private credential preparation, remote reads/authentication, staging build/push, and later publication steps. Refer to the relevant documentation without printing arbitrary captured errors or sensitive environment values.
- Cover both explicit `stop` paths and unexpected command failures handled by the ERR trap. Avoid contradictory duplicate guidance, preserve nonzero exits, and keep `attempt` reconciliation status handling unchanged.
- Differentiate early readiness failures from stages where remote writes may have been accepted. After any possible write, advise inspecting exact remaining objects and following documented retry states; never advise blind retry, deletion, tag rewriting, alias rollback, credential weakening, or package reassignment.
- Reuse existing bounded Git/API/registry checks for connectivity and identity. Do not add generic health endpoints, unconditional version gates, extra authentication writes, or permission claims that read-only checks cannot prove.

### 4. Extend local regression coverage

- Extend `tests/test_bash_release.py` and only necessary fake-port behavior in `tests/fixtures/bash_release_ports.py` to assert milestone order for fresh publication, staging reuse, and completed-publication verification. Completed retries must not announce or execute a new build/promotion/release POST.
- Cover missing prerequisites, unusable builder, missing ARM64 advertisement, source mismatch, credential failure, remote transport/authentication failure, and build failure. Assert actionable stage guidance, nonzero exits, and no publication writes after failed preflight.
- Assert failures after an accepted write retain existing state and recommend inspection without issuing repair, cleanup, or rollback commands. Preserve lost-response reconciliation and package-association behavior tests.
- Add sentinel secret/path and hostile remote-output checks proving progress/recovery messages do not expose credentials or relay raw output. Verify stderr messages cannot corrupt parsed digests, IDs, statuses, or final success output.
- Preserve `--help` and `--validate` boundaries: no credentials, Docker, network, release lock, or publication progress for validation; help still needs only Bash. Do not require machine-specific installed-tool versions in tests.

### 5. Verify and record the changes

- Run `python3 -B -m unittest discover -s tests -v`, Bash syntax checks for `scripts/*.sh`, `./scripts/release.sh --validate`, and `git diff --check`.
- Check active documentation links, table-of-contents anchors, command examples, progress claims, and troubleshooting instructions against the implemented behavior. Update `docs/verification.md` with the new locally tested boundaries without implying live certification.
- During the implementation workflow, update root `VERSION`, README version, configured notes path, and a new versioned release note together according to project conventions. Do not edit historical release notes or archived task records.
- Record results and limitations in this task's `4-implemented.md`. Commit only task-related changes; leave the existing deletion of task 16 untouched.
- Do not run real publication, use production credentials, pull runtime-check images, install dependencies, change host emulation, or contact live release services during verification.

## Acceptance Criteria

- A consumer developer can follow one linked checklist from prerequisites through final verification and find safe, specific remediation for common failures.
- Documentation accurately describes combined staging build/push, later digest promotion, distinct service checks, and platform-advertising versus runtime guarantees.
- Release execution reports meaningful stages before long operations and actionable failures without exposing secrets or changing machine-readable helper output.
- Missing prerequisites and failed platform/source/server reads stop before publication writes; partial-publication failures preserve accepted remote state and existing retry rules.
- No privileged setup, automatic installation, raw output streaming, new remote writes, CLI changes, or relaxed publication guards are introduced.
- All local checks pass, active documentation links/TOCs resolve, and verification claims remain limited to fake-port/local tests.

## Risks And Decisions

- Keep scope limited to operator clarity and small observability improvements. The two known warnings in `docs/bash-publication.md` remain separate work; do not claim this task resolves publication readiness or config-local Buildx discovery.
- Script changes alter the annotation-bound script hash. Warn that modified scripts cannot adopt publications made under an older identity; preserve original checkouts for historical retries.
- Static milestone messages intentionally trade raw build-detail visibility for credential safety and bounded output. Continuous live build logs would need a separately reviewed output policy.
- Existing read operations establish connectivity only when reached. Package availability and link authority are checked after publication under current rules; do not promise that every late-stage permission failure can be eliminated before building.
- Native multi-platform builds may not need binfmt. Privileged preparation affects the selected daemon host and requires separate administrator approval, especially with remote builders.
- Keep operational ordering and safety rules unchanged except splitting stage labels and improving diagnostics. Any proposed protocol or recovery change requires separate review rather than being hidden in logging work.
