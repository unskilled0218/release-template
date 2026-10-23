# Installation and updates

- [Installation and updates](#installation-and-updates)
  - [Explicit installation](#explicit-installation)
  - [Pinned updates](#pinned-updates)
  - [Interrupted transactions](#interrupted-transactions)

## Explicit installation

Installation into existing projects is deferred to a separate adoption task. The following commands describe future approved use; do not run them against the seven reference projects during template development. The destination must already exist, and initial managed paths and launchers must be absent. Example configuration and hooks are selected separately, not silently overwritten by the installer.

From a trusted checkout of this template, select an exact 40-character committed revision:

```sh
python3 -B scripts/update.py /approved/consumer --revision <40-character-commit> --dry-run
python3 -B scripts/update.py /approved/consumer --revision <40-character-commit>
python3 -B scripts/update.py /approved/consumer --verify
```

The installer reads files from that Git object, not modified working-tree copies or a mutable branch. It installs only Python engine files beneath `scripts/release-template/`, stable `scripts/launch.py` and `scripts/release.sh`, and `release-template.lock.json`. The lock records upstream version, commit, bootstrap protocol, and SHA-256 inventory. Configuration, project hooks, and all other files stay outside the managed inventory.

Before committing future consumer adoption, add the patterns in `examples/consumer.gitignore` to that project's ignore rules through its own reviewed change. The installer does not change `.gitignore`, README, source, Dockerfiles, or configuration. The managed Python runtime does not generate bytecode during release. Unexpected managed-directory files, symlink destinations, absolute inventory paths, traversal, and user-modified managed files are refused.

## Pinned updates

Use the same explicit update command with a newly reviewed immutable revision. Dry-run lists replaced/removed paths without replacing consumer files; it may create the destination operation lock. Before writing, the updater verifies every old managed checksum and prepares the full new inventory. Obsolete files are removed only if they are in the old managed inventory and remain unchanged. Review and commit the resulting consumer diff as a separate adoption/update change.

Releases execute vendored pinned files without network updates. The stable launcher lives outside the changing engine and validates the installed inventory before importing it. Bootstrap protocol 1 does not automatically update bootstrap code: a source revision with changed stable launcher bytes is refused until a separately reviewed bootstrap migration exists. This avoids replacing the guard that protects a multi-file update while a release is starting.

Managed-code upgrades do not migrate release checkpoints. Checkpoint identity includes the exact template commit as well as source/configuration identity; the new pin rejects an old-pin checkpoint even when both use schema 1. Same-revision retries remain supported. Preserve old checkpoints and publication provenance for a separately reviewed operator procedure. Do not rewrite identity fields, discard checkpoints, roll source backward, or run vulnerable old-code cleanup as an upgrade workaround. Version 0.1.1 supplies no cross-revision adoption command.

## Interrupted transactions

The updater and launcher share `.template-operation.lock` using nonblocking POSIX `flock` for their whole operation. A second update or release fails promptly. Supported destinations are Linux/POSIX local filesystems with atomic same-filesystem replacement, file/directory `fsync`, and working advisory locks. Network filesystems and external writers that ignore this protocol are not supported.

Updates prepare staged bytes/backups and a durable `.template-transaction/journal.json` before replacing files. The lock record is replaced last; an in-progress directory prevents the launcher from importing a mixed engine. On interruption, use the standalone updater from a trusted template checkout, not code from the partial installation:

```sh
python3 -B scripts/update.py /approved/consumer --recover complete
python3 -B scripts/update.py /approved/consumer --recover restore
```

Recovery validates the entire transaction before any write, comparing current files against recorded old/new hashes. It refuses conflicting external changes and never discards user edits. A kill during preparation has not changed destination files; incomplete staging can be discarded when its contents are recognizable. Unknown staging content needs manual inspection. Once transaction staging is being retired after successful verification, completion may still finish, but restoration can be unavailable if backups have already been retired; do not treat this cleanup phase as a rollback guarantee.
