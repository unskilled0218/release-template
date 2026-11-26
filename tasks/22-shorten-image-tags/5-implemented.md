# Implementation

- [Implementation](#implementation)

Version 0.7.0 builds to the plain version tag and promotes the same digest to `latest`. Both tags are checked before package association and again before success. Retries refuse a conflicting version rather than moving it.

Ten targeted tests passed: five interface checks and five publication cases covering exact tag names and completed retries, interrupted-build reuse, version collision, destination drift and latest-tag drift. Bash syntax, offline validation and diff checks passed. No live publication was run.
