# Implementation

- [Implementation](#implementation)
  - [Scope And Status](#scope-and-status)
  - [Changes](#changes)
  - [Verification](#verification)
  - [Compatibility And Safety](#compatibility-and-safety)
  - [Live Verification Gate](#live-verification-gate)
  - [Remaining Resources And Limits](#remaining-resources-and-limits)

## Scope And Status

Implemented the local code, examples, tests, documentation, and version update for `2-plan.md` on the new branch `9-publish-images-readable-releases`. Version is `0.2.4`. Review findings P1–P3 are implemented at the checkpoint, adapter, and test boundaries. Live v0.2.4 publication and its post-release runtime/removal experiment remain gated on explicit target/version/source-write approval; no live success is claimed by the local results below.

## Changes

- Required safe relative `release_notes` configuration with an explicit migration error. Publication reads a regular committed UTF-8 blob up to 64 KiB, checks its version heading, narrowly normalizes newlines, and freezes exact text/hash before remote publication writes. The Gitea body is only that project-update text. Added reviewed `docs/releases/0.2.4.md` and a replace-before-publication consumer sample.
- Added pure canonical schema-2 identity validation and annotated-tag envelope parsing. New identity includes the original source/template/repository/alias/digest/platform fields and a notes path/hash binding. Duplicate/unknown fields, inconsistent coverage, malformed hashes, and changed notes fail closed.
- Added exact Git tag/object adapters: deterministic annotation creation, direct commit targets, advertised/peeled verification, object fetch without local-tag/worktree replacement, durable exact-object push intent, and lost-response reconciliation. Deterministic epoch tagger time represents reproducible object creation, not the publication date. Legacy schema-1 description metadata/lightweight source tags remain read-only predecessor inputs; malformed annotated records never downgrade to legacy authority.
- Added opt-in `link_packages`, complete paginated/scoped association evidence, prepared-version presence checks, durable per-image intent, strict encoded 201 link calls, fresh post-confirmation, and final association verification. Every necessary POST requires a bounded exact-scope, exact-server-version, unexpired operator-confirmed single-writer window via `--package-link-window`; matching links need no window or POST. Window renewal remains outside immutable intent and publication identity.
- Added opt-in `remove_local_images` with daemon/context binding, a durable original baseline including untagged IDs, declared immutable hook-pull intents, private observation journals, per-reference removal progress, fresh shared/container/identity checks, and mandatory `docker image rm --no-prune` without force. Unproven/undeclared/pre-existing/shared/changed/in-use content is preserved and reported. The engine does not invent ownership for opaque custom hooks.
- Integrated local finalization into verified publish/resume even when remote cleanup is deliberately blocked. Publication, remote cleanup, and local outcomes remain separate. A persisted success flag alone cannot authorize local removal in a fresh invocation. Read-only modes and failed publication perform no local removal.
- Updated the Ubuntu hook to durably report each platform's inspected local image ID after pull. Enabled the two opt-ins in the approved fixture, while generic consumers retain false defaults. Added dedicated image-usage, package-linking, and local-ownership documentation; updated README/configuration/publication/verification/Ubuntu instructions.

## Verification

- Latest full local run: `python3 -B -m unittest discover -s tests -q` passed 226 tests in 45.520 seconds. The original 169-test baseline also passed during implementation. New tests cover real temporary Git repositories and a local bare remote, canonical identity/note validation, static legacy predecessors, pre-intent/tag-response recovery, link windows/association conflicts/lost responses/ordering, removal-aware local stores, daemon changes, journal validation, parent protection, partial removal/restart, CLI outcome separation, and hook observations.
- Loopback HTTP verifies encoded package-link routes, strict 201 acceptance, rejection of 200/204/401/403/404/409/500, and bounded errors without raw token-bearing bodies. No new unlink/delete/visibility calls are introduced by linking.
- All six example configurations passed direct validation. Generic `examples/explicit.json` and live-fixture `examples/ubuntu-hello/release.json` each passed serial `scripts/launch.py validate` invocations without credentials or remote operations.
- `bash -n scripts/release.sh`, Python AST syntax checks, root/module/README version agreement, Markdown heading/table-of-contents checks, and `git diff --check` passed. Stable bootstrap scripts, `release_template/state.py`, and `release_template/cleanup.py` remain unchanged; checkpoint/retirement outer schemas and remote deletion gates are preserved.
- Local tests do not contact the real Docker daemon, read the default credential file, publish images, access the production server, or delete host images. Removal tests use exact emitted-command assertions and removal-aware fake stores, not real shared-daemon teardown.

## Compatibility And Safety

Configuration remains schema 2 with a deliberately stricter notes input. New consumers must commit their own version-matched project updates. Legacy historical records are readable but not automatically rewritten; old JSON-only binaries may reject new releases. Exact source/config/template checkpoint identity remains mandatory, and old-pin transactions cannot be silently adopted.

Package association affects every version of an owner-scoped package and can change cleanup ownership eligibility, but it never supplies remote deletion evidence. The new window record documents real operator-established exclusion; it cannot enforce permissions, prove that other writers are disabled, or turn a checkout-local lock into a distributed lock. Unknown/unconfirmed exclusion blocks mutation. Link replacement semantics remain conservatively treated as potentially reassigning; no live reassignment experiment was performed.

Local cleanup protects original references/IDs and uses `--no-prune` to preserve untagged parents. Current inventory, declared immutable digest, observed local IDs, original daemon, and container/shared-reference evidence must agree. Registry index digests are not conflated with local image IDs. An ambiguous image store or opaque hook can leave explicit safe skips. No-concurrent-writer coordination for the exact local references remains an operational prerequisite; identical concurrent pulls cannot establish ownership by themselves.

## Live Verification Gate

Before any new remote write, reconfirm `https://git.lan/dev/container-release-template`, image `git.lan/dev/container-release-template-hello`, unused tag `v0.2.4`, the legacy predecessor/current alias, committed source/notes, effective Git destinations, and source/tag/image/release publication authority. Use a clean isolated checkout on its own `main`, normal fast-forward source publication, private temporary authentication, and no remote deletion evidence. Do not publish from the dirty task branch or rewrite v0.2.3.

An approved experiment must independently verify the actual project-update body, exact annotated object and notes binding, repository association/Packages visibility, `latest` and immutable-index selection, AMD64/ARM64 default output `Hello World\n`, source labels, and same-checkpoint retry with no extra build/promotion/release or confirmed link POST. Journal independent verification pulls before they occur and run guarded finalization after the last check. Record exact removed/absent/skipped/failed references and confirm remote artifacts remain intact. If browser verification is unavailable, distinguish that from authenticated API confirmation.

## Remaining Resources And Limits

No live packages, tags, releases, images, credentials, or remote sources were changed by the implementation work recorded here. Historical v0.2.3 and its preserved checkout/checkpoint/evidence remain untouched. Its existing four linked package versions are historical context, not fresh v0.2.4 verification. No v0.2.4 production deletion attestation is created or implied.

Local finalization intentionally does not prune builder caches, shared layers, unrelated images, base images, or other daemon contexts. It removes only declared observed immutable hook-pull references; undeclared staging/final aliases from custom hooks remain protected and reported when observable. Free-space recovery is not guaranteed. Keep checkpoints and private journals for recovery. Further approved live results must update this record rather than being inferred from synthetic tests. `todo.md` remains untouched.
