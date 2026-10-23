# Ubuntu release test

- [Ubuntu release test](#ubuntu-release-test)
  - [Scope and approval](#scope-and-approval)
  - [Prepare the source and platforms](#prepare-the-source-and-platforms)
  - [Publish and verify](#publish-and-verify)
  - [Retry and cleanup](#retry-and-cleanup)
  - [Observed result](#observed-result)

## Scope and approval

The opt-in fixture in `examples/ubuntu-hello/` builds `ubuntu:24.04` with default command `echo "Hello World"` for `linux/amd64` and `linux/arm64`. Its `release.json` explicitly targets `https://git.lan/dev/container-release-template` and package `git.lan/dev/container-release-template-hello`. It is not a generic consumer configuration and must never silently select another project.

The user authorized using this existing project instead of the original plan's disposable repository, with login `dev` and default protected token-file path. Source publication must be a normal fast-forward, never a replacement or force push. The test uses an isolated clean checkout of the committed fixture on its own `main`, with this repository as its remote. Because this is the template source repository, the existing source-checkout launcher runs the engine at that captured commit; this is not a vendored-installation test of the originally proposed `0.2.2` pin. Version `0.2.3` adds the fixture without changing release-engine behavior.

Confirm target, unused version tag, image namespace, and publication permission before a new run. Do not create/link/delete packages or repositories automatically. No deletion evidence is supplied, and no deletion-safety claim follows from this test. Use the private token file through `GIT_TOKEN` or its default; never log its contents. Independent Git authentication is required. A token need not have account-profile access if approved repository/package operations already work.

## Prepare the source and platforms

Commit the fixture and configuration before release. Confirm a clean source `main`, correct effective fetch/push remote, and the same captured commit on remote `main`. Preserve the exact source/configuration/checkpoint identity through retry. Do not run publication from the task branch or push a separate disposable repository over the project's main history.

Follow [platform preparation](platform-preparation.md). Verify that the builder advertises both architectures and that each runtime actually runs Ubuntu successfully. Privileged host preparation is performed by the administrator, not the release tool. The fixture's verification hook pulls and runs the prepared immutable digest on both platforms without replacing its default command, and requires exact stdout `Hello World\n` and exit zero.

For build-once evidence, a private external Docker wrapper may record only enumerated operation labels and forward every real operation unchanged. Record per-phase counts, not raw arguments, environment, stdin, or Docker auth files. Keep logs outside Git and outside the committed build context. Preserve daemon/builder connections when using temporary private registry authentication.

## Publish and verify

After the approved fixture commit reaches remote `main`, run from the matching clean checkout:

The commands below describe the recorded `v0.2.3` experiment at source `e096c05d760c156fd0641d3ae906937c942476c2`. Do not republish that tag from a later documentation/results commit. Retry uses the preserved matching checkout and checkpoint; a new experiment requires a separately committed, approved unused version rather than rewriting the old tag or state.

```sh
GIT_USERNAME=dev ./scripts/release.sh validate --config examples/ubuntu-hello/release.json
GIT_USERNAME=dev ./scripts/release.sh publish --config examples/ubuntu-hello/release.json --tag v0.2.3
```

The version comes from the committed root `VERSION`; do not change it to retry a previous checkpoint. The first command uses no credentials or remote operations. Publication is expected to finish before the absent-evidence cleanup gate returns nonzero. Count this as publication success only when `published: true`, the release operation is complete, the specific failure is missing deletion evidence, and independent remote checks agree. Any earlier failure is a real failed or incomplete publication.

Inspect the release, source Git tag, final registry alias, immutable index, and all runnable configuration labels. Prepared, Buildx-metadata, `latest`, and release-target digests must agree. Pull and execute that final immutable digest on both platforms using private temporary auth, requiring `Hello World\n`. The image has no final version alias by default; its release-unique staging alias remains while cleanup is blocked. A repeated build producing the same digest is not proof of build-once behavior; check the operation trace.

## Retry and cleanup

Before any source/configuration/pin change, run:

```sh
GIT_USERNAME=dev ./scripts/release.sh resume --config examples/ubuntu-hello/release.json --tag v0.2.3
GIT_USERNAME=dev ./scripts/release.sh cleanup-plan --config examples/ubuntu-hello/release.json --tag v0.2.3
GIT_USERNAME=dev ./scripts/release.sh cleanup --config examples/ubuntu-hello/release.json --tag v0.2.3
```

Resume must reverify the same publication without another build, promotion, or duplicate release, then report the same missing-evidence cleanup error. Read-only planning needs no attestation. The final command must refuse deletion and preserve publication. A missing/foreign package association remains visible in the plan but does not grant linking authority.

Keep checkpoint provenance, sanitized evidence, and exact remaining resource identifiers until results are accepted. Do not delete packages, releases, tags, repositories, or broad Docker caches as automatic teardown. Deletion remains separately authorized and evidence-gated. One successful fixture run does not certify other Gitea deployments, interrupted-write recovery, storage deletion behavior, or filesystem power-loss durability. Actual results belong in the task's `4-implemented.md`, not in a speculative success claim here.

## Observed result

On 2026-10-23, source commit `e096c05d760c156fd0641d3ae906937c942476c2` published [v0.2.3](https://git.lan/dev/container-release-template/releases/tag/v0.2.3) on Gitea 28.2.0. The final image is `git.lan/dev/container-release-template-hello@sha256:a7aa21103ec639854ff02d29668e61b85c22b24fb92c7f5cddf7a52e2fa1a8fd`. AMD64 and ARM64 each ran the image's default command and returned exactly `Hello World\n` with exit zero.

The initial publication invoked one real Buildx build and one promotion. Same-checkpoint resume added neither and preserved the release ID, digest, source tag, and checkpoint. Publication/resume returned exit 1 only after verified publication because deletion evidence was deliberately absent. Read-only cleanup planning passed; explicit cleanup refused deletion without modifying the checkpoint. Gitea package records lacked repository links and were reported as skipped, not automatically linked. Deletion and interrupted-write behavior remain unverified on this deployment. The task's implementation record and `release-evidence.json` contain sanitized details; the source tag must never be moved to later result/documentation commits.
