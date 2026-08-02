#!/usr/bin/env bash
# Dumps the production Postgres database to a timestamped, gzipped file.
# Intended to run from a cron job on the VM (see DEPLOYMENT.md) — not
# inside a container, so it works even if you later move the DB off-box.
#
# Usage: ./backup-db.sh [backup_directory]
set -euo pipefail

BACKUP_DIR="${1:-/root/banking-backups}"
TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
COMPOSE_FILE="$(dirname "$0")/docker-compose.prod.yml"

mkdir -p "$BACKUP_DIR"

# shellcheck disable=SC1091
set -a; source "$(dirname "$0")/.env"; set +a

docker compose -f "$COMPOSE_FILE" exec -T db \
  pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" \
  | gzip > "$BACKUP_DIR/banking-db-${TIMESTAMP}.sql.gz"

echo "Backup written to $BACKUP_DIR/banking-db-${TIMESTAMP}.sql.gz"

# Keep the last 14 days of backups, delete anything older.
find "$BACKUP_DIR" -name "banking-db-*.sql.gz" -mtime +14 -delete
