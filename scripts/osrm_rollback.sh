#!/usr/bin/env bash
# Point osrm-data/current at the previous build and recreate the three containers.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OSRM_DATA="${OSRM_DATA:-$ROOT/osrm-data}"

log() { echo "[osrm-rollback $(date '+%Y-%m-%dT%H:%M:%S%z')] $*"; }

compose() {
  docker compose --profile osrm -f "$ROOT/docker-compose.yml" --project-directory "$ROOT" "$@"
}

if [[ ! -L "$OSRM_DATA/previous" && ! -d "$OSRM_DATA/previous" ]]; then
  log "ERROR: no previous build at $OSRM_DATA/previous"
  exit 1
fi

prev="$(readlink -f "$OSRM_DATA/previous")"
if [[ ! -d "$prev" ]]; then
  log "ERROR: previous target missing: $prev"
  exit 1
fi

curr=""
if [[ -L "$OSRM_DATA/current" || -d "$OSRM_DATA/current" ]]; then
  curr="$(readlink -f "$OSRM_DATA/current")"
fi

if [[ -d "$OSRM_DATA/current" && ! -L "$OSRM_DATA/current" ]]; then
  log "ERROR: $OSRM_DATA/current is a real directory (expected symlink)"
  exit 1
fi

ln -sfn "$prev" "$OSRM_DATA/current"
if [[ -n "$curr" && "$curr" != "$prev" ]]; then
  ln -sfn "$curr" "$OSRM_DATA/previous"
fi
log "current -> $prev"

for svc in osrm-car osrm-bicycle osrm-foot; do
  log "recreate $svc"
  compose up -d --force-recreate "$svc"
done

log "done"
