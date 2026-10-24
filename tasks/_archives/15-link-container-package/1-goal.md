- [command](#command)
- [goal](#goal)

## command

Update the release workflow to link the published container package to the repository configured in `scripts/release.json`, so it appears in the repository’s Packages tab. Use the Gitea package association API with existing credentials, preserve correct associations, refuse conflicting associations, verify links after linking and on completed-publication retries, and cover the behavior with tests and documentation.

## goal

The configured container package appears in the configured repository’s Packages tab after a successful release. Only that package is linked; existing correct links remain unchanged, and links to other repositories are never reassigned. Association failures are reported without deleting packages or rolling back published objects. Tests cover unlinked, correctly linked, conflicting, and failed associations, including completed-publication retries. Documentation describes the supported behavior. This task record makes no implementation changes or live publication requests.
