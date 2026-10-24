# Goal

- [Goal](#goal)
  - [command](#command)
  - [goal](#goal-1)

## command

Make the release process as simple as possible using a Bash script like `~/workdir/home-web/scripts/release.sh`, with a straightforward `container-release-template/` layout containing `scripts/release.sh`, any necessary supporting files under `scripts/`, and a root `Dockerfile`. The request names `~/workdir/home-web-scripts/release.sh`; that path does not exist, so the previously discussed home-web script is the assumed reference.

## goal

Simplify this project into a small Bash-based container release template that builds and publishes through `./scripts/release.sh`, rather than requiring users to understand the current Python release engine and its explicit CLI arguments. Keep the project layout centered on a root `Dockerfile` and release scripts, with minimal required setup and clear credential handling. Preserve essential source/version checks and safe failure behavior; do not copy the reference project's credentials or hard-coded publication target. This goal authorizes no implementation, live publication, resource deletion, or changes to home-web.
