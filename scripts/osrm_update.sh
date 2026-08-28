#!/usr/bin/env bash
# Build (or refresh) Moscow OSRM graphs for car / bicycle / foot, then promote.
# First run = initial prepare. Weekly timer: monitor-osrm-update.timer
# Skip rebuild when the PBF is unchanged (HTTP 304) and current graphs exist.
# Force: OSRM_FORCE=1 ./scripts/osrm_update.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OSRM_DATA="${OSRM_DATA:-$ROOT/osrm-data}"
IMAGE="${OSRM_IMAGE:-ghcr.io/project-osrm/osrm-backend:26.8-debian}"
PBF_URL="${OSRM_PBF_URL:-https://download.openstreetmap.fr/extracts/russia/central_federal_district/moscow-latest.osm.pbf}"
PBF_NAME="moscow-latest.osm.pbf"
FORCE="${OSRM_FORCE:-0}"
KREMLIN="37.6173,55.7558"
CAR_PORT="${OSRM_CAR_PORT:-5000}"
BICYCLE_PORT="${OSRM_BICYCLE_PORT:-5001}"
FOOT_PORT="${OSRM_FOOT_PORT:-5002}"

PROFILES=(car bicycle foot)
PROMOTED=0
BUILD=""

log() { echo "[osrm-update $(date '+%Y-%m-%dT%H:%M:%S%z')] $*"; }

compose() {
  docker compose --profile osrm -f "$ROOT/docker-compose.yml" --project-directory "$ROOT" "$@"
}

current_real() {
  if [[ -L "$OSRM_DATA/current" || -d "$OSRM_DATA/current" ]]; then
    readlink -f "$OSRM_DATA/current"
  fi
}

graphs_present() {
  local p
  for p in "${PROFILES[@]}"; do
    if ! compgen -G "$OSRM_DATA/current/$p/moscow-latest.osrm*" > /dev/null; then
      return 1
    fi
  done
  return 0
}

download_pbf() {
  local tmp="$OSRM_DATA/pbf/${PBF_NAME}.new"
  local headers="$OSRM_DATA/pbf/${PBF_NAME}.headers"
  local etag_file="$OSRM_DATA/pbf/${PBF_NAME}.etag"
  local extra=()
  mkdir -p "$OSRM_DATA/pbf"

  if [[ -f "$OSRM_DATA/pbf/$PBF_NAME" && "$FORCE" != "1" ]]; then
    extra+=(-z "$OSRM_DATA/pbf/$PBF_NAME")
    if [[ -s "$etag_file" ]]; then
      extra+=(-H "If-None-Match: $(tr -d '\r\n' < "$etag_file")")
    fi
  fi

  local code
  code="$(curl -sS -L --retry 3 -w '%{http_code}' -o "$tmp" -D "$headers" "${extra[@]}" "$PBF_URL")"

  if [[ "$code" == "304" ]]; then
    rm -f "$tmp"
    log "PBF unchanged (HTTP 304)"
    return 2
  fi
  if [[ "$code" != "200" ]]; then
    rm -f "$tmp"
    log "ERROR: PBF download HTTP $code"
    return 1
  fi
  if [[ ! -s "$tmp" ]]; then
    rm -f "$tmp"
    log "ERROR: downloaded PBF is empty"
    return 1
  fi
  mv "$tmp" "$OSRM_DATA/pbf/$PBF_NAME"
  grep -i '^etag:' "$headers" | awk '{print $2}' | tr -d '\r' > "$etag_file" || true
  log "PBF saved ($(du -h "$OSRM_DATA/pbf/$PBF_NAME" | awk '{print $1}'))"
  return 0
}

extract_profile() {
  local profile="$1"
  local dir="$BUILD/$profile"
  mkdir -p "$dir"
  if ! ln "$OSRM_DATA/pbf/$PBF_NAME" "$dir/$PBF_NAME" 2>/dev/null; then
    cp "$OSRM_DATA/pbf/$PBF_NAME" "$dir/$PBF_NAME"
  fi

  log "extract $profile"
  docker run --rm -v "$dir:/data" "$IMAGE" \
    osrm-extract -p "/opt/${profile}.lua" "/data/$PBF_NAME"
  log "partition $profile"
  docker run --rm -v "$dir:/data" "$IMAGE" \
    osrm-partition "/data/moscow-latest.osrm"
  log "customize $profile"
  docker run --rm -v "$dir:/data" "$IMAGE" \
    osrm-customize "/data/moscow-latest.osrm"

  rm -f "$dir/$PBF_NAME"
  if ! compgen -G "$dir/moscow-latest.osrm*" > /dev/null; then
    log "ERROR: missing $dir/moscow-latest.osrm* after extract"
    return 1
  fi
}

on_error_cleanup() {
  local rc=$?
  if [[ "$PROMOTED" != "1" && -n "$BUILD" && -d "$BUILD" ]]; then
    log "extract failed — removing staging $BUILD"
    rm -rf "$BUILD"
  fi
  exit "$rc"
}

promote() {
  local old
  old="$(current_real || true)"
  mkdir -p "$OSRM_DATA"

  if [[ -d "$OSRM_DATA/current" && ! -L "$OSRM_DATA/current" ]]; then
    log "ERROR: $OSRM_DATA/current is a real directory (expected symlink). Remove it and re-run."
    return 1
  fi

  if [[ -n "$old" && "$old" != "$BUILD" ]]; then
    ln -sfn "$old" "$OSRM_DATA/previous"
  fi
  ln -sfn "$BUILD" "$OSRM_DATA/current"
  PROMOTED=1
  log "promoted current -> $BUILD"
}

recreate_one() {
  local svc="$1"
  log "recreate $svc"
  compose up -d --force-recreate "$svc"
}

wait_ok() {
  local url="$1"
  local i
  for i in $(seq 1 30); do
    if curl -sf "$url" | grep -q '"code":"Ok"'; then
      return 0
    fi
    sleep 2
  done
  return 1
}

smoke_all() {
  wait_ok "http://127.0.0.1:${CAR_PORT}/nearest/v1/driving/${KREMLIN}" \
    && wait_ok "http://127.0.0.1:${BICYCLE_PORT}/nearest/v1/bike/${KREMLIN}" \
    && wait_ok "http://127.0.0.1:${FOOT_PORT}/nearest/v1/foot/${KREMLIN}"
}

prune_old_builds() {
  local keep_current keep_previous d real
  keep_current="$(current_real || true)"
  keep_previous=""
  if [[ -L "$OSRM_DATA/previous" || -d "$OSRM_DATA/previous" ]]; then
    keep_previous="$(readlink -f "$OSRM_DATA/previous")"
  fi
  shopt -s nullglob
  for d in "$OSRM_DATA/builds"/*; do
    [[ -d "$d" ]] || continue
    real="$(readlink -f "$d")"
    if [[ -n "$keep_current" && "$real" == "$keep_current" ]]; then
      continue
    fi
    if [[ -n "$keep_previous" && "$real" == "$keep_previous" ]]; then
      continue
    fi
    log "prune $d"
    rm -rf "$d"
  done
}

rollback_if_possible() {
  if [[ -x "$ROOT/scripts/osrm_rollback.sh" ]] && { [[ -L "$OSRM_DATA/previous" ]] || [[ -d "$OSRM_DATA/previous" ]]; }; then
    log "smoke failed — rolling back"
    "$ROOT/scripts/osrm_rollback.sh" || true
  else
    log "smoke failed — no previous build to roll back to"
  fi
}

mkdir -p "$OSRM_DATA/pbf" "$OSRM_DATA/builds"

pbf_changed=0
set +e
download_pbf
dl_rc=$?
set -e
if [[ "$dl_rc" -eq 0 ]]; then
  pbf_changed=1
elif [[ "$dl_rc" -eq 2 ]]; then
  pbf_changed=0
else
  exit "$dl_rc"
fi

if [[ ! -f "$OSRM_DATA/pbf/$PBF_NAME" ]]; then
  log "ERROR: no PBF at $OSRM_DATA/pbf/$PBF_NAME"
  exit 1
fi

need_build=0
if [[ "$FORCE" == "1" || "$pbf_changed" -eq 1 ]]; then
  need_build=1
fi
if ! graphs_present; then
  need_build=1
fi

if [[ "$need_build" -eq 0 ]]; then
  log "PBF unchanged and current graphs present — skip"
  exit 0
fi

STAMP="$(date '+%Y-%m-%dT%H%M')"
BUILD="$OSRM_DATA/builds/$STAMP"
mkdir -p "$BUILD"
trap on_error_cleanup EXIT

for profile in "${PROFILES[@]}"; do
  extract_profile "$profile"
done

trap - EXIT
promote

recreate_one osrm-car
recreate_one osrm-bicycle
recreate_one osrm-foot

if ! smoke_all; then
  log "ERROR: smoke-test failed after promote"
  rollback_if_possible
  exit 1
fi

prune_old_builds
log "done"
