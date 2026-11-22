#!/bin/sh
# бэкап Postgres: pg_dump из контейнера в BACKUP_DIR
# хранит 7 ежедневных и 4 еженедельных (воскресных) копии
# запускает systemd-таймер aibank-backup.timer
set -eu

BACKUP_DIR=/var/backups/aibank
KEEP_DAILY=7
KEEP_WEEKLY=4

umask 077

cd /opt/aibank
compose() {
    docker compose -f docker-compose.yml -f docker-compose.prod.yml "$@"
}

mkdir -p "$BACKUP_DIR/daily" "$BACKUP_DIR/weekly"

file="$BACKUP_DIR/daily/aibank_$(date +%Y-%m-%d_%H%M).dump"
tmp="$file.tmp"
trap 'rm -f "$tmp"' EXIT

compose exec -T postgres sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "$tmp"
compose exec -T postgres pg_restore --list < "$tmp" > /dev/null

mv "$tmp" "$file"
echo "бэкап готов: $file ($(du -h "$file" | cut -f1))"

if [ "$(date +%u)" = 7 ]; then
    ln -f "$file" "$BACKUP_DIR/weekly/"
fi

prune() {
    ls -1t "$1"/*.dump 2>/dev/null | tail -n +"$(($2 + 1))" | xargs -r rm -f --
}
prune "$BACKUP_DIR/daily" "$KEEP_DAILY"
prune "$BACKUP_DIR/weekly" "$KEEP_WEEKLY"