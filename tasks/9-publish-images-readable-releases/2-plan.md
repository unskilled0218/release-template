# Plan

- [Plan](#plan)
  - [Scope](#scope)
  - [Implementation Plan](#implementation-plan)
    - [1. Define readable release notes and image references](#1-define-readable-release-notes-and-image-references)
    - [2. Preserve identity verification without JSON notes](#2-preserve-identity-verification-without-json-notes)
    - [3. Integrate publication and compatibility](#3-integrate-publication-and-compatibility)
    - [4. Test notes, predecessor handling, and retries](#4-test-notes-predecessor-handling-and-retries)
    - [5. Document image consumption and update the version](#5-document-image-consumption-and-update-the-version)
    - [6. Verify the approved live outcome](#6-verify-the-approved-live-outcome)
  - [Acceptance Criteria](#acceptance-criteria)
  - [Risks And Decisions](#risks-and-decisions)

## Scope

Deliver a stable Gitea Packages image reference that supports AMD64 and ARM64, plus human-readable release descriptions containing useful pull/run instructions rather than a serialized identity blob. Preserve build-once publication, digest verification, monotonic version ownership, text-only releases, and safe retries. This stage writes only the plan; no implementation code, credentials, or remote resources are changed.

Task 8 already published and executed `git.lan/dev/container-release-template-hello:latest` on both platforms. Treat `git.lan/dev/example-image:latest` in the request as an illustrative reference, not authorization to rename/reassign an owner-scoped package. Keep the existing configured image name unless the user explicitly selects another name. Image publication and package-repository association are separate concerns; missing repository links do not mean the registry reference is unusable.

## Implementation Plan

### 1. Define readable release notes and image references

- Replace new-body generation in `release_template/policy.py:description` with deterministic, ordinary Markdown. Include a short release/version summary, supported platforms, each image's fully qualified `latest` reference, an immutable digest reference, and copyable `docker pull` / `docker run --rm` commands. For retained version aliases, show their actual configured references too.
- Add a readable source section identifying the repository, source commit, and template revision. These are useful provenance details, not a separate machine-only appendix. Include a table of contents for generated headings, consistent with project Markdown conventions. Avoid decorative tables and emoji.
- Do not include a JSON/YAML/XML block, serialized object, HTML comment carrying hidden JSON, encoded metadata payload, or attachment. Shell command examples remain acceptable human-facing instructions; do not present a different data serialization as a substitute for JSON notes.
- Pass the configured registry authority explicitly as rendering context, for example `description(identity, registry)`, instead of hard-coding `git.lan`, the owner, or the fixture image name. Construct full image references from the configured authority, the repository owner, and each validated image/alias entry. Do not use mutable `latest` as the immutable release identity.
- Use one readable per-image section and fixed source labels, with deterministic image/alias ordering. Preserve each identity's platform-list order so parsing reconstructs the exact existing identity rather than silently sorting a significant list. Keep the content concise and understandable without knowing the checkpoint schema. State that registry authentication may be required; do not claim the package is anonymously public or expose token contents in instructions.

### 2. Preserve identity verification without JSON notes

- Retain the existing logical release identity fields and schema 1: version, tag, source commit, template revision, repository, targets, and platforms. Avoid checkpoint/configuration schema changes solely to improve presentation. The registry authority is presentation context already bound by the checkpoint's configuration hash; it need not force a new release-identity schema.
- Implement a small pure parser for the new readable template in `policy.py`, using its visible version, source fields, image references/digests, and platforms to reconstruct exactly the same identity dictionary. Recognize the new format by its exact ordinary heading/section structure, not by scraping arbitrary English release prose.
- Validate required fields, types, semantic version/tag agreement, commit/revision identities, repository shape, immutable SHA-256 digests, image/alias coverage, supported nonempty platform sets, and consistent registry/owner/name references. Reject missing or duplicate fields/sections/aliases, contradictory references, unexpected embedded data, unknown layouts, and tag/body disagreement with bounded `ReleaseError` messages. Reuse existing validation primitives where practical rather than copying workflow verification into the notes parser.
- Preserve registry context while parsing so the rendered full image references and displayed commands can be checked against the extracted identity. Require canonical re-rendering to match the recognized readable template after narrowly normalizing line endings and one trailing newline. Do not silently ignore changed commands or source fields merely because one digest still matches. This intentionally treats generated notes as a verified public contract, not an arbitrary editable changelog.
- Extend `metadata(release)` with explicit read paths: recognized readable Markdown and the existing legacy `MARKER` plus JSON format. Keep legacy reading compatible with known schema-1 releases, including old Gitea/Forgejo introductory prose. Never generate new legacy JSON descriptions. Malformed readable notes must not fall back into a permissive parser or establish absence.
- Keep validation and deterministic rendering/parsing in the policy module. Network reads, OCI inspection, and durable state remain in their existing adapters/workflow layers. Do not introduce a generic Markdown parser dependency or an external metadata database solely for these notes.

### 3. Integrate publication and compatibility

- Update `Workflow.publish` to render notes with the configured registry authority. Keep `snapshot`, `eligibility`, existing-release reconciliation, and `verify_publication` comparing parsed semantic identity with `release_identity()`; do not replace these checks with a body substring, tag existence, or command success alone.
- A new release must remain text-only, non-draft, non-prerelease, and asset-free. Preserve default `latest` promotion of the already prepared multi-platform root digest, optional version aliases, source Git tags, and complete platform/label verification. Do not build a separate image for the release notes or add archive uploads.
- Persist the exact new readable body in durable release intent before POST, as today. Same-pin retry must reuse that body/identity and reconcile an accepted-but-response-lost release without another image build, promotion, or duplicate release. Conflicting equal-version notes must stop rather than trigger an automatic PATCH.
- Read the existing live `v0.2.3` legacy identity as a predecessor for a newer release without rewriting its source tag, checkpoint, image identity, or body. A normal publication of the same old tag from new code must not adopt or rewrite old-pin state. Preserve exact-pin checkpoint refusal and document that old binaries cannot necessarily read the new notes format.
- Do not change the image allowlist, retention ordering, package association policy, deletion gate, or credential contract. Owner-scoped package linking/reassignment and historical release-body edits require separately confirmed targets and permission; neither is an automatic consequence of rendering new notes.
- Update test fakes/call sites that generate new release bodies to supply registry context. Keep explicit static legacy-body fixtures for compatibility tests so old-format coverage does not accidentally become a test of the new renderer.

### 4. Test notes, predecessor handling, and retries

- Add focused policy tests, preferably `tests/test_release_notes.py`, for readable output and exact round trips. Cover one image, multiple images, latest-only and retained version aliases, registry ports, deterministic ordering, source fields, and complete platform coverage.
- Assert that newly generated descriptions contain the actual full image references, useful pull/run commands, supported platforms, and readable provenance. Assert absence of the old serialized `Release identity` block, hidden/encoded metadata, and JSON/YAML/XML identity payloads. Verify that changing the configured registry changes displayed references correctly rather than leaking a hard-coded fixture target.
- Add negative parser tests for missing/duplicated labels or image sections, invalid digests, mismatched owner/registry/image references, altered commands, platform omissions/duplicates, tag/version conflict, malformed body types, unknown layouts, and truncated notes. Exercise allowed line-ending normalization explicitly; do not gradually accept arbitrary Markdown edits through loose regular expressions.
- Preserve representative legacy schema-1 JSON-body parsing tests, including the actual shape of task 8's `v0.2.3` identity, without contacting live services. Reject corrupt legacy payloads with bounded errors and retain required absence/status validation in the Gitea adapter.
- Extend workflow tests to publish a new readable release, resume successfully, and recover an accepted-but-response-lost release POST with one build and one release record. Test an old JSON-backed predecessor followed by a newer readable release, mixed historical listings, and refusal of equal-version conflicting source/digest/platform/template identities.
- Use loopback/injected Gitea transport tests to verify the POST body is the readable text, no attachment or historical-release PATCH is sent, malformed lookup responses still stop progress, and retries preserve immutable intent/identity. Test CLI success-versus-cleanup-incomplete diagnostics unchanged.
- Keep the existing Ubuntu verification hook and its tests: each declared architecture must actually run the prepared image's default command. Do not replace runtime checks with a manifest platform list or reuse a cached output assertion as live proof.

### 5. Document image consumption and update the version

- Add a dedicated `docs/image-usage.md` describing the actual published image name, trusted registry login when needed, `docker pull`, default `docker run --rm`, automatic platform selection, explicit `--platform linux/amd64` / `linux/arm64` checks, and immutable digest references for reproducibility. Explain that `latest` is mutable and does not guarantee old image availability after separately authorized retention cleanup.
- Keep README concise, link the usage document, and show the real usable reference `git.lan/dev/container-release-template-hello:latest`. Do not imply `example-image` exists unless it is explicitly created and verified under a separate naming decision.
- Update `docs/publication.md`, `docs/verification.md`, and `docs/ubuntu-release-test.md` for human-readable new notes, visible provenance verification, old JSON-body read compatibility, exact-pin limitations, and the distinction between package storage/pullability and repository association. Correct `docs/configuration.md`'s blanket statement that no example selects a real endpoint: the task 8 live fixture is explicitly opt-in and targets the user-approved project.
- Update `VERSION`, `release_template.__version__`, and README consistently from `0.2.3` to `0.2.4` during implementation. Preserve bootstrap, configuration schema, release identity schema, and checkpoint/retirement schemas. Documentation must distinguish this new engine pin from the captured `v0.2.3` experiment; never retag that historical source.
- Write `4-implemented.md` with the actual changes, verification results, approved remote targets, any scope deviations, and remaining gaps. Keep credentials, private auth material, and raw secret-bearing logs outside task artifacts.

### 6. Verify the approved live outcome

- First run the local suite and fixture/configuration checks. Before any new remote write, reconfirm the selected repository/image name, unused `v0.2.4` tag, expected predecessor identity and current `latest` digest, exact committed source, remote main destination, and permission for source/tag/image/release publication. Reuse the already selected project only when that scope is confirmed; planning itself grants no remote-write authority.
- Use an isolated clean checkout on its own `main`, not the task branch or a dirty working tree. Advance approved source only by normal fast-forward and confirm remote main matches the captured fixture commit before release. Do not deploy or rewrite code in existing consumer projects.
- Publish the newer release through the real default build/promotion workflow with both AMD64/ARM64 platforms and no deletion evidence. Independently verify Gitea Packages lists the configured image, `latest` resolves to the prepared index digest, both platforms pull/run successfully, OCI labels and the source Git tag match, and the displayed release body contains readable instructions without JSON.
- Test the user-facing `latest` reference as well as the immutable digest: for each platform, pull `latest` under private temporary auth, verify the selected identity belongs to the expected published index, and run its default command. Require exact `Hello World\n` and exit zero. Preserve the existing reference instead of inventing an unapproved alias/name. Do not assume anonymous access if authentication is required.
- Record and compare actual Docker build/promotion operation counts, release IDs, root/platform digests, source/template commits, and checkpoint identity. Same-source/config/pin retry must create no extra build, promotion, or release, while the missing-evidence cleanup error remains expected only after independently verified publication.
- Historical `v0.2.3` notes remain unchanged in this implementation's normal publication path. If the user also wants its existing JSON body replaced, obtain explicit body-only edit approval and review old-reader/checkpoint compatibility before a separate migration. Do not silently hide JSON, discard identity checks, or rewrite a historical tag to make all old descriptions look new.
- Do not automatically link the existing owner-scoped package to the repository, change package visibility, or enable cleanup. Report missing package association separately from successful pull/run; require separate approval for linking and real disposable contract evidence for deletion. Test/read-only planning and evidence-free refusal may run without making such mutations.
- Run `python3 -B -m unittest discover -s tests -q`, `bash -n scripts/release.sh`, both generic and Ubuntu fixture configuration validation, `git diff --check`, version agreement, and changed-document anchor checks. Run launcher validations serially because they share the destination lock. Commit only authorized implementation/docs/results changes; leave `todo.md` untouched.

## Acceptance Criteria

- A real, fully qualified `latest` reference is documented and verified for AMD64 and ARM64. Docker selects the proper platform, and the Ubuntu fixture's default command produces `Hello World\n`. No unapproved rename, repository reassignment, or visibility change is required.
- New release descriptions are readable Markdown with image references, supported platforms, pull/run examples, and provenance. No JSON or alternative serialized/hidden identity blob is emitted.
- The new visible template round-trips to the existing complete semantic identity. Missing, duplicated, inconsistent, or tampered required content fails closed. Legacy JSON-backed releases remain readable as predecessors without automatically rewriting them.
- Publication, equal-version conflict protection, source/digest/platform verification, exact-pin refusal, durable intent, and accepted-but-response-lost recovery remain intact. Same-pin retry does not rebuild images, repromote unchanged aliases, duplicate releases, or silently edit conflicting notes.
- Text-only release and cleanup safety rules remain unchanged. No attachments, historical tag moves, checkpoint rewriting, automatic package linking, or deletion-evidence bypass is introduced.
- Local regression tests and docs/version checks pass. Live results, if approved and executable, independently verify notes, package pullability, both runtimes, and retry; blocked or unexercised outcomes are reported honestly rather than claimed as passes.

## Risks And Decisions

- Human-readable notes still carry visible provenance needed for safe release recognition. Removing all source/digest information or accepting arbitrary prose would weaken stale/equal-version protection. Fixed readable headings/labels and a strict round trip preserve that contract without JSON or a separate machine-only footer.
- Registry authority is additional rendering context, not a new persisted identity schema. The parser must reject inconsistent full references while returning the original schema-1 identity shape used by workflow comparisons. Tests must cover this distinction.
- New binaries read both legacy and readable notes; old JSON-only binaries may reject readable successors. This is a documented forward-format limitation, not permission to adopt old-pin checkpoints or run vulnerable old cleanup code. Historical bodies remain unchanged unless a separate migration is explicitly approved.
- Gitea Packages are owner-scoped. A valid registry image can be pullable while absent from a repository's linked-package view. The user requested reusable images, not automatic reassignment; preserve that security boundary and document where the package actually exists.
- This repository already has a verified multi-platform image. The task should improve release presentation and prove reusable references, not build a second registry/publishing framework or create a differently named image merely to match an illustrative example.
- A new live release changes mutable `latest` and the project's release history. Confirm the exact new version/target before execution, preserve old source tags, and keep deletion disabled. This planning task performs no remote reads or writes and does not presume approval to rewrite the existing `v0.2.3` body.
