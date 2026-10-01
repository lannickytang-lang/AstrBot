#!/usr/bin/env bash
# yuansheng-astrbot server-side deployment script.
#
# Usage:
#   ./server.sh deploy <dist.tar.gz|none> [--tag deploy/<ts>]   full update
#   ./server.sh frontend <dist.tar.gz>                          dist swap only
#   ./server.sh status                                          container/health summary
#   ./server.sh list                                            list deploy tags + backups
#   ./server.sh rollback <ts> [--with-db]                       restore a previous deployment
#
# Design notes:
# - Images are NOT backed up. Rollback = `git reset --hard deploy/<ts>` + rebuild
#   (the git tag is the backup). Old image tags are pruned after each deploy.
# - Backups kept per deployment timestamp: db snapshot + previous dist.
# - Any failure aborts before the container is touched (no half-updates).

set -euo pipefail

APP_DIR="/root/apps/yuansheng-astrbot"
REPO_DIR="$APP_DIR/repo"
DATA_DIR="$APP_DIR/data"
BACKUP_DIR="$APP_DIR/backups"
IMAGE_NAME="yuansheng-astrbot"
KEEP_BACKUPS=5
KEEP_IMAGES=3

cd "$APP_DIR"
mkdir -p "$BACKUP_DIR"

now_ts() { date +%Y%m%d_%H%M; }

log()  { echo "[server.sh] $*"; }
die()  { echo "[server.sh][ERROR] $*" >&2; exit 1; }

require_repo() {
  [ -d "$REPO_DIR/.git" ] || die "repo/ missing at $REPO_DIR"
}

# git fetch --tags + reset --hard to a ref (default origin/dev)
sync_repo() {
  local ref="${1:-origin/dev}"
  log "git fetch --tags --force ..."
  git -C "$REPO_DIR" fetch origin --tags --force --prune
  log "git reset --hard $ref"
  git -C "$REPO_DIR" reset --hard "$ref" >/dev/null
  log "repo at: $(git -C "$REPO_DIR" log --oneline -1)"
}

backup_db() {
  local ts="$1"
  local target="$BACKUP_DIR/db-$ts.db"
  log "backup db -> $(basename "$target")"
  python3 - "$DATA_DIR/data_v4.db" "$target" <<'PY'
import sqlite3, sys
src, dst = sys.argv[1], sys.argv[2]
src_conn = sqlite3.connect(f"file:{src}?mode=ro", uri=True)
dst_conn = sqlite3.connect(dst)
src_conn.backup(dst_conn)
dst_conn.close(); src_conn.close()
PY
}

backup_dist() {
  local ts="$1"
  if [ -d "$DATA_DIR/dist" ]; then
    log "backup dist -> dist-$ts.tar.gz"
    tar czf "$BACKUP_DIR/dist-$ts.tar.gz" -C "$DATA_DIR" dist
  fi
}

swap_dist() {
  local dist_pkg="$1"
  [ -f "$dist_pkg" ] || die "dist package not found: $dist_pkg"
  # sanity: package must contain index.html
  tar tzf "$dist_pkg" | grep -q "index.html" || die "dist package has no index.html"
  rm -rf "$DATA_DIR/dist.new"
  mkdir -p "$DATA_DIR/dist.new"
  tar xzf "$dist_pkg" -C "$DATA_DIR/dist.new"
  [ -f "$DATA_DIR/dist.new/assets/version" ] || die "dist missing assets/version (would trigger upstream overwrite)"
  rm -rf "$DATA_DIR/dist.old-tmp"
  if [ -d "$DATA_DIR/dist" ]; then
    mv "$DATA_DIR/dist" "$DATA_DIR/dist.old-tmp"
  fi
  mv "$DATA_DIR/dist.new" "$DATA_DIR/dist"
  rm -rf "$DATA_DIR/dist.old-tmp"
  log "dist swapped, version=$(cat "$DATA_DIR/dist/assets/version")"
}

sync_plugin() {
  # source of truth in repo; runtime files (state/log) stay untouched
  local src="$REPO_DIR/custom_plugins/kf_human_transfer"
  local dst="$DATA_DIR/plugins/kf_human_transfer"
  [ -d "$src" ] || { log "no plugin in repo, skip"; return; }
  mkdir -p "$dst"
  rsync -a --delete \
    --exclude '__pycache__/' \
    --exclude 'state.json' \
    --exclude 'chat_log.jsonl' \
    "$src/" "$dst/"
  log "plugin synced -> data/plugins/kf_human_transfer"
}

prune_old() {
  log "prune backups (keep $KEEP_BACKUPS) and unused images (keep $KEEP_IMAGES tags)"
  ls -1t "$BACKUP_DIR"/db-*.db 2>/dev/null | tail -n +$((KEEP_BACKUPS + 1)) | xargs -r rm -f
  ls -1t "$BACKUP_DIR"/dist-*.tar.gz 2>/dev/null | tail -n +$((KEEP_BACKUPS + 1)) | xargs -r rm -f
  docker images --format '{{.Repository}}:{{.Tag}} {{.CreatedSince}}' "$IMAGE_NAME" \
    | grep -v ':latest' | sort -t' ' -k2 -r | tail -n +$((KEEP_IMAGES + 1)) \
    | awk '{print $1}' | xargs -r docker rmi 2>/dev/null || true
}

health_check() {
  local ok=1
  for i in 1 2 3; do
    sleep 6
    local container_state code
    container_state="$(docker inspect -f '{{.State.Status}}' yuansheng-astrbot 2>/dev/null || echo missing)"
    code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 http://127.0.0.1:6185/api/stat/versions || echo 000)"
    log "health try $i: container=$container_state api=$code"
    if [ "$container_state" = "running" ] && [ "$code" = "200" ]; then ok=0; break; fi
  done
  if [ $ok -ne 0 ]; then
    log "HEALTH CHECK FAILED — recent logs:"
    docker logs yuansheng-astrbot --tail 20 2>&1 | tail -20
    die "health check failed"
  fi
  local domain_code
  domain_code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 8 http://yuansheng.tudodo.vip/api/stat/versions || echo 000)"
  log "domain check: $domain_code (non-200 is nginx-level, container itself is healthy)"
  log "HEALTH OK"
}

cmd_deploy() {
  local dist_pkg="${1:-none}"
  shift || true
  local ref="origin/dev"
  if [ "${1:-}" = "--tag" ]; then
    ref="${2:?--tag requires a ref like deploy/20261001_2330}"
  fi

  local ts; ts="$(now_ts)"
  require_repo
  sync_repo "$ref"

  log "docker build -> $IMAGE_NAME:$ts (cache-friendly)"
  docker build -t "$IMAGE_NAME:$ts" -t "$IMAGE_NAME:latest" "$REPO_DIR" || die "docker build failed (old container untouched)"

  backup_db "$ts"
  backup_dist "$ts"

  sync_plugin

  if [ "$dist_pkg" != "none" ]; then
    swap_dist "$dist_pkg"
  fi

  log "compose up (image=$IMAGE_NAME:$ts)"
  sed -i "s|image: $IMAGE_NAME:.*|image: $IMAGE_NAME:$ts|" docker-compose.yml
  docker compose up -d || die "compose up failed"

  health_check
  prune_old

  log "deployed ts=$ts ref=$ref commit=$(git -C "$REPO_DIR" log --oneline -1 | head -c 60)"
}

cmd_frontend() {
  local dist_pkg="${1:?usage: server.sh frontend <dist.tar.gz>}"
  swap_dist "$dist_pkg"
  log "frontend updated (no container restart needed)"
}

cmd_status() {
  echo "== container =="
  docker ps --filter name=yuansheng-astrbot --format '{{.Image}}  {{.Status}}'
  echo "== api =="
  echo "local:  $(curl -s -o /dev/null -w '%{http_code}' --max-time 5 http://127.0.0.1:6185/api/stat/versions)"
  echo "== repo =="
  git -C "$REPO_DIR" log --oneline -1 2>/dev/null || echo "repo missing"
  echo "== disk =="
  df -h / | tail -1
}

cmd_list() {
  echo "== deploy tags (git) =="
  git -C "$REPO_DIR" tag -l 'deploy/*' --sort=-creatordate | head -10
  echo "== backups =="
  ls -1t "$BACKUP_DIR" 2>/dev/null | head -10
  echo "== image tags =="
  docker images --format '{{.Tag}}  {{.CreatedSince}}' "$IMAGE_NAME" | head -8
}

cmd_rollback() {
  local ts="${1:?usage: server.sh rollback <ts> [--with-db] [YES]}"
  local with_db=0
  if [ "${2:-}" = "--with-db" ]; then
    with_db=1
  fi

  git -C "$REPO_DIR" fetch origin --tags --force --prune
  git -C "$REPO_DIR" rev-parse -q --verify "deploy/$ts" >/dev/null || die "tag deploy/$ts not found"

  if [ "$with_db" = "1" ]; then
    if [ "${3:-}" != "YES" ]; then
      die "rollback --with-db overwrites customer data; re-run with YES as 3rd arg (a safety snapshot will be taken first)"
    fi
    backup_db "pre-rollback-$(now_ts)"
    [ -f "$BACKUP_DIR/db-$ts.db" ] || die "db backup db-$ts.db not found"
    docker compose stop yuansheng-astrbot >/dev/null 2>&1 || true
    cp "$BACKUP_DIR/db-$ts.db" "$DATA_DIR/data_v4.db"
    rm -f "$DATA_DIR/data_v4.db-wal" "$DATA_DIR/data_v4.db-shm"
    log "db restored from db-$ts.db"
  fi

  if git -C "$REPO_DIR" rev-parse -q --verify "refs/tags/deploy/$ts" >/dev/null; then
    log "rebuild from deploy/$ts ..."
    sync_repo "deploy/$ts"
    docker build -t "$IMAGE_NAME:rollback" -t "$IMAGE_NAME:latest" "$REPO_DIR" || die "build failed"
  fi

  if [ -f "$BACKUP_DIR/dist-$ts.tar.gz" ]; then
    swap_dist "$BACKUP_DIR/dist-$ts.tar.gz"
  fi

  sed -i "s|image: $IMAGE_NAME:.*|image: $IMAGE_NAME:rollback|" docker-compose.yml
  docker compose up -d || die "compose up failed"
  health_check
  log "rolled back to deploy/$ts"
}

case "${1:-}" in
  deploy)   shift; cmd_deploy "$@" ;;
  frontend) shift; cmd_frontend "$@" ;;
  status)   cmd_status ;;
  list)     cmd_list ;;
  rollback) shift; cmd_rollback "$@" ;;
  *) sed -n '2,16p' "$0" ;;
esac
