#!/bin/sh
# deploy-хук certbot: после продления сертификата nginx перечитывает его
# ставится симлинком в /etc/letsencrypt/renewal-hooks/deploy/, см. docs/deploy.md
set -eu

cd /opt/aibank
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec -T nginx nginx -s reload
