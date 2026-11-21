#!/bin/sh
# автообновление: подтягивает конфиги из main и обновляет контейнеры
# запускает systemd-таймером aibank-update.timer
set -eu

cd /opt/aibank
git pull --ff-only origin main

docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --remove-orphans
docker image prune -f