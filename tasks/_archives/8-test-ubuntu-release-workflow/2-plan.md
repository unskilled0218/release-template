# Plan

- [Plan](#plan)
  - [Scope](#scope)
  - [Implementation Plan](#implementation-plan)
    - [1. Confirm the disposable target and authorization](#1-confirm-the-disposable-target-and-authorization)
    - [2. Check tooling and platform execution](#2-check-tooling-and-platform-execution)
    - [3. Prepare a pinned disposable consumer](#3-prepare-a-pinned-disposable-consumer)
    - [4. Publish and independently verify Hello World](#4-publish-and-independently-verify-hello-world)
    - [5. Verify retry and the closed cleanup gate](#5-verify-retry-and-the-closed-cleanup-gate)
    - [6. Record results and preserve test resources](#6-record-results-and-preserve-test-resources)
  - [Acceptance Criteria](#acceptance-criteria)
  - [Risks And Decisions](#risks-and-decisions)

## Scope

Exercise the real pinned release template through a disposable consumer containing an Ubuntu `Hello World` image. Verify Git/source identity, Buildx publication, digest promotion, text-only Gitea release metadata, runtime output, and same-checkpoint retry. Do not modify release-engine behavior, existing consumer projects, or this template's remote configuration. This planning commit changes only this plan; it performs no build, credential access, installation, push, publication, or deletion.

The completed local AMD64 build/run smoke test is background evidence only. It does not establish release publication, ARM64 execution, retry safety, or Gitea deletion semantics. The current template version is `0.2.2`; fixture release versions are independent.

## Implementation Plan

### 1. Confirm the disposable target and authorization

- Before any live operation, obtain the exact credential-free HTTPS Gitea origin, matching registry host/port, disposable owner/repository, unique owner-scoped image name, and permitted Git fetch/push URL. Do not infer these from the template's `origin` or from existing consumer settings.
- Confirm who creates the empty disposable remote repository. Obtain separate approval if the agent must create it. Confirm that the repository and image namespace are disposable, have no existing consumers, and have no prior releases, `latest` alias, or other package content that could be adopted or overwritten. An existing owner/repository must not be silently repurposed.
- Obtain explicit permission for the initial fixture source push, the template's version-tag push, image staging push, `latest` promotion, and text-only release creation. The template automatically performs some of these operations during `publish`; approval for a local Docker run is not sufficient.
- Obtain `GIT_USERNAME` and the path selected by `GIT_TOKEN`, not token contents. Use a user-owned readable private token file with narrowly scoped Gitea permissions. Confirm independent native Git authentication without embedding a token in remote URLs, command arguments, repository files, or logs. Reject unsupported credential aliases as the engine requires.
- Record public target identifiers and approval scope in task results, but not token contents or private Git/Docker connection material. Confirm operational serialization: no other publisher may write this namespace during the test.
- If any required target, permission, credential path, or trust configuration is missing, stop before live writes and report the test as blocked. Local fixture preparation and configuration validation may proceed without claiming end-to-end success.

### 2. Check tooling and platform execution

- Recheck Python 3.11+, Git, Docker client/daemon connectivity, selected Docker context, and Buildx version. Record their actual versions. The preceding smoke test observed Docker 29.9.2 and Buildx 0.38.1, but do not treat those observations as a current preflight.
- Inspect the selected builder's advertised platforms, then separately verify runnable `linux/amd64` and `linux/arm64` support with native or already-configured emulated Docker runtimes. A builder's platform list alone is not runtime proof. If different daemons are required for the two runtime checks, record the mapping and approved contexts explicitly.
- Do not install emulation, run privileged helper containers, change daemon settings, disable TLS, or use root. Report missing prerequisites for the user to supply. If ARM64 execution is unavailable, stop the two-platform live test or obtain an explicit reduced-scope AMD64 decision; never silently report a two-platform pass.
- Verify trusted HTTPS for Python API reads, Git, Docker daemon pulls, and BuildKit pushes. Inspect only the approved target's product/version/API contract after target and credential access are confirmed. `/api/v1/version` records exact version but does not independently prove product identity.

### 3. Prepare a pinned disposable consumer

- Use a new unique directory under `/tmp/opencode` on the supported local filesystem, with a distinct private directory outside the consumer for logs and any test instrumentation. Do not reuse the template checkout or any existing consumer directory. Initialize the disposable consumer's own Git branch as `main`.
- Pin template commit `af15c2d9b24c02d44f4e379bdef5dfffe4a36cc2`, which contains the reviewed `0.2.2` engine. Verify the object exists and its `VERSION`/module version agree. Run the standalone updater's dry-run, install, and `--verify` against this new consumer. Use the exact pin throughout publication and retry; do not update managed code mid-test.
- Create the consumer's Dockerfile with exactly this minimal application behavior:

```dockerfile
FROM ubuntu:24.04
CMD ["echo", "Hello World"]
```

- Add the ignore rules from `examples/consumer.gitignore`. Create schema-2 `release.json` using the approved origin, matching registry authority, exact disposable repository, unique approved simple image name, explicit version source, and platforms `linux/amd64` and `linux/arm64`. Keep `source_push: false`, omit custom build hooks, and leave `retain_version: false` so the real default builder and latest-only promotion path are tested.
- Add a small consumer-only Python verification hook using `RELEASE_INPUT_JSON`. For each required platform, pull and run the supplied immutable `image` reference with an explicit `--platform`; require exit code zero and stdout exactly `Hello World\n`. Use argument arrays and a bounded subprocess timeout. Do not override the container command, entrypoint, or runtime platform to force a pass. Register the hook under the image's `verify` command. This checks the default CMD, not merely that `/bin/echo` can be invoked separately.
- Set the approved credential-free origin remote. Commit Dockerfile, configuration, hook, ignore rules, vendored engine, and lock inventory before publication. Confirm a clean consumer `main`, correct effective fetch and push destinations, and a fixed source commit. Logs, token files, auth configuration, and checkpoints must not enter the committed build context.
- Run the installed consumer launcher in `validate` mode without credentials first. After explicit source-push approval, push the captured fixture commit to the disposable remote `main` and confirm it through `git ls-remote`. Do not use force or enable automatic source push to hide a mismatch.
- To measure build-once behavior, use a private temporary Docker command wrapper outside the consumer. Resolve the real Docker executable before adjusting the invocation's PATH. The wrapper forwards arguments, environment, streams, stdin, and exit behavior unchanged to that absolute executable, and records only enumerated operation labels such as `buildx build` or `imagetools create`. Never record raw arguments, environment, stdin, token values, or Docker auth files. Use the same wrapper for publish and retry; it must not replace real Docker operations with fakes.

### 4. Publish and independently verify Hello World

- On the clean disposable `main`, run `GIT_USERNAME=<approved-login> GIT_TOKEN=<protected-file-path> ./scripts/release.sh publish --tag v1.0.0` with the isolated operation trace enabled. Do not provide deletion evidence during this primary test.
- Expect publication to finish and the subsequent cleanup gate to return nonzero with `Publication succeeded; cleanup incomplete`. A nonzero exit is acceptable only when the checkpoint says `published: true`, the release operation is complete, the specific error is missing deletion evidence, and independent remote checks pass. Do not classify an earlier build, auth, promotion, or publication error as this expected result.
- Capture the run ID, source commit, template pin, staging alias/digest, prepared output digest, Buildx metadata digest, final alias digest, and release identity. Require one real `buildx build` invocation for the initial run, no archive upload, and no custom second image build. Record the resolved Ubuntu base digest from available build evidence without replacing `ubuntu:24.04` with an unapproved image.
- Verify remote `main` and `refs/tags/v1.0.0` identify the captured fixture source. Fetch the release through the approved API: it must be non-draft, non-prerelease, text-only with no assets, and contain the expected repository/source/template/version/target/platform identity. Verify expected final aliases: `latest` exists and resolves to the prepared root digest; no `v1.0.0` registry alias is expected because `retain_version` is false. Staging remains separate from final aliases.
- Inspect the immutable index and every runnable platform manifest/configuration independently of the command's exit status. Require exactly AMD64 and ARM64 members, expected revision/version/source labels, valid digest identities, and equality among prepared, metadata, release-target, and promoted root digests. Preserve sanitized evidence of the exact manifests/configurations examined.
- With private temporary Docker authentication, pull the final digest from the registry, then run it on each explicitly selected platform and require `Hello World\n` plus exit zero. Resolve `latest` again and confirm it still identifies that digest. Registry/configuration verification alone does not prove layers are pullable or the default command runs.
- Do not rely on an ambient Docker login or persist test credentials in the user's normal Docker configuration. Cleanly end only the temporary authentication scope after runtime checks; maintain the selected contexts/builder connections. Retain no credential-bearing raw logs in the task artifacts.

### 5. Verify retry and the closed cleanup gate

- Before changing the fixture commit/configuration/template pin or publishing any newer version, snapshot the checkpoint identities, output digest, build metadata, remote source tag, release ID/body, alias mapping, and Docker operation counts. Keep the same authoritative checkpoint directory.
- Run `resume --tag v1.0.0` through the same installed launcher and real Docker trace. Require publication revalidation, the same missing-evidence cleanup error, no additional `buildx build` or `imagetools create`, unchanged source tag/release identity/output digest, and no duplicate release. Complete-operation identities remain stable; do not require byte-identical state when the engine legitimately reflushes unchanged progress.
- Run `cleanup-plan --tag v1.0.0` without deletion evidence. Require success, no DELETE or publication mutation, and a candidate/retirement plan bound to the same run. Missing package association may explain an explicit skipped record but does not grant linking or deletion authority. Stop and report real API incompatibility rather than adjusting production code or metadata to manufacture a pass.
- Explicitly run `cleanup --tag v1.0.0` without evidence and require the closed deletion gate, preserved publication, unchanged approved deletion state, and no remote deletion. Confirm the run's staging and current image references remain present. No absence of old resources should be presented as a deletion-safety test.
- Do not trigger live crash/lost-response faults in this first test. Successful same-checkpoint retry proves idempotent revalidation, not every interrupted-build scenario covered by synthetic tests.
- Optional deletion extension is excluded unless separately approved. It requires exact deletion authority, real retained contract-test logs, and a fresh schema-2 attestation for the same server/full version/storage environment. The contract-test repository named in that attestation must be distinct from the disposable consumer under cleanup. Obtain approval for that second namespace and its actual contract-check deletions before testing them; never derive an attestation from the local Hello World test or fill its Boolean results speculatively. If these prerequisites are absent, leave cleanup blocked and report deletion unverified.

### 6. Record results and preserve test resources

- Write `4-implemented.md` in this task with approvals and public target identifiers, exact fixture/template/source versions, tool/server versions, actual commands and exit classifications, digest/release evidence, per-platform output, retry command-count deltas, observed failures, and remaining gaps. Use explicit pass/fail/blocked/not-run status for publication, each runtime platform, retry, cleanup planning, and deletion. Do not claim a live pass when execution is blocked by missing target or permissions.
- Add a dedicated `docs/ubuntu-release-test.md` recipe based on the actual procedure and link it briefly from README/verification documentation as appropriate. Keep real credentials, private connection details, and raw secret-bearing logs outside Git. State clearly whether Gitea publication was exercised on a real deployment and whether deletion remains unverified; do not convert one deployment result into a universal compatibility claim.
- Keep fixture checkpoints and sanitized manifests/logs until the user accepts the results and any separately approved teardown is complete. Report the exact disposable repository, package aliases/digests, images, and local directories left behind. Do not delete remote packages/releases/repositories or broadly prune Docker resources as automatic cleanup. Local containers created for runtime checks may use `--rm`; remove only individually identified test artifacts when authorized.
- Run the project's local regression suite, `bash -n scripts/release.sh`, example configuration validation, `git diff --check`, and documentation anchor checks before committing task results/documentation. The planning baseline has 165 passing tests; rerun rather than reuse that result. Do not modify `todo.md` or engine code to accommodate an integration failure; capture a reproducible issue for a separate fix task.
- Do not bump the consumer fixture version or template pin during the retry experiment. Record any repository workflow metadata-version requirement separately from the tested `0.2.2` pin; a documentation version change must not silently change what engine was exercised. No release/tag of the template repository itself is part of this test.

## Acceptance Criteria

- No existing consumer or non-disposable remote namespace is modified. All live writes have confirmed targets and explicit authorization; missing prerequisites produce a blocked result rather than a fabricated pass.
- The committed Ubuntu fixture prints exactly `Hello World\n` using its default CMD on each declared platform. AMD64-only execution cannot satisfy two-platform acceptance.
- The installed immutable `0.2.2` pin executes the real default build/promotion/publication path. Prepared, Buildx-metadata, final-alias, and release-target digests agree, and source labels/Git tags identify the captured consumer commit.
- A text-only release with correct identity is independently verified. Expected missing-evidence cleanup failure is distinguished from publication failure, and publication is durably recorded as successful.
- Same-source/config/pin `resume` adds zero build and promotion invocations, preserves digest/tag/release identity, and creates no duplicate release. Read-only cleanup planning works; evidence-free cleanup refuses deletion without invalidating publication.
- Deletion remains blocked and explicitly unverified unless separate authorization and real same-server contract evidence satisfy the existing gate. No credentials or manufactured attestations are committed.
- Results include actual per-platform/runtime and retry evidence, versions, remaining resources, and explicit limitations. Project regressions and documentation checks pass, or failures are reported without altering engine behavior to suppress them.

## Risks And Decisions

- Approved Gitea origin/repository/image namespace, account/token-file path, remote-write permissions, repository-creation responsibility, and platform runtime availability are not yet supplied. They are execution gates, not assumed defaults. Planning approval alone does not authorize the remote operations listed above.
- The consumer is a separate Git repository on its own `main`; the implementation task branch in this template repository must never be substituted as its release source. The template's untracked `todo.md` is irrelevant to the isolated consumer and remains untouched.
- `ubuntu:24.04` is mutable. Record the actual resolved digest and use the prepared immutable image digest for verification and retry. The test does not certify future Ubuntu tag contents or require a base-image rebuild on retry.
- Two-platform publication and execution need both builder support and runnable daemons/emulation. No privileged installation or insecure registry workaround is authorized. Ask the user to supply prerequisites rather than silently narrowing scope.
- A successful release with deliberately blocked cleanup returns nonzero by design. Report publication and cleanup as separate outcomes; do not disable the gate just to obtain exit zero. Retained staging/package/release records are expected resources until separately approved teardown.
- Package association and deletion authority are owner-scoped, not implied by image labels, matching names, or push success. Package linking affects the whole package and requires separate approval; this plan does not perform it automatically.
- Command tracing must remain outside the captured source and record only operation classifications. This provides build-once evidence without changing the engine or exposing password-stdin contents; unchanged digests alone would not prove absence of a repeated build.
- A Hello World release validates this small fixture and observed deployment only. It does not establish full suite/dependency behavior, live interrupted-write recovery, deletion semantics, storage upgrades, or power-loss durability. Keep unexercised claims explicitly unverified.
