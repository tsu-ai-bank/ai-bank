#!/bin/sh
# автообновление: подтягивает конфиги из main и обновляет контейнеры
# запускает systemd-таймером aibank-update.timer
set -eu

cd /opt/aibank
compose() {
    docker compose -f docker-compose.yml -f docker-compose.prod.yml "$@"
}

before=$(git rev-parse HEAD)
git pull --ff-only origin main

compose up -d --remove-orphans

# nginx читает конфиг только при старте — перечитать, если он поменялся
if ! git diff --quiet "$before" HEAD -- deploy/nginx; then
    compose exec -T nginx nginx -s reload
fi

docker image prune -f
