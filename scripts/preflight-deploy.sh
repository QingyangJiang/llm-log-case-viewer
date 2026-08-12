#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

command -v docker >/dev/null 2>&1 || { echo "错误：未找到 docker" >&2; exit 1; }
docker compose version >/dev/null 2>&1 || { echo "错误：需要 Docker Compose v2" >&2; exit 1; }
test -f .env || { echo "错误：请先执行 cp .env.example .env 并修改密码" >&2; exit 1; }

set -a
# shellcheck disable=SC1091
. ./.env
set +a

if [[ -z "${POSTGRES_PASSWORD:-}" || "$POSTGRES_PASSWORD" == change-this-* ]]; then
  echo "错误：请在 .env 中设置强 POSTGRES_PASSWORD" >&2
  exit 1
fi
if [[ -z "${ADMIN_PASSWORD:-}" || "$ADMIN_PASSWORD" == change-this-* || ${#ADMIN_PASSWORD} -lt 8 ]]; then
  echo "错误：请在 .env 中设置至少 8 位的 ADMIN_PASSWORD" >&2
  exit 1
fi
if ! [[ "${APP_PORT:-8080}" =~ ^[0-9]+$ ]] || (( APP_PORT < 1 || APP_PORT > 65535 )); then
  echo "错误：APP_PORT 必须是 1–65535 的整数" >&2
  exit 1
fi

mkdir -p data/postgres data/app/uploads data/app/exports
docker compose config --quiet

echo "预检通过。启动后访问：http://<服务器内网IP>:${APP_PORT:-8080}"
