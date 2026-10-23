#!/usr/bin/env bash
set -Eeuo pipefail
set +x
export PYTHONDONTWRITEBYTECODE=1
case "${1:-}" in
  --help)
    [[ $# == 1 ]] || exit 2
    echo 'Usage: ./scripts/release.sh [--validate | --help]'
    echo 'No arguments: build and publish the configured project. Setup: scripts/release.json and a private token file.'
    exit 0 ;;
  --validate|'') ;;
  *) echo 'Unsupported arguments; use scripts/legacy-release.sh for the old Python CLI.' >&2; exit 2 ;;
esac
[[ $# -le 1 ]] || exit 2
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
source "$root/scripts/release-common.sh"
command -v python3 >/dev/null || stop 'Install Python 3.11 or later (no jq required)'
if [[ "${1:-}" == --validate ]]; then
  # /dev/null is a deliberate output sink; this path creates no lock, temp state, or credentials.
  data settings "$root" /dev/null
  echo 'Configuration valid; no credentials or remote operations used'
  exit 0
fi
for tool in git docker curl; do
  command -v "$tool" >/dev/null || stop "Required command unavailable: $tool"
done
for marker in release-template.lock.json scripts/release-template .template-transaction; do
  [[ ! -e "$root/$marker" && ! -L "$root/$marker" ]] || stop 'Managed/unfinished legacy installation; use its original pin and legacy-release.sh'
done
if [[ -z "${RELEASE_LOCK_FD:-}" ]]; then
  exec python3 -B "$root/scripts/release-data.py" locked "$root" "$root/scripts/release.sh"
fi
data lock-check "$root"
umask 077
work=$(mktemp -d "${TMPDIR:-/tmp}/bash-release.XXXXXXXX")
phase='local setup'
cleanup() { rm -rf -- "$work"; }
trap cleanup EXIT
trap 'echo "Publication incomplete/uncertain during $phase; inspect exact remaining objects without rollback" >&2' ERR
trap 'exit 130' INT
trap 'exit 143' TERM
data settings "$root" "$work/settings.json"
tag=$(field "$work/settings.json" tag)
version=$(field "$work/settings.json" version)
origin=$(field "$work/settings.json" gitea)
repository=$(field "$work/settings.json" repository)
image=$(field "$work/settings.json" image)
printf 'Release target: %s / %s (%s)\n' "$repository" "$image" "$tag"
[[ ! -e "$root/.release-template/$tag.json" && ! -L "$root/.release-template/$tag.json" ]] || stop 'Legacy checkpoint exists; preserve its original checkout/pin'
phase='source and builder preflight'
run 1048576 60 docker buildx inspect --bootstrap
data platforms "$work/command.out"
commit=$(data source "$root")
# Validate captured notes before reading credentials or doing any registry write.
data payload "$root" "$commit" "$work/payload.json"
data auth "$root" "$work"
registry_host=${image%%/*}
original_docker_config=${DOCKER_CONFIG:-$HOME/.docker}
export BUILDX_CONFIG=${BUILDX_CONFIG:-$original_docker_config/buildx}
run 65536 60 docker context show
context=$(cat "$work/command.out")
export DOCKER_CONFIG="$work/docker"
export DOCKER_CONTEXT="$context"
phase='read-only startup classification'
data inventory "$root" "$work" "$work/inventory.json"
tag_state
if [[ -n "$remote_oid" || -n "$release_record" ]]; then
  [[ -n "$remote_oid" && -n "$release_record" && "$remote_commit" == "$commit" ]] || stop 'Ambiguous tag-only/release-only or conflicting startup state; inspect without repair'
  phase='completed-publication verification'
  run 1048576 60 git -C "$root" fetch --no-tags --no-write-fetch-head origin "$remote_oid"
  data inspect-tag "$root" "$commit" "$remote_oid" "$work/identity.json"
  prepared=$(field "$work/identity.json" digest)
  printf '%s\n' "$release_record" > "$work/release.json"
  data release-check "$root" "$commit" "$work/release.json"
  [[ $(data image "$root" "$work" "$prepared" "$commit") == "$prepared" ]] || stop 'Bound image differs'
  [[ $(data resolve "$root" "$work" latest) == "$prepared" ]] || stop 'Completed latest is missing or foreign; no repair authority'
  scan
  [[ $(field "$work/inventory.json" object) == "$remote_oid" && $(field "$work/inventory.json" commit) == "$commit" ]] || stop 'Completed tag changed'
  field "$work/inventory.json" release > "$work/release.json"
  data release-check "$root" "$commit" "$work/release.json"
  [[ $(data resolve "$root" "$work" latest) == "$prepared" ]] || stop 'Completed latest changed during verification'
  success
  exit 0
fi
phase='fresh-publication preparation'
run 65536 60 git -C "$root" tag --list "$tag"
[[ ! -s "$work/command.out" ]] || stop 'Local tag exists without a remote publication; inspect before building'
predecessor=$(data resolve "$root" "$work" latest)
config_hash=$(field "$work/settings.json" config_hash)
staging="rt-${version}-${commit}-${config_hash#sha256:}"
prepared=$(data image "$root" "$work" "$staging" "$commit" missing)
if [[ -z "$prepared" ]]; then
  fresh_guard
  login
  data snapshot "$root" "$commit" "$work/source"
  phase='staging build and immutable verification'
  run 16777216 7200 docker buildx build --platform linux/amd64,linux/arm64 --provenance=false \
    --metadata-file "$work/build.json" --push --tag "$image:$staging" \
    --label "org.opencontainers.image.version=$version" --label "org.opencontainers.image.revision=$commit" \
    --label "org.opencontainers.image.source=$origin/$repository" --file "$work/source/Dockerfile" "$work/source"
  prepared=$(data image "$root" "$work" "$staging" "$commit")
  data metadata "$work/build.json" "$prepared"
else
  login
fi
oid=$(data make-tag "$root" "$commit" "$prepared" "$predecessor" "$work/identity.json")
phase='tag publication'
fresh_guard
# A failed response may follow an accepted write. Reconcile exactly; never force or roll back.
attempt run 1048576 60 git -C "$root" push origin "$oid:refs/tags/$tag"
scan
tag_state
[[ "$remote_oid" == "$oid" && "$remote_commit" == "$commit" && -z "$release_record" ]] || stop 'Tag push not confirmed or release appeared'
phase='digest promotion'
fresh_guard
if [[ $(data resolve "$root" "$work" latest) != "$prepared" ]]; then
  attempt run 1048576 60 docker buildx imagetools create --tag "$image:latest" "$image@$prepared"
fi
[[ $(data resolve "$root" "$work" latest) == "$prepared" ]] || stop 'Promotion not confirmed'
phase='release creation'
fresh_guard
attempt data http "$work" POST "$origin/api/v1/repos/$repository/releases" "$work/post.json" "$work/payload.json" > "$work/post.status"
phase='final publication verification'
scan
tag_state
[[ "$remote_oid" == "$oid" && "$remote_commit" == "$commit" && -n "$release_record" ]] || stop 'Release creation not confirmed'
printf '%s\n' "$release_record" > "$work/release.json"
data release-check "$root" "$commit" "$work/release.json"
[[ $(data image "$root" "$work" "$prepared" "$commit") == "$prepared" && $(data resolve "$root" "$work" latest) == "$prepared" ]] || stop 'Final image verification failed'
success
