# plan

- [plan](#plan)
  - [Scope](#scope)
  - [Current behavior](#current-behavior)
  - [Implementation Plan](#implementation-plan)
    - [1. Add failing regression scenarios](#1-add-failing-regression-scenarios)
    - [2. Preserve graph evidence and classify images consistently](#2-preserve-graph-evidence-and-classify-images-consistently)
    - [3. Protect every preserved reference before selecting digest deletions](#3-protect-every-preserved-reference-before-selecting-digest-deletions)
    - [4. Revalidate persisted cleanup candidates](#4-revalidate-persisted-cleanup-candidates)
    - [5. Update documentation and verify the patch](#5-update-documentation-and-verify-the-patch)
  - [Acceptance Criteria](#acceptance-criteria)
  - [Risks And Decisions](#risks-and-decisions)

## Scope

Resolve F1 and F2 from `tasks/1-standardize-container-releases/5-code-review.md` in this template only. Protect preserved references and their transitive manifests during cleanup, and verify every runnable platform and its identity without misclassifying artifacts. Address plan-review P1 with transaction-relative survivor protection and P2 by retaining exact template-revision identity checks, not introducing cross-revision adoption. Add focused regression tests and document conservative failure behavior. This stage updates only this plan and commits it; it does not modify implementation, run live operations, change consumers, or touch `todo.md`.

## Current behavior

- `release_template/cleanup.py:29-61` protects current outputs and unfinished checkpoints, but not graphs reachable from other preserved package references. `plan()` skips unknown, prerelease, newer, and external-staging aliases before resolving their graphs; their older backing digests can still become deletion candidates.
- `cleanup.apply()` reuses persisted candidates and rechecks only the narrower protected set. Fixing initial selection alone would leave old saved plans and newly preserved references unsafe on retry.
- `release_template/adapters.py:241-280` traverses nested manifests and subjects but returns bare configurations, discarding descriptor and artifact context. Publication and cleanup identify runnable images solely by `amd64`/`arm64` membership.
- `tests/support.py` provides a permissive registry fake. The loopback OCI fixture treats an unmarked `unknown` architecture configuration as an attestation, so it cannot distinguish genuine artifacts from malformed image entries.
- The review recorded 59 passing tests, but no real Docker/Forgejo verification. The deletion attestation gate must remain unchanged.
- Checkpoint schema and recovery identity are separate contracts. `Workflow` binds each checkpoint to its exact template revision, and `State` rejects mismatches before CLI cleanup runs. Upgrading the template pin does not grant access to an older checkpoint merely because both use schema 1.

## Implementation Plan

### 1. Add failing regression scenarios

- In `tests/test_workflow.py`, reproduce F1 with a completed older checkpoint whose `cleanup_complete` is true, a newer verified publication, a preserved alias pointing at older content, and separately listed digest records for that content. This avoids accidentally passing because unfinished-checkpoint protection hides the defect.
- Cover unknown aliases, prerelease tags, newer version aliases, and external staging aliases. Include nested indexes, shared child manifests, attestation dependencies, and both inventory orders so selection cannot depend on package listing order.
- Verify the read-only plan excludes every protected digest and apply never calls deletion for it. Include a truly unreferenced, provably older digest as a positive deletion control.
- Save an unsafe cleanup inventory before adding or retargeting a preserved alias, then resume apply. Assert that fresh evidence blocks the pending digest deletion without changing publication success or rebuilding images. Include an old-selection-shaped schema-1 inventory injected into a checkpoint with matching source/config/template identity; this tests inventory validation, not cross-revision checkpoint compatibility.
- For P1, introduce an older stable alias such as `v0.9.0` after planning, absent from the saved candidate inventory but pointing at a pending digest. Test introduction before apply and between digest candidates. Its policy eligibility must not grant deletion authority: protect its complete graph or stop before deleting it. Also test an alias recreated after its candidate was marked complete and a pending alias whose digest changed.
- For P2, create a disposable old-pin checkpoint and invoke the patched CLI with a different template revision. Assert identity rejection before cleanup/publication writes or registry login, unchanged checkpoint bytes, and zero remote mutations. Keep a separate same-revision CLI retry test demonstrating successful inventory revalidation. Do not bypass the identity guard to make the upgrade test pass.
- In `tests/test_adapters.py`, use real loopback OCI responses for a valid two-platform index containing an extra runnable `linux/riscv64` entry. Assert rejection even when that entry has matching labels; separately cover missing or conflicting labels, unknown/missing OS or architecture, duplicate platform entries, and descriptor/configuration disagreement.
- Replace the existing unmarked attestation stand-in with explicitly identified Buildx/OCI artifact fixtures. Verify legitimate nested artifacts remain accepted and protected, while an unmarked `unknown` configuration or contradictory artifact/image evidence fails closed.
- Add cleanup ownership cases where an extra runnable configuration has foreign source labels, missing labels, or a non-older version. Such a digest must not qualify for deletion merely because its AMD64/ARM64 subset looks owned and old.

### 2. Preserve graph evidence and classify images consistently

- Extend `Registry.graph()` to retain immutable manifest identity, configuration media type/content, manifest artifact/layer metadata, and incoming descriptor platform/annotation evidence for each image-bearing node. Keep the complete reachable manifest set for deletion protection, including nested indexes and subject edges.
- Retain evidence for every incoming edge even when a shared manifest was already fetched. Digest deduplication must not hide conflicting platform descriptors or let an artifact role on one edge exempt a runnable role elsewhere. Distinguish index membership from subject-only reachability when assembling the publication's runnable set.
- Add a small shared, side-effect-free classifier in `release_template/oci.py`. Define supported runnable-image and non-runnable artifact forms explicitly; return all runnable image configurations rather than filtering against the consumer's supported architectures. Unknown or contradictory forms raise `ReleaseError` rather than silently disappearing.
- Recognize supported Buildx attestation manifests using their explicit descriptor annotations, non-runnable platform/configuration evidence, and attestation layer media types together. Recognize supported OCI artifacts using explicit artifact/configuration media-type evidence. Architecture `unknown`, a lone annotation, or an `artifactType` field on a contradictory runnable image is not sufficient to bypass image verification. Unsupported artifact encodings stop verification pending an explicit adapter extension.
- Make `Registry.verify()` compare the complete runnable platform multiset against configured requirements, reject duplicates/extras/missing platforms, validate descriptor/configuration agreement, and check source/version/revision labels on every runnable configuration. Artifact configurations do not count as runnable platforms, but their manifests remain in the protected graph.
- Make cleanup ownership use the same classifier. A digest is eligible only when it has at least one proven runnable image and every runnable image has the exact configured source and a provably older stable version. Non-runnable artifact-only or unclassifiable historical content stays preserved; no supported-architecture subset can grant deletion authority.
- Update all graph consumers and `FakeRegistry` to the new evidence contract. Give fixtures explicit platform/configuration records and use the shared pure classifier where appropriate, while retaining independent HTTP-based tests so a permissive fake cannot conceal F2 again. Do not persist transient graph records in checkpoints or change the stable bootstrap.

### 3. Protect every preserved reference before selecting digest deletions

- Refactor cleanup discovery into explicit phases: exhaust the paginated inventory, classify reference eligibility, resolve required evidence, construct the full protected union, and only then select digest candidates. Keep existing release-version selection and exact image-name/repository deletion boundaries.
- Classify ordinary aliases as retained, provably older, exactly owned successful-run staging, or preserved/uncertain. Retained and preserved aliases contribute complete graph roots before any digest selection. Continue reporting ambiguous records in `skipped` and preserve the existing cleanup-incomplete result.
- Define the transaction's survivor set separately from general policy eligibility. A live reference is authorized for removal only by an exact matching pending candidate in this transaction, including current image/name/version/digest and ownership evidence. Every other live reference contributes full graph protection, even if it is an older stable alias that policy would otherwise permit deleting. A completed candidate does not authorize deleting a recreated reference.
- For a new plan, establish the proposed candidate inventory before calculating transaction-relative survivors; then remove any protected digest candidates and retain the resulting protected closure. For retry, use only the already recorded pending inventory. Never silently append newly discovered eligible references to that inventory.
- Classify digest ownership with the shared image classifier before final candidate selection. Digest records excluded because their ownership/version cannot be proven also contribute their reachable graphs, so a preserved index cannot lose a separately listed child digest.
- Union these roots with current publication outputs, unfinished sibling checkpoint outputs, and accepted-but-uncheckpointed staging evidence. Preserve existing abandoned-run protections. Completed checkpoints may stop protecting their old outputs, but live preserved aliases must still protect those same outputs.
- For the same configured image name, preserve graph roots from package records not eligible for repository-scoped deletion, including missing/conflicting repository association. Never broaden deletion authority to those records. Records for other image names remain outside the deletion namespace.
- If a relevant preserved reference cannot resolve or its graph cannot be established, stop cleanup before deletion rather than assuming it protects nothing. Reuse fetched immutable graph evidence within one inventory pass, but do not reuse mutable alias resolutions across later safety checks.
- Keep alias deletion distinct from digest deletion: an eligible old or owned staging alias may still be removed when it shares protected content, but only under the unchanged attested alias-deletion semantics. Protected raw digest records must never be removed.

### 4. Revalidate persisted cleanup candidates

- Before processing any persisted cleanup inventory, first require the existing exact source/config/template identity match, then collect fresh package evidence and establish transaction-relative survivor protection. Apply these checks to schema-1 inventories accepted under that matching identity, including old-selection-shaped candidate lists. This is defensive inventory validation, not permission to load checkpoints from a different template revision.
- Immediately before each pending digest deletion, repeat publication verification, exact package ownership/digest checks, transaction-relative survivor graph protection, and all-runnable ownership/version checks. Any live reference without a matching pending deletion candidate protects its graph, regardless of its general policy eligibility. A newly protected or newly ambiguous candidate stops with a clear cleanup-incomplete error; do not mark it complete, silently delete it, or automatically add replacement candidates.
- Retire authorized alias candidates before deleting affected backing digests, including when replaying a differently ordered saved inventory. If an alias deletion fails or its identity changes, stop before deleting its required content. Preserve candidate completion markers without using them as authority over recreated records.
- Keep confirmed absence idempotent, preserve completion markers for already finished operations, and retain pending inventory for investigation/retry. Malformed, unauthorized, or unavailable responses are not confirmed absence. Do not refresh stale publication predecessors or alter build-once recovery.
- Retain the current template-revision mismatch refusal for `resume`, `cleanup-plan`, and `cleanup`. Do not rewrite stored template identity, release metadata, or provenance, offer implicit adoption, or relax `State` validation. Cross-revision cleanup adoption requires a separately reviewed operator procedure and is outside this patch.
- Test unresolved preserved references, graph traversal failures, unscheduled older aliases introduced between candidates, partial deletion retries, matching-identity old-shaped inventories, cross-revision CLI rejection, and current-publication drift. Assert zero additional unsafe deletion calls after a failed safety check.

### 5. Update documentation and verify the patch

- Update `docs/retention.md` to state that preserving a reference preserves its reachable graph, including skipped aliases, uncertain digest roots, and policy-eligible references absent from the pending transaction. Explain that unavailable protection evidence blocks cleanup and saved candidates are revalidated rather than automatically trusted or expanded.
- Update `docs/configuration.md` and `docs/verification.md` with exact runnable-platform verification, supported explicit artifact evidence, realistic fixture coverage, and conservative handling of unsupported OCI forms. Keep live deletion verification requirements and the single-publisher limitation explicit.
- Update `docs/installation.md` and `docs/publication.md` to distinguish managed-code upgrade support from checkpoint recovery compatibility. An upgraded pin cannot resume an old revision-bound checkpoint. Preserve that checkpoint and its provenance for separately reviewed handling; do not suggest rewriting its identity, discarding it, rolling back source, or running vulnerable old-code cleanup as a workaround. Same-revision retries remain supported; this patch supplies no cross-revision adoption command.
- During implementation, bump the patch version from `0.1.0` to `0.1.1` consistently in `VERSION`, `release_template/__init__.py`, and the README version statement. Keep README changes minimal and leave bootstrap files unchanged so ordinary pinned updates remain possible.
- Run `TMPDIR=/tmp/opencode python3 -B -m unittest discover -s tests`, `bash -n scripts/release.sh`, credential-free example validation, and `git diff --check`. Run focused new tests first and then the entire suite, including installer/update and recovery tests.
- Record actual results and remaining live-verification limits in this task's `4-implemented.md` when implementation is authorized. Commit only scoped implementation, tests, documentation, version, and task-result changes; leave unrelated work untouched.

## Acceptance Criteria

- Preserved aliases and ineligible digest records protect every reachable manifest regardless of inventory order or whether the older checkpoint completed cleanup.
- Plans never select protected raw digests, and fresh apply/retry checks block unsafe candidates from both newly generated and old-selection-shaped saved inventories with matching checkpoint identity. Eligible alias retirement and provably unreferenced older-content deletion still work under the existing gate.
- P1: every live reference absent from the exact pending deletion inventory protects its complete graph, including newly discovered older aliases and recreated completed candidates. Policy eligibility alone never expands a saved transaction's authority; affected alias removal must finish before backing-digest deletion.
- P2: an actual CLI invocation with an old-pin checkpoint and a new template revision fails without remote mutation or checkpoint modification. Exact identity validation stays intact. Inventory-shape regression tests are not presented as cross-revision recovery support.
- Unavailable preserved-reference evidence fails closed. Same-name records outside repository deletion authority do not become deletion candidates or lose shared graph protection.
- Publication rejects every unexpected runnable platform and checks labels on every runnable image. Supported explicit artifacts/attestations remain accepted without platform-count pollution; malformed or contradictory entries are rejected.
- Cleanup never infers whole-digest ownership from a supported-platform subset. Foreign, missing, newer, ambiguous, or artifact-only evidence cannot authorize historical digest deletion.
- Existing stale-resume, build-once, durable-state, pagination, staging, abandonment, installer/update, and text-only-release guarantees continue passing, with new regression tests for both warnings.
- No live credentials, Docker builds, remote writes, consumer migrations, or destructive operations are used to implement or test this patch. No production deletion attestation is fabricated or enabled.

## Risks And Decisions

- OCI/Buildx artifact shapes vary. Support explicit tested forms, document them, and fail closed for unknown encodings instead of treating every unsupported architecture as an artifact. This patch does not promise universal OCI artifact compatibility.
- Complete graph protection may retain more historical content and require more registry reads. Safety takes priority over aggressive garbage collection; caching is limited to immutable evidence within a fresh scan.
- Changes to `Registry.graph()` are internal and require coordinated updates to its callers and fakes, not a checkpoint/bootstrap schema migration. Pending inventories accepted under matching checkpoint identity remain untrusted inputs that need current safety checks. Keeping schema 1 does not make checkpoints portable across template revisions; cross-revision adoption is explicitly deferred.
- Transaction-relative survivors may force a previously valid digest deletion to stop when a newly discovered older alias would otherwise be eligible for removal. This is intentional: retaining content is safer than silently broadening a persisted deletion inventory. Replanning authority must be explicit and is not added by this patch.
- Fresh checks still cannot provide distributed compare-and-swap across Forgejo and the registry. Keep the existing single-publisher requirement, local destination lock, and independently attested deletion gate.
- Tests prove local candidate selection and classification behavior, not real Forgejo storage/deletion semantics. Live contract verification remains a separately authorized operation.
