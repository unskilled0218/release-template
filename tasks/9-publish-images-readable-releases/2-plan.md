# Plan

- [Plan](#plan)
  - [Scope](#scope)
  - [Implementation Plan](#implementation-plan)
    - [1. Use project-update release notes](#1-use-project-update-release-notes)
    - [2. Separate verification identity from the description](#2-separate-verification-identity-from-the-description)
    - [3. Integrate durable publication and legacy compatibility](#3-integrate-durable-publication-and-legacy-compatibility)
    - [4. Test notes, identity storage, and recovery](#4-test-notes-identity-storage-and-recovery)
    - [5. Document image usage separately and update the version](#5-document-image-usage-separately-and-update-the-version)
    - [6. Verify the approved live outcome](#6-verify-the-approved-live-outcome)
  - [Acceptance Criteria](#acceptance-criteria)
  - [Risks And Decisions](#risks-and-decisions)

## Scope

Publish reusable AMD64/ARM64 images to Gitea Packages and make the release description a human-readable account of the project's update: features, fixes, compatibility changes, and relevant upgrade notes. The user's clarification supersedes the image-focused description proposed earlier. Do not turn release descriptions into image catalogs, pull/run instructions, provenance dumps, or another machine-oriented format. Keep image consumption instructions in dedicated documentation.

Task 8 already published and executed `git.lan/dev/container-release-template-hello:latest` on both platforms. Treat `git.lan/dev/example-image:latest` as illustrative, not permission to rename/reassign an owner-scoped package. Preserve the existing configured name unless the user explicitly selects another. This planning update changes only the plan; it accesses no credentials and performs no implementation or remote operations.

## Implementation Plan

### 1. Use project-update release notes

- Add an explicit `release_notes` relative-file setting to consumer configuration. Validate its path using existing traversal/symlink safeguards. Require this input for new publication under the updated engine, with a clear migration error when absent; do not silently fall back to image-centered generic text. Keep read-only configuration validation free of credentials and remote calls.
- Store this project's next notes in `docs/releases/0.2.4.md` and point the Ubuntu release configuration at that file. Write concise, curated Markdown describing the actual changes in this release, such as project-focused release notes, backward-reading compatibility, and separately documented image usage. Do not invent features or use unreviewed commit subjects as finished prose.
- Update the bundled example configurations and test configuration fixtures for the new notes input. Consumer examples must explain that their notes belong to the consuming project; do not silently publish this template's update text for another application. Keep generic and Ubuntu example validation usable within this repository.
- Require a version heading matching the requested release, for example `# Release v0.2.4`, followed by useful project-update sections. Include a table of contents for headings. Omit empty sections, decorative tables, emoji, image/platform inventories, generated Docker commands, digest lists, and source/template commit footers.
- Read the note content from the captured Git commit, not an ignored file or mutable working-tree copy. Require a regular committed UTF-8 file with bounded size, for example 64 KiB, and validate it before creating remote publication side effects. Freeze the exact normalized text and its digest for this run; retries must not silently consume later edits.
- The public body is that project-update Markdown alone. Do not append JSON, YAML, XML, hidden HTML metadata, an encoded identity, or an image usage section. The release title/tag identifies the version; the description explains what changed in the project.

### 2. Separate verification identity from the description

- Stop parsing normal release descriptions to recover image/publication identity. Store machine identity in the annotated Git release tag's message instead, outside the Gitea description. This uses an existing immutable, independently verifiable source reference without creating a release attachment, external database, or registry-specific metadata service.
- Define a versioned annotated-tag message envelope with an explicit marker and canonical identity. Use identity schema 2, retaining version, tag, source commit, template revision, repository, targets, and platforms, and adding the committed notes path and normalized-text digest. Machine serialization is permitted in this internal tag record, never in the release description. Keep configuration schema 2 and checkpoint/retirement schemas unchanged; document stricter configuration and the new publication identity format.
- Add small Git adapter helpers to resolve a remote tag's advertised object ID and peeled source commit, fetch the exact tag object without modifying the worktree or replacing local tags, and inspect its type, target, declared tag name, and message. Use normal Git object verification and bounded subprocesses; do not infer identity from a mutable branch name or `target_commitish` string.
- Validate the envelope schema and complete identity: version/tag agreement, repository, source/template revisions, SHA-256 image digests, alias/image/platform coverage, notes path, and notes digest. Require the annotation to target the recorded source commit directly, the peeled commit to agree, and the declared tag name to match the requested release. Authentication, fetch, malformed-object, and missing-required-identity failures must stop progress rather than become absence.
- Keep pure identity validation in policy code and Git/network I/O in adapters. Resolve accepted release identities in workflow orchestration instead of letting `policy.py` fetch network data. Select/validate the highest stable published release before resolving its tag; preserve rejection of unknown publication identities.
- Verify the public description against the note file at the identity's captured source commit and its stored digest. This verifies the intended project text without scraping prose for image metadata. Normalize only explicitly defined line endings and the final newline; arbitrary body changes remain conflicts rather than being ignored.

### 3. Integrate durable publication and legacy compatibility

- Replace new-body rendering in `Workflow.publish` with the frozen committed notes. `release_identity()` emits schema 2 including the notes binding. Preserve default multi-platform build, complete platform/label verification, prepared-digest promotion, optional version aliases, source checks, text-only/non-draft/non-prerelease releases, and asset prohibition.
- After all prepared image outputs exist, create the annotated source tag with the final identity. Persist the exact tag object ID and intended identity before its remote push. Push that captured object without force. On restart, validate/reuse an existing matching local tag and recorded object rather than regenerating a different annotation or replacing tags.
- Reconcile both the remote tag object and complete identity after a lost push response. An existing tag with a conflicting object/identity, a lightweight tag for a new-format release, or a mismatched commit must stop. Do not attach metadata to a pre-existing conflicting tag or rebuild images to escape the conflict.
- Persist the exact project-update body in release intent before POST. Existing-release reconciliation and `verify_publication` compare the schema-2 tag identity, frozen note text/digest, source tag, final aliases, and full runnable evidence. Same-pin retry must not rebuild, repromote unchanged aliases, duplicate a release, or silently PATCH an edited description.
- Preserve a read-only legacy path for schema-1 JSON-backed releases such as live `v0.2.3`, whose tag is lightweight. Resolve and verify their source tag and recognized old body, while new releases use the annotation. A present but malformed new-format tag must never fall back to old JSON and gain authority. Unknown or missing identity remains a failure.
- Allow a recognized legacy predecessor followed by a newer annotated-tag/project-notes release. Do not rewrite the legacy body, move old source tags, update old checkpoint identities, or automatically adopt an old-pin transaction. New binaries can read both generations; old JSON-only binaries may reject new releases and this limitation must be documented.
- Update test fakes to represent annotated tag objects, peeled commits, explicit notes files/content, and release bodies. Preserve genuine static legacy fixtures rather than generating old-format samples through the new renderer. No release-engine path automatically changes package association, visibility, retention ordering, or the deletion gate.

### 4. Test notes, identity storage, and recovery

- Add focused tests for committed-note loading: correct version heading, exact project-update text, bounded UTF-8 content, regular tracked files, path safety, missing configuration/file, version mismatch, and working-tree edits that cannot replace captured content. Verify clear failure before remote writes.
- Assert that the release POST body equals the curated project notes and contains no generated image inventory, Docker commands, digest/provenance appendix, serialized/hidden metadata, or attachment operations. Project notes must not depend on the number or names of published images.
- Test schema-2 tag identity round trips for one/multiple images, latest-only and version aliases, exact platform-list preservation, and notes path/digest. Reject missing/duplicate/unknown identity fields, invalid digests/revisions, contradictory coverage, altered note content, and tag/version/repository/source mismatch.
- Use real temporary Git repositories and a local bare remote to test annotated-object creation/push/readback, peeled commit verification, direct commit targets, fetch without worktree/local-tag replacement, lightweight new-format refusal, malformed annotations, and existing tag conflicts. Keep fake-port tests for workflow decisions and loopback/injected Gitea tests for HTTP behavior.
- Inject termination/lost-response faults around annotation creation, durable tag intent, remote tag push, release POST, and completion flush. Reopen persisted state and require reuse of the approved tag object, no repeated confirmed push/build/promotion/release creation, and no force update or checkpoint rewrite.
- Test legacy schema-1 lightweight tags plus JSON bodies, mixed historical listings, a newer schema-2 successor, and refusal to use malformed new-format identity as a legacy fallback. Keep stale/equal-version source/digest/platform/template conflict protection and exact-pin checkpoint refusal.
- Preserve CLI publication-success/cleanup-incomplete reporting and status-aware lookup safety. Keep the Ubuntu runtime hook and its tests; both architectures must execute the prepared image's default command. Notes tests are not substitutes for image pullability/runtime tests.

### 5. Document image usage separately and update the version

- Add `docs/image-usage.md` for the real reference `git.lan/dev/container-release-template-hello:latest`, trusted authentication when required, `docker pull`, default `docker run --rm`, automatic architecture selection, explicit AMD64/ARM64 checks, and immutable digest use. Explain that `latest` is mutable and older content may disappear after separately authorized cleanup.
- Keep README concise and link image usage separately from release notes. Do not imply `example-image` exists unless a new name is explicitly selected, published, and verified. Do not put image consumption instructions back into the Gitea description.
- Update configuration/publication/verification/Ubuntu-test documentation for the required committed `release_notes` input, project-update-only bodies, annotated-tag identity, legacy reading, frozen note content, and exact-pin limitations. Correct the outdated claim that no example selects a real endpoint: the task 8 fixture is explicitly opt-in for the approved project.
- Update `VERSION`, `release_template.__version__`, and README consistently from `0.2.3` to `0.2.4` during implementation. Add reviewed project-update notes for that version before source publication. Keep bootstrap bytes and checkpoint/retirement schemas unchanged; the identity schema change is explicit and does not enable cross-pin adoption.
- Write `4-implemented.md` with changes, actual verification, compatibility implications, approved targets, remaining resources, and limitations. Never commit credentials, temporary auth configuration, or raw secret-bearing logs.

### 6. Verify the approved live outcome

- Run local tests first. Before remote writes, reconfirm repository/image name, unused `v0.2.4` tag, expected legacy predecessor/current `latest` digest, committed notes/source, Git push destination, and permission for source/tag/image/release publication. Planning and this clarification do not themselves grant new remote-write authority.
- Use an isolated clean checkout on its own `main`. Advance approved source only by normal fast-forward, confirm remote main matches the captured commit, and use the real default two-platform workflow without deletion evidence. Do not run release from a dirty task branch or overwrite another project's source.
- Independently verify Gitea Packages lists the configured image, `latest` identifies the prepared multi-platform index, both platforms pull/run `Hello World\n`, OCI labels/source commit agree, and the new annotated source tag contains the expected machine identity and notes binding.
- Verify the actual displayed Gitea body equals the curated project-update notes. It must explain this project's changes, not describe image artifacts or present pull/run commands. Ensure no metadata blob is visible or hidden in the body. Read image instructions from documentation instead.
- Test the user-facing `latest` reference and immutable digest on each platform under private temporary authentication; confirm selected identities and default output/exit status. Preserve the configured image name and record actual runtime evidence rather than claiming anonymous access.
- Trace real build/promotion operations without recording arguments/environment/stdin. Same-source/config/pin retry must preserve tag object, release ID/body, digests, note binding, and checkpoint identity while creating no additional build, promotion, or release. The absent-evidence cleanup error is expected only after independently verified publication.
- Leave historical `v0.2.3` notes unchanged. A separate body-only historical edit needs explicit approval and compatibility review; do not retag, rewrite old state, or hide JSON to make historical records appear migrated.
- Do not automatically link/reassign packages, change visibility, or enable deletion. Missing package association is reported separately from pull/run success. Linking requires separate approval; deletion requires both approval and real same-server/full-version disposable contract evidence.
- Run `python3 -B -m unittest discover -s tests -q`, shell syntax, generic/Ubuntu configuration validation, `git diff --check`, version agreement, and Markdown anchor checks. Run launcher validations serially because they share a lock. Commit authorized implementation/docs/results changes and leave `todo.md` untouched.

## Acceptance Criteria

- AMD64 and ARM64 images remain usable through a documented full `latest` reference, with verified platform selection and default runtime output. No unapproved image rename, package reassignment, or visibility change is needed.
- The release description contains curated human-readable project updates only. It is not an image catalog, Docker usage guide, provenance dump, or serialized/hidden metadata container.
- New identity is verified from a source-bound annotated tag and the committed notes digest, not extracted from project prose. Missing/conflicting/malformed identity or edited notes fails closed; legacy predecessors remain readable without automatic migration.
- Durable tag/release intent, immutable source/object identity, equal/stale-version checks, platform/digest verification, exact-pin refusal, and lost-response recovery remain intact. Retry causes no rebuild, unnecessary promotion, duplicate release, force tag update, or silent description edit.
- Releases remain text-only and asset-free. Historical tags/checkpoints are preserved; package linking and deletion safety rules are unchanged.
- Local regressions and docs/version checks pass. Approved live results separately verify project-focused notes, package pullability, both runtimes, and retry; blocked/unexercised results remain explicit.

## Risks And Decisions

- This is a deliberate change from the earlier image-focused plan. Reading machine identity from a release body would keep forcing artifact fields into prose, so verification moves to annotated Git tags. Canonical machine data remains internal to tag storage and must never be copied into the public description.
- Annotated tags are a format change: new publications require the new envelope, while legacy lightweight tags are accepted only with recognized old metadata. Distinguish missing legacy data from malformed new data and never downgrade after a new-format validation failure.
- Identity schema 2 binds the notes path/hash while retaining image ownership information outside prose. A required `release_notes` setting is a documented stricter publication contract despite unchanged configuration schema. Old consumers must add committed project notes before publishing with the new pin.
- Human text is curated, not automatically invented from image labels or commit subjects. It is frozen by the captured source and note digest; manual edits to a published description become explicit conflicts, not automatic permission to rewrite state.
- Git tags can be force-moved by external actors. This tool never force-updates them, records exact object identity for retries, and verifies remote evidence, but operational serialization and trusted repository permissions remain required.
- Gitea Packages are owner-scoped. Successful registry pulls do not authorize package linking or deletion, and a missing repository link is not a failed image publication. Keep image usage, project release notes, and cleanup authority separate.
- New live publication changes `latest` and release history; reconfirm the version/target before executing. Existing `v0.2.3` remains historical, with no implied permission to edit its description or source tag.
