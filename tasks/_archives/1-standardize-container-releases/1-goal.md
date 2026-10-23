- [command](#command)
- [goal](#goal)

## command

Create a shared container-release template repository using `home-web` releases as the starting point, then adopt it across all seven repositories: `dev-docker`, `home-web`, `yt-web`, `my-library`, `my-rss`, `baikal-docker`, and `ntr-server`. After successfully publishing the latest release, delete older Docker image package versions and older Forgejo releases. Publish release description text only, without image archives such as `img.tar.gz`, checksum files such as `img.tar.gz.sha256`, or other attachments. Keep this goal under `~/workdir/tasks/` and do not touch any repositories yet.

## goal

Provide a shared, versioned release-template repository with reusable release scripts, cleanup safety tests, and per-project settings for image names, builds, and checks. Adapt the `home-web` workflow to publish text-only Forgejo releases and remove older releases and Docker image versions only after the latest publication succeeds. Preserve the current images and their required multi-platform manifests during cleanup. Adopt the template across all seven repositories with pinned template versions and an explicit update process so fixes do not drift between projects. At this goal stage, create no repositories, change no existing repository files, and perform no releases or remote deletions.
