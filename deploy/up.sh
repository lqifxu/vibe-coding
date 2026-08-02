#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ ! -f deploy/.env ]]; then
  echo "缺少 deploy/.env，请先: cp deploy/.env.example deploy/.env 并填写"
  exit 1
fi

# shellcheck disable=SC1091
set -a
# strip Windows CRLF if any
source <(sed 's/\r$//' deploy/.env | grep -v '^\s*#' | grep -v '^\s*$')
set +a

mkdir -p deploy/data deploy/temp
export VITE_SITE_URL="${VITE_SITE_URL:-${PUBLIC_APP_URL:-http://localhost}}"
export HTTP_PORT="${HTTP_PORT:-80}"

echo "Building with VITE_SITE_URL=$VITE_SITE_URL HTTP_PORT=$HTTP_PORT"
docker compose --env-file deploy/.env up -d --build
docker compose ps
echo "Health: $(curl -fsS "http://127.0.0.1:${HTTP_PORT}/api/health" || echo failed)"
