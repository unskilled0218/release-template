#!/usr/bin/env bash
# Shared shell boundaries. JSON and bounded binary I/O live in release-data.py, not the legacy engine.

data() { python3 -B "$root/scripts/release-data.py" "$@"; }
field() { data field "$1" "$2"; }
stop() { echo "Release stopped (${phase:-local setup}): $*; inspect partial state without rollback" >&2; exit 1; }
run() { data run "$1" "$2" "$work/command.out" "${@:3}"; }
login() {
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
  [[ "$current" == "$predecessor" || "$current" == "$prepared" ]] || stop 'Latest changed since preparation'
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
  phase='package association'
  publication_guard "$expected_oid"
  data package-ensure "$root" "$work" || stop 'Package association failed or uncertain'
  publication_guard "$expected_oid"
  data package-check "$root" "$work" || stop 'Cannot verify final package association'
}
success() {
  printf 'Publication verified: %s\nImage: %s@%s\nLatest: %s:latest\nRelease: %s/%s/releases/tag/%s\n' \
    "$tag" "$image" "$prepared" "$image" "$origin" "$repository" "$tag"
}
