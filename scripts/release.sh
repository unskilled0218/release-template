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
  *) echo 'Unsupported arguments. Usage: ./scripts/release.sh [--validate | --help]' >&2; exit 2 ;;
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
publication_state=none
if [[ -z "${RELEASE_LOCK_FD:-}" ]]; then stage 'prerequisite checks'; fi
for tool in git docker curl; do
  command -v "$tool" >/dev/null || stop "Required command unavailable: $tool. Install $tool and make it available on PATH (Docker also needs Buildx)"
done
for marker in release-template.lock.json scripts/release-template .template-transaction; do
  [[ ! -e "$root/$marker" && ! -L "$root/$marker" ]] || stop 'Old installation state; use its preserved original checkout/pin, not this command'
done
if [[ -z "${RELEASE_LOCK_FD:-}" ]]; then
  stage 'checkout locking'
  exec python3 -B "$root/scripts/release-data.py" locked "$root" "$root/scripts/release.sh"
fi
stage 'checkout lock verification'
data lock-check "$root" || stop 'Cannot verify inherited checkout lock'
umask 077
stage 'temporary storage'
work=$(mktemp -d "${TMPDIR:-/tmp}/bash-release.XXXXXXXX" 2>/dev/null) || stop 'Cannot create private temporary directory'
cleanup() { rm -rf -- "$work"; }
trap cleanup EXIT
trap unexpected_failure ERR
trap 'interrupted 130' INT
trap 'interrupted 143' TERM
stage 'local setup'
data settings "$root" "$work/settings.json"
tag=$(field "$work/settings.json" tag)
version=$(field "$work/settings.json" version)
origin=$(field "$work/settings.json" gitea)
repository=$(field "$work/settings.json" repository)
image=$(field "$work/settings.json" image)
printf 'Release target: %s / %s (%s)\n' "$repository" "$image" "$tag"
[[ ! -e "$root/.release-template/$tag.json" && ! -L "$root/.release-template/$tag.json" ]] || stop 'Legacy checkpoint exists; preserve its original checkout/pin'
stage 'builder readiness'
original_docker_context=${DOCKER_CONTEXT-}
original_docker_config=${DOCKER_CONFIG:-$HOME/.docker}
run 1048576 60 docker buildx inspect --bootstrap
stage 'platform readiness'
data platforms "$work/command.out"
progress 'builder advertises linux/amd64 and linux/arm64'
stage 'source verification'
commit=$(data source "$root") || stop 'Cannot verify release source'
# Validate captured notes before reading credentials or doing any registry write.
stage 'release notes validation'
data payload "$root" "$commit" "$work/payload.json"
stage 'credential preparation'
data auth "$root" "$work"
registry_host=${image%%/*}
export BUILDX_CONFIG=${BUILDX_CONFIG:-$original_docker_config/buildx}
stage 'Docker connection selection'
run 65536 60 docker context show
context=$(cat "$work/command.out") || stop 'Cannot read selected Docker context'
[[ -n "$context" && "$context" != *$'\n'* && "$context" != *$'\r'* ]] || stop 'Invalid selected Docker context'
export DOCKER_CONFIG="$work/docker"
# Selecting default here would override an otherwise host-only connection.
if [[ "$context" != default || -n "$original_docker_context" ]]; then
  export DOCKER_CONTEXT="$context"
else
  unset DOCKER_CONTEXT
fi
stage 'read-only startup classification'
data inventory "$root" "$work" "$work/inventory.json"
tag_state
if [[ -n "$remote_oid" || -n "$release_record" ]]; then
  [[ -n "$remote_oid" && -n "$release_record" && "$remote_commit" == "$commit" ]] || stop 'Ambiguous tag-only/release-only or conflicting startup state; inspect without repair'
  publication_state=possible
  stage 'completed-publication verification'
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
  associate_package "$remote_oid"
  success
  exit 0
fi
stage 'fresh-publication preparation'
tag_confirmed=false
promotion_confirmed=false
run 65536 60 git -C "$root" tag --list "$tag"
[[ ! -s "$work/command.out" ]] || stop 'Local tag exists without a remote publication; inspect before building'
predecessor=$(data resolve "$root" "$work" latest) || stop 'Cannot capture predecessor alias'
config_hash=$(field "$work/settings.json" config_hash)
staging="rt-${version}-${commit}-${config_hash#sha256:}"
stage 'staging lookup'
prepared=$(data image "$root" "$work" "$staging" "$commit" missing) || stop 'Cannot verify staging evidence'
if [[ -z "$prepared" ]]; then
  fresh_guard
  login
  stage 'source snapshot'
  data snapshot "$root" "$commit" "$work/source"
  stage 'staging build and immutable verification'
  progress 'starting multi-platform build; staging may be pushed during this operation'
  publication_state=possible
  run 16777216 7200 docker buildx build --platform linux/amd64,linux/arm64 --provenance=false \
    --metadata-file "$work/build.json" --push --tag "$image:$staging" \
    --label "org.opencontainers.image.version=$version" --label "org.opencontainers.image.revision=$commit" \
    --label "org.opencontainers.image.source=$origin/$repository" --file "$work/source/Dockerfile" "$work/source"
  prepared=$(data image "$root" "$work" "$staging" "$commit") || stop 'Cannot verify built image'
  data metadata "$work/build.json" "$prepared"
  progress 'staging build and immutable verification complete'
else
  progress 'reusing verified staging image; no build needed'
  login
fi
stage 'local tag preparation'
oid=$(data make-tag "$root" "$commit" "$prepared" "$predecessor" "$work/identity.json") || stop 'Cannot create exact intended tag'
stage 'tag publication'
fresh_guard
# A failed response may follow an accepted write. Reconcile exactly; never force or roll back.
publication_state=possible
attempt run 1048576 60 git -C "$root" push origin "$oid:refs/tags/$tag"
scan
tag_state
[[ "$remote_oid" == "$oid" && "$remote_commit" == "$commit" && -z "$release_record" ]] || stop 'Tag push not confirmed or release appeared'
tag_confirmed=true
progress 'tag publication confirmed'
stage 'digest promotion'
fresh_guard
promotion_latest=$(data resolve "$root" "$work" latest) || stop 'Cannot read latest before promotion'
[[ "$promotion_latest" == "$predecessor" || "$promotion_latest" == "$prepared" ]] || stop 'Latest changed before promotion'
if [[ "$promotion_latest" != "$prepared" ]]; then
  attempt run 1048576 60 docker buildx imagetools create --tag "$image:latest" "$image@$prepared"
else
  progress 'latest already matches the prepared digest; skipping promotion'
fi
confirmed_latest=$(data resolve "$root" "$work" latest) || stop 'Cannot verify promotion'
[[ "$confirmed_latest" == "$prepared" ]] || stop 'Promotion not confirmed'
promotion_confirmed=true
progress 'digest promotion verified'
stage 'release creation'
fresh_guard
attempt data http "$work" POST "$origin/api/v1/repos/$repository/releases" "$work/post.json" "$work/payload.json" > "$work/post.status"
stage 'final publication verification'
scan
tag_state
[[ "$remote_oid" == "$oid" && "$remote_commit" == "$commit" && -n "$release_record" ]] || stop 'Release creation not confirmed'
printf '%s\n' "$release_record" > "$work/release.json"
data release-check "$root" "$commit" "$work/release.json"
[[ $(data image "$root" "$work" "$prepared" "$commit") == "$prepared" && $(data resolve "$root" "$work" latest) == "$prepared" ]] || stop 'Final image verification failed'
associate_package "$oid"
success
