#!/usr/bin/env bash
# Shared shell boundaries. JSON and bounded binary I/O live in release-data.py, not the legacy engine.

data() { python3 -B "$root/scripts/release-data.py" "$@"; }
field() { data field "$1" "$2"; }
progress() { printf 'Release progress: %s\n' "$1" >&2; }
stage() { phase=$1; progress "$phase"; }
recovery() {
  case "${phase:-local setup}" in
    'checkout locking'|'checkout lock verification')
      echo 'Next: inspect or wait for the active checkout lock owner; check checkout access and filesystem lock support. Do not delete or bypass the lock.' >&2 ;;
    'temporary storage')
      echo 'Next: check a valid writable temporary parent, available space, and permissions; review TMPDIR and docs/bash-configuration.md. Do not bypass checkout locking.' >&2 ;;
    'local setup'|'prerequisite checks')
      echo 'Next: review required tools, configuration, and checkout locking in docs/bash-configuration.md.' >&2 ;;
    'builder readiness')
      echo 'Next: check Docker access, the selected context/host, Buildx installation, and builder availability; see docs/release-process.md#troubleshooting.' >&2 ;;
    'platform readiness')
      echo 'Next: select native nodes or ask an administrator to prepare emulation for linux/amd64 and linux/arm64; see docs/platform-preparation.md. No privileged setup runs automatically.' >&2 ;;
    'source verification'|'release notes validation'|'source snapshot')
      echo 'Next: check clean main, effective Git remotes, already-pushed source, committed notes, and snapshot inputs; see docs/bash-configuration.md.' >&2 ;;
    'credential preparation'|'registry login')
      echo 'Next: check private token ownership/mode, account permissions, and independent Git authentication; see docs/bash-configuration.md#credentials-and-prerequisites.' >&2 ;;
    'Docker connection selection')
      echo 'Next: check the selected Docker context/host and its TLS metadata; see docs/bash-configuration.md#credentials-and-prerequisites.' >&2 ;;
    'staging build and immutable verification')
      echo 'Next: check Dockerfile/application build prerequisites for both platforms and registry push access; see docs/release-process.md#troubleshooting.' >&2 ;;
    *)
      echo 'Next: check Git/Gitea/registry connectivity, DNS, HTTPS trust, account permissions, and exact identity evidence; see docs/release-process.md#troubleshooting.' >&2 ;;
  esac
  if [[ "${publication_state:-none}" == possible ]]; then
    echo 'Publication incomplete/uncertain: inspect exact remaining objects without rollback; follow docs/bash-publication.md#retry-states. Do not blindly retry, delete, rewrite tags, or reassign packages.' >&2
  else
    echo 'No publication writes were sent by this invocation; existing remote state may still need inspection. Follow docs/bash-publication.md#retry-states before retrying.' >&2
  fi
}
stop() { echo "Release stopped (${phase:-local setup}): $*" >&2; recovery; exit 1; }
unexpected_failure() {
  local status=$?
  # The parent reports failed command substitutions; do not duplicate their diagnostics.
  if [[ $BASH_SUBSHELL == 0 ]]; then
    printf 'Release stopped (%s): operation failed\n' "${phase:-local setup}" >&2
    recovery
  fi
  return "$status"
}
interrupted() {
  printf 'Release stopped (%s): operation interrupted\n' "${phase:-local setup}" >&2
  recovery
  exit "$1"
}
run() { data run "$1" "$2" "$work/command.out" "${@:3}"; }
login() {
  stage 'registry login'
  data run-input 1048576 60 "$work/login.out" "$work/token" docker login "$registry_host" \
    --username "$(cat "$work/login")" --password-stdin
}
attempt() {
  local status
  if "$@"; then return 0; else status=$?; fi
  # Only transport/command failures may reconcile accepted writes. Resource or input refusals stop.
  [[ "$status" == 2 ]] || stop 'Input/resource refusal; remote outcome may be incomplete'
}
scan() {
  data source "$root" "$commit" >/dev/null || stop 'Cannot verify captured source'
  data settings "$root" "$work/current.json" || stop 'Cannot read current settings'
  cmp -s "$work/settings.json" "$work/current.json" || stop 'Captured configuration/scripts changed'
  data inventory "$root" "$work" "$work/inventory.json" || stop 'Cannot verify complete inventory'
}
tag_state() {
  remote_oid=$(field "$work/inventory.json" object) || stop 'Cannot read observed tag object'
  remote_commit=$(field "$work/inventory.json" commit) || stop 'Cannot read observed peeled commit'
  release_record=$(field "$work/inventory.json" release) || stop 'Cannot read observed release'
}
alias_guard() {
  local current
  current=$(data resolve "$root" "$work" latest) || stop 'Cannot verify latest alias'
  if [[ "${promotion_confirmed:-false}" == true ]]; then
    [[ "$current" == "$prepared" ]] || stop 'Confirmed latest disappeared or changed'
  else
    [[ "$current" == "$predecessor" || "$current" == "$prepared" ]] || stop 'Latest changed since preparation'
  fi
}
fresh_guard() {
  scan
  tag_state
  [[ -z "$release_record" ]] || stop 'Requested release appeared during publication'
  if [[ "$tag_confirmed" == true ]]; then
    [[ "$remote_oid" == "$oid" && "$remote_commit" == "$commit" ]] || stop 'Confirmed tag disappeared or changed'
  else
    [[ -z "$remote_oid" || ( -n "${oid:-}" && "$remote_oid" == "$oid" && "$remote_commit" == "$commit" ) ]] || stop 'Requested tag changed'
  fi
  alias_guard
}
publication_guard() {
  local expected_oid=$1 current_image current_latest
  scan
  tag_state
  [[ "$remote_oid" == "$expected_oid" && "$remote_commit" == "$commit" && -n "$release_record" ]] || stop 'Completed publication changed before association'
  printf '%s\n' "$release_record" > "$work/release.json"
  data release-check "$root" "$commit" "$work/release.json" || stop 'Cannot verify release before association'
  current_image=$(data image "$root" "$work" "$prepared" "$commit") || stop 'Cannot verify bound image before association'
  [[ "$current_image" == "$prepared" ]] || stop 'Bound image changed before association'
  current_latest=$(data resolve "$root" "$work" latest) || stop 'Cannot verify latest before association'
  [[ "$current_latest" == "$prepared" ]] || stop 'Latest differs before association'
}
associate_package() {
  local expected_oid=$1
  stage 'package association'
  publication_guard "$expected_oid"
  publication_state=possible
  data package-ensure "$root" "$work" || stop 'Package association failed or uncertain'
  stage 'final association verification'
  publication_guard "$expected_oid"
  data package-check "$root" "$work" || stop 'Cannot verify final package association'
}
success() {
  printf 'Publication verified: %s\nImage: %s@%s\nLatest: %s:latest\nRelease: %s/%s/releases/tag/%s\n' \
    "$tag" "$image" "$prepared" "$image" "$origin" "$repository" "$tag"
}
