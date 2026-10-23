# Publication and recovery

For the default 0.3.0 command, use [Bash publication and recovery](bash-publication.md). This page describes legacy Python checkpoint publication under original pinned launchers. Its commands are not accepted by the new default wrapper; current-source legacy entry is `scripts/legacy-release.sh`, and old transactions still require their original source/config/template pin.

- [Publication and recovery](#publication-and-recovery)
  - [Preflight and publication](#preflight-and-publication)
  - [Checkpoints and retries](#checkpoints-and-retries)
  - [Safety boundaries](#safety-boundaries)

## Preflight and publication

Use a committed clean `main` checkout, explicit configured origin, and committed semantic version. Follow [installation](installation.md) first. The consumer must ignore `.release-template/`, `.template-operation.lock`, and `.template-transaction/`; release checks these ignore rules without editing them. The stable launcher verifies installed checksums under a destination lock before importing the engine.

```sh
GIT_USERNAME=your-login ./scripts/release.sh publish
# For an explicit version source:
GIT_USERNAME=your-login ./scripts/release.sh publish --tag v1.2.3
```

Before tests, Git fetch/push, registry login, or builds, both normal and recovery paths check Buildx's advertised platforms. Diagnostics identify the builder, advertised platforms, and required targets. This is not a runtime emulation test. Publication first validates and freezes committed project notes and, if opted in, saves the original local-image baseline before project checks/hooks/builds. It confirms or explicitly pushes source without force, builds every image once into a unique staging reference, verifies immutable configurations, and records outputs. Opted-in package linking is confirmed before tag push, promotion, or release creation. The workflow creates/verifies the exact annotated Git tag, promotes prepared digests, creates a text-only release containing only project notes, and verifies the complete publication before cleanup.

For host-side AMD64/ARM64 emulation installation, builder bootstrap, and runtime checks, see [platform preparation](platform-preparation.md). An authorized administrator performs privileged setup separately from release execution.

Descriptions contain only curated committed project updates. Identity schema 2 lives in the annotated Git tag message, prefixed by `Release-template identity 2` and followed by canonical JSON. It binds version/tag, source/template revisions, repository, exact aliases/digests/platforms, and notes path/hash. The tag directly targets the captured commit. Deterministic tagger identity and epoch timestamp make object creation replayable before intent is saved; this timestamp is not a release-time claim. Git object verification and exact remote object IDs protect recovery. Fetches do not replace local tags or worktree content. There are no attachment upload calls, image archives, checksum assets, or archive-based recovery checks. Defaults leave `latest` as the only final registry tag; temporary staging tags have a separate lifecycle. Git tags remain versioned. If `retain_version` is explicitly enabled, the current version registry alias is retained too.

Recognized schema-1 JSON descriptions and lightweight source tags, including historical v0.2.3, remain readable as predecessors. They are never rewritten automatically. A malformed annotated/new-format tag cannot fall back to old description metadata. Old JSON-only binaries may reject schema-2 publications; keep each checkpoint's exact template pin and do not modify old identity to force adoption. Project-note edits, changed tag objects, missing identity, or source/digest/platform conflicts stop publication rather than triggering PATCH or force updates.

Cleanup runs after publication but requires the independent evidence gate in [retention safety](retention.md). Without evidence, publication remains recorded as successful and the command returns nonzero with “Publication succeeded; cleanup incomplete”. Do not repeatedly publish merely to satisfy cleanup; provide approved evidence and use cleanup-only mode.

Opted-in [local finalization](local-images.md) runs after verified publication even when remote cleanup is blocked. Its removed/absent/skipped/failed outcomes are reported separately; a local failure does not overwrite the remote-cleanup diagnostic or undo publication. `resume` revalidates publication before local finalization and never relies only on a persisted success flag. Read-only modes do not remove local images.

Cleanup and abandonment also refuse malformed, expired, or excessively future-dated verification evidence. Version 0.2.2 enforces exact UTC formats, a 30-day maximum age, and a 5-minute future tolerance at cleanup/abandon invocation entry, not before every DELETE. Reverify after expiry or storage changes; do not merely redate an attestation. These refusals preserve an already recorded publication's success and return cleanup incomplete.

## Checkpoints and retries

```sh
GIT_USERNAME=your-login ./scripts/release.sh resume --tag v1.2.3
GIT_USERNAME=your-login ./scripts/release.sh cleanup-plan --tag v1.2.3
GIT_USERNAME=your-login ./scripts/release.sh cleanup --tag v1.2.3 --deletion-evidence /protected/gitea-verification.json
```

Ignored `.release-template/v<version>.json` is a versioned checkpoint containing credential-free source/config/template identity, operation IDs, durable intent, immutable prepared digests, exact staging inventories, predecessor aliases, and completion records. Do not discard it after remote mutation or share a state directory between different projects. Keep one authoritative state directory across releases; changing it loses protection for resumable local runs. Retain state and manifests until publication and retirement finish.

Intent is flushed and atomically replaced on the same filesystem before side effects; files and directories must support `fsync`. Lost responses reconcile exact remote tags, aliases, and release identities rather than silently repeat writes. A crash after a build intent but without any recoverable staging digest stops for explicit recovery, even if no build actually started. Inspect the operation, local Buildx metadata, and remote staging identity. Recover missing remote evidence only through a separately reviewed operator procedure; the engine offers no force-rebuild, force-adopt, or checkpoint-rewrite bypass. Never change an identity to hide a conflict.

A tag object ID in checkpoint JSON is not a Git garbage-collection root. Version 0.2.6 recreates the existing deterministic annotation bytes locally before inspecting a new or pending tag operation. Existing intent must match the captured identity, and the regenerated object ID must equal its recorded ID exactly. Pruning an unreferenced local object therefore does not require another image build or a different annotation. Reissuing `git mktag` is a local content-addressed operation, not a tag move or remote mutation. Matching remote tags reconcile without another push; local/remote object conflicts, malformed intent, and a completed remote tag's disappearance remain refusals. No private refs, checkpoint rewrite, broad Git-error-as-absence fallback, or old-pin adoption is introduced.

Resume accepts aliases only at the captured predecessor or this exact run's prepared target. It refuses newer successful publications, equal versions with different source/digests, unrelated alias changes, and unknown predecessor metadata. An older checkpoint never refreshes its predecessor to gain promotion authority. A partially promoted suite can resume only within the recorded transition; cross-service writes are not atomic.

After source advances, use the same committed source checkout and pinned template/configuration to inspect its checkpoint. The source confirmation policy still requires the configured remote main to match; do not roll main backward to force recovery. Investigate mismatches rather than rewriting history.

`resume`, `cleanup-plan`, and `cleanup` require the exact checkpoint template revision, not merely the same schema. Updating managed code cannot resume an old-pin publication or cleanup transaction. Preserve the checkpoint and its original provenance; cross-revision adoption requires a separately reviewed procedure and has no automatic bypass. Do not rewrite identity or release metadata, discard state, or use vulnerable old-code cleanup to force progress. Within a matching revision, saved cleanup inventories are revalidated against current identities and all surviving reference graphs before deletion.

Cleanup now checkpoints a versioned [retirement schedule](retention.md#retirement-schedule) before its first deletion. Referring indexes/manifests retire before shared or nested dependencies. Resume keeps that approved order, confirms exact absent targets without repeating DELETE, and still fetches fresh live survivor graphs. Publication remains successful if cleanup stops because a new reference protects a pending dependency. Retry cannot repair a legacy transaction whose child was already deleted without approved ordering evidence; preserve that state for separately reviewed operator recovery rather than forcing adoption or rebuilding content.

Explicit [abandonment](retention.md#staging-and-abandoned-runs) requires both scoped package and registry alias absence before recording a run as abandoned. A successful DELETE with uncertain confirmation leaves that run pending and stops later aliases. Retry the same selected runs after remote views converge; confirmed-absent aliases need no second DELETE. Earlier confirmed deletions and completed runs remain progress, while captured digests and graph protection remain intact. No automatic rollback, forced completion, or old-checkpoint repair is provided.

## Safety boundaries

The source reference is `home-web/scripts/release.sh` plus `home-web/docs/releases.md`. Preserved conventions include clean main, exact versions, source checks, early platform preflight, isolated credentials, trusted TLS, versioned Git tags, and single-publisher operation. Archive uploads, separate archive/registry builds, and archive-dependent `--promote-latest` are intentionally replaced.

Existing projects are not migrated. Existing registry aliases or published records without recognized template identity cannot be adopted automatically; plan their migration separately. No code here promises cross-host transactions or prevention of a publisher racing between final identity checks and writes. Local locks exclude concurrent local update/release invocations; external publishers must be serialized operationally.
