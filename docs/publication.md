# Publication and recovery

- [Publication and recovery](#publication-and-recovery)
  - [Preflight and publication](#preflight-and-publication)
  - [Checkpoints and retries](#checkpoints-and-retries)
  - [Safety boundaries](#safety-boundaries)

## Preflight and publication

Use a committed clean `main` checkout, explicit configured origin, and committed semantic version. Follow [installation](installation.md) first. The consumer must ignore `.release-template/`, `.template-operation.lock`, and `.template-transaction/`; release checks these ignore rules without editing them. The stable launcher verifies installed checksums under a destination lock before importing the engine.

```sh
FORGEJO_USERNAME=your-login ./scripts/release.sh publish
# For an explicit version source:
FORGEJO_USERNAME=your-login ./scripts/release.sh publish --tag v1.2.3
```

Before tests, Git fetch/push, registry login, or builds, both normal and recovery paths check Buildx's advertised platforms. Diagnostics identify the builder, advertised platforms, and required targets. This is not a runtime emulation test. The workflow runs project checks, confirms or explicitly pushes source without force, builds every image once into a unique staging reference, verifies immutable image configurations, records outputs, creates/verifies the exact source Git tag, promotes verified digests, creates a text-only Forgejo release, and verifies the complete publication before cleanup.

Descriptions contain schema-bound source, template, image digest, and platform identities. There are no attachment upload calls, image archives, checksum assets, or archive-based recovery checks. Defaults leave `latest` as the only final registry tag; temporary staging tags have a separate lifecycle. Git tags remain versioned. If `retain_version` is explicitly enabled, the current version registry alias is retained too.

Cleanup runs after publication but requires the independent evidence gate in [retention safety](retention.md). Without evidence, publication remains recorded as successful and the command returns nonzero with “Publication succeeded; cleanup incomplete”. Do not repeatedly publish merely to satisfy cleanup; provide approved evidence and use cleanup-only mode.

## Checkpoints and retries

```sh
FORGEJO_USERNAME=your-login ./scripts/release.sh resume --tag v1.2.3
FORGEJO_USERNAME=your-login ./scripts/release.sh cleanup-plan --tag v1.2.3
FORGEJO_USERNAME=your-login ./scripts/release.sh cleanup --tag v1.2.3 --deletion-evidence /protected/forgejo-verification.json
```

Ignored `.release-template/v<version>.json` is a versioned checkpoint containing credential-free source/config/template identity, operation IDs, durable intent, immutable prepared digests, exact staging inventories, predecessor aliases, and completion records. Do not discard it after remote mutation or share a state directory between different projects. Keep one authoritative state directory across releases; changing it loses protection for resumable local runs. Retain state and manifests until publication and retirement finish.

Intent is flushed and atomically replaced on the same filesystem before side effects; files and directories must support `fsync`. Lost responses reconcile exact remote tags, aliases, and release identities rather than silently repeat writes. A crash after a build intent but without any recoverable staging digest stops for explicit recovery, even if no build actually started. Inspect the operation, local Buildx metadata, and remote staging identity. Recover missing remote evidence only through a separately reviewed operator procedure; the engine offers no force-rebuild, force-adopt, or checkpoint-rewrite bypass. Never change an identity to hide a conflict.

Resume accepts aliases only at the captured predecessor or this exact run's prepared target. It refuses newer successful publications, equal versions with different source/digests, unrelated alias changes, and unknown predecessor metadata. An older checkpoint never refreshes its predecessor to gain promotion authority. A partially promoted suite can resume only within the recorded transition; cross-service writes are not atomic.

After source advances, use the same committed source checkout and pinned template/configuration to inspect its checkpoint. The source confirmation policy still requires the configured remote main to match; do not roll main backward to force recovery. Investigate mismatches rather than rewriting history.

## Safety boundaries

The source reference is `home-web/scripts/release.sh` plus `home-web/docs/releases.md`. Preserved conventions include clean main, exact versions, source checks, early platform preflight, isolated credentials, trusted TLS, versioned Git tags, and single-publisher operation. Archive uploads, separate archive/registry builds, and archive-dependent `--promote-latest` are intentionally replaced.

Existing projects are not migrated. Existing registry aliases or published records without recognized template identity cannot be adopted automatically; plan their migration separately. No code here promises cross-host transactions or prevention of a publisher racing between final identity checks and writes. Local locks exclude concurrent local update/release invocations; external publishers must be serialized operationally.
