# Implementation Results

- [Implementation Results](#implementation-results)
  - [Outcome](#outcome)
  - [Authorization and Plan Changes](#authorization-and-plan-changes)
  - [Changes](#changes)
  - [Live Verification](#live-verification)
  - [Local Verification](#local-verification)
  - [Remaining Resources and Limits](#remaining-resources-and-limits)

## Outcome

Published [v0.2.3](https://git.lan/dev/container-release-template/releases/tag/v0.2.3) and `git.lan/dev/container-release-template-hello:latest` on Gitea 28.2.0. The prepared, Buildx-metadata, promoted, and release-target root digests agree: `sha256:a7aa21103ec639854ff02d29668e61b85c22b24fb92c7f5cddf7a52e2fa1a8fd`. Both AMD64 and ARM64 pulled that immutable image and ran its default command, producing exactly `Hello World\n` with exit zero. Same-checkpoint retry performed no additional build or promotion. Cleanup remained deliberately blocked and deletion is not verified.

The captured source/template revision is `e096c05d760c156fd0641d3ae906937c942476c2`, run `56d55584c3ac4546917a82b631b0055b`, release ID 1. Sanitized machine-readable results are recorded in `release-evidence.json`. The original Ubuntu base index resolved to `sha256:68ee22004a9109b44973313b02ff7b1de250f1de0f5ecb628d73f579aaff33ac`, confirmed by both platform entries in Buildx provenance metadata.

## Authorization and Plan Changes

- The user explicitly changed the target from a new disposable repository to `git@git.lan:dev/container-release-template.git`, requested the project's configured username and default protected token-file path, retained both platforms, and then instructed continuation of build and release. Configured Git username `dev` was used with `~/.config/git/token`; no token content was printed or committed.
- The token initially could not be read. After the user requested retry, protected-file access, approved repository/package reads, and registry lookup succeeded. An optional `/api/v1/user` profile read returned HTTP 403; no broader permissions were requested because repository/package operations and Docker login worked with the existing scoped token.
- The initial builder advertised only AMD64. The agent did not install binfmt or run any privileged helper. After administrator preparation and the user's continuation request, the builder advertised ARM64 and separate Ubuntu runs succeeded on both platforms.
- Because the approved target is this existing source repository, the test used its committed fixture and source-checkout launcher at immutable revision `e096c05`, not a new vendored consumer installed at the originally proposed `0.2.2` pin. Version metadata was updated to `0.2.3` consistently with the implementation workflow. Engine behavior was not changed; vendored installation is not claimed as a live outcome.
- A separate clean checkout under `/tmp/opencode` used its own local `main`. The approved source push was a normal fast-forward from remote `af15c2d` to `e096c05`; no force push or unrelated repository replacement occurred. The release engine then pushed `refs/tags/v0.2.3`. Result/documentation commits follow the captured source and must not be substituted into that existing release tag or checkpoint.
- The task branch remains `8-test-ubuntu-release-workflow` for result recording and subsequent review. Package linking, deletion, teardown, and interrupted-write tests were not authorized or performed.

## Changes

- Added `examples/ubuntu-hello/Dockerfile` with `FROM ubuntu:24.04` and default `CMD ["echo", "Hello World"]`.
- Added explicit opt-in `examples/ubuntu-hello/release.json` targeting the approved repository and image name, with both platforms, default builder, root VERSION source, local regression checks, and no automatic source push or retained version alias.
- Added `examples/ubuntu-hello/verify.py` to pull/run the prepared immutable image on both platforms with bounded subprocesses, exact default-command output checks, and bounded failure messages. It does not replace the command or entrypoint to force success.
- Added four local hook test methods in `tests/test_ubuntu_hello.py`, covering real command shape through mocked Docker boundaries, immutable/two-platform input rejection, failed pulls, and incorrect/nonzero runtime outcomes. These tests do not contact the server or read credentials.
- Added `docs/ubuntu-release-test.md`, linked it from README and verification documentation, and recorded actual scope, commands, results, and limitations. Version values in `VERSION`, the module, and README agree at `0.2.3`.
- The earlier task commit `fc2167c` documented the administrator's AMD64/ARM64 setup commands in `docs/platform-preparation.md` and linked that document from credentials/publication docs. Those commands were documented only, not run by the agent.

## Live Verification

- Preflight passed for Gitea version `28.2.0`, no existing releases, no existing `container-release-template-hello` package records, and absent `latest`. Remote `main` initially identified `af15c2d`; no existing Git tags were listed.
- Both preflight runtime commands passed: `docker run --rm --platform linux/amd64 ubuntu:24.04 echo "Hello World"` and the ARM64 equivalent. Runtime context was `default`, with Docker client/server 29.9.2, Buildx 0.38.1, and BuildKit 0.34.0. Python was 3.12.3 and Git was 2.43.0.
- `publish --config examples/ubuntu-hello/release.json --tag v0.2.3` passed publication in 47.470 seconds, invoking one real `buildx build` and one `imagetools create`. CLI exit 1 was expected only after `Publication verified: v0.2.3`, a durable published checkpoint, completed release operation, and the exact missing-evidence cleanup diagnostic. No earlier failure was accepted as success.
- Independent authenticated API/registry checks confirmed the text-only non-draft/non-prerelease release with no assets, exact source/config/template/version/platform identities, matching prepared/metadata/final/release root digests, complete two-platform configurations and source labels, matching source Git tag, and no final `v0.2.3` registry alias.
- The final immutable image was pulled and run again outside publication under private temporary Docker auth. Both platforms returned exactly `Hello World\n` and exit zero without an explicit command override. Temporary auth material was removed by its context manager; no persistent user login was created.
- `resume` passed revalidation in 2.388 seconds, then returned the same expected missing-evidence error. It added zero builds/promotions, preserved the entire decoded checkpoint, source tag, output digest, release ID/body, and single-release inventory. It did not rebuild merely because the Ubuntu tag is mutable.
- `cleanup-plan` passed with exit 0 in 1.417 seconds. It had zero candidates and four skipped package records, each missing the configured repository association. No package was automatically linked. Its empty retirement schedule remained bound to the same run.
- `cleanup` without evidence returned exit 1 in 0.638 seconds at the closed evidence gate. Checkpoint bytes stayed unchanged, and current/staging references remained present. No deletion request or attestation was generated; deletion semantics remain unverified.
- An external wrapper forwarded actual Docker operations unchanged and recorded only enumerated operation labels, never arguments, environment, stdin, or credentials. Counts were one build and one promotion over all phases; raw per-phase state and sanitized manifest evidence remain outside the checkout.

## Local Verification

- Passed `python3 -B -m unittest discover -s tests -q`: 169 tests in 41.479 seconds before source publication. The release's configured checks ran this suite again before its first build.
- Passed `python3 -B scripts/launch.py validate --config examples/ubuntu-hello/release.json` without credential access or remote operations.
- Passed `bash -n scripts/release.sh` and `git diff --check` before committing the fixture.
- Final regression rerun passed: 169 tests in 41.401 seconds. Both the generic example and live fixture configurations validated successfully. Concurrent validation initially encountered the launcher's intended nonblocking destination lock; the fixture validation passed when retried serially.
- Final shell syntax, diff whitespace, version agreement, Markdown table-of-contents anchors, and persisted live-evidence comparisons passed. Saved source/revision/run/release identities, digest, per-platform output, and phase exit/count/timing records agree with the captured live results.

## Remaining Resources and Limits

- Remote resources retained: release ID 1 / tag `v0.2.3`; image `git.lan/dev/container-release-template-hello:latest`; staging alias `rt-56d55584c3ac4546917a82b631b0055b-container-release-template-hello`; AMD64 manifest `sha256:523e0b3a9747a4bc0aa42733f5c9955480c0bc21b9a62ac306a86cccb49302f5`; ARM64 manifest `sha256:3325bac0c66bddc88da782a1b1253b71e0e6a0a416a37df978afdb422c236042`; root index `sha256:a7aa21103ec639854ff02d29668e61b85c22b24fb92c7f5cddf7a52e2fa1a8fd`. No repository, tag, release, or package was deleted.
- Gitea's four listed package versions had no repository association. Linking is a separate owner-scoped action and was not performed. Cleanup remains disabled without real same-server/full-version disposable contract evidence even if linking is approved later.
- Preserved local test directory: `/tmp/opencode/ubuntu-release-k8vdffRB`. It contains the clean source checkout, authoritative ignored `.release-template/v0.2.3.json` checkpoint, ignored Buildx metadata, operation-only trace, sanitized results/manifest evidence, and external test controller. Preserve this provenance; do not replace its source/configuration or checkpoint identity to force a retry after main advances. It contains no copied token or retained Docker auth configuration.
- Ubuntu base and final test-image layers remain in the selected Docker daemon cache. Runtime containers used `--rm`; no broad prune or image cleanup was performed.
- This validates one source-checkout fixture release and successful retry on the observed Gitea deployment. It does not certify vendored installation, another server/version, live interrupted-write recovery, package linking, deletion/storage semantics, other tool-suite consumers, or power-loss durability. No production deletion attestation was created.
