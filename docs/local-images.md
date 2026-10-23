# Local image removal

- [Local image removal](#local-image-removal)
  - [Ownership and daemon binding](#ownership-and-daemon-binding)
  - [Hook observations and retries](#hook-observations-and-retries)
  - [Removal and outcomes](#removal-and-outcomes)

## Ownership and daemon binding

`remove_local_images: true` opts publication/resume into final removal of proven release-owned local copies. It defaults to false; the Ubuntu fixture enables it. This is not remote package cleanup, broad Docker garbage collection, or authorization to wipe a shared daemon.

Before project checks, hooks, builds, or runtime pulls, the engine durably records a versioned `local_finalization` section in the existing schema-1 checkpoint. It stores the run, selected context, hashed endpoint identity, successfully queried daemon ID, and original local references/image IDs, including pre-existing untagged images. Connection credentials and TLS material are not stored. Baseline and progress remain outside immutable publication identity and retirement metadata.

Every resume retains that original baseline; a fresh inventory is only current evidence. A context name repointed to another daemon cannot authorize removal. Unavailable identities, malformed ownership records, or a missing baseline after release operations began require explicit recovery rather than retrospective adoption. Keep the original source/config/pin/checkpoint; changing them cannot repair ownership.

## Hook observations and retries

The engine journals exact configured immutable verification-pull references and declared platforms before invoking a hook. A cooperating hook writes the private bounded observation journal described in [configuration](configuration.md), recording inspected local image IDs after successful pulls. The Ubuntu hook uses this protocol. Registry index digests and local image IDs are distinct identities; a store that cannot establish the relationship safely leaves an explicit skip.

Crash recovery retains pending intents and original ownership. A private journal flushed before the parent dies can be merged on retry; missing or uncertain observations never become deletion authority. Opaque custom build/verify hooks remain usable, but undeclared/unproven effects are preserved and reported when relevant configured references are observable. The tool does not infer ownership from labels, name prefixes, or successful publication. Custom hooks may create unobservable unrelated/untagged effects, which remain outside the engine's removal authority.

No other local writer may concurrently create or reassign the exact references while ownership is being established or removal runs. Fresh checks cannot identify who pulled identical content. Coordinate externally; when provenance is uncertain, skip. Broad daemon isolation or locking services are not introduced.

For independent post-release verification, use the same matching `Workflow` and daemon under private auth: call `local.start()`, then `local.declare(exact_digest_reference, platforms)` before the pull. Supply that declaration as the hook's `local_images` input, call `local.observe(declaration)` after successful hook execution, call `verify_publication()` in this invocation, and only then call `local.finalize()`. Keep the authoritative state directory and perform the final pass after all alias/platform/retry checks. Uninstrumented manual pulls are not automatically adopted for removal.

## Removal and outcomes

Removal begins only after publication is verified in this invocation and required runtime checks finish. A persisted `published` flag alone is insufficient. Each operation uses exactly `docker image rm --no-prune <owned-reference>` without force. Implicit deletion of untagged parents is disabled. Pre-existing references/IDs, named bases, untagged ancestors, changed identities, unrelated/shared tags or digest references, and any running/stopped container use protect the image. Identity, shared-reference evidence, daemon binding, and container use are rechecked before removal.

There are no image/system/builder prune commands, blanket dangling-image deletion, all-ID removal, container deletion, remote DELETE calls, or iteration over other daemons/builders. Default push-only builds may leave no local staging/final aliases. Only explicitly declared observed immutable hook-pull references gain automatic removal authority; other new relevant aliases are reported as undeclared effects, not guessed to be owned.

Outcomes are `removed`, `already absent`, `safely skipped: <reason>`, or `failed: <reason>`. Confirmed absence requires a successful inventory, not a daemon/query failure. Per-reference removal intent/progress survives interruption. A lost removal response reconciles absence without repeating removal. Safe skips can legitimately leave copies behind; shared-layer and builder-cache retention means free-space recovery is not guaranteed.

The CLI reports publication, remote cleanup, and local outcomes separately. Missing remote deletion evidence still returns cleanup incomplete but does not suppress local finalization after verified publication. A local failure returns a separate incomplete-local-cleanup diagnostic without erasing remote errors, republishing, changing package links, or enabling deletion. Failed publication and read-only modes perform no local removal. Local observations/checkpoints remain for recovery; the published registry image is untouched and can be pulled again later.
