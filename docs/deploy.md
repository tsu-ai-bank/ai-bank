# Деплой и эксплуатация

Прод — одна ВМ ТГУ (Ubuntu 24.04), проект в `/opt/aibank`, ветка `main`.
Стек поднимается через Docker Compose: `api`, `postgres`, `redis`, `nginx` (порт 80).

Все команды ниже выполняются на сервере из `/opt/aibank`.
Пользователь не в группе `docker`, поэтому через `sudo`.
Для краткости:

```sh
cd /opt/aibank
alias dc='sudo docker compose -f docker-compose.yml -f docker-compose.prod.yml'
```

## Как выкатывается релиз

1. PR в `develop` → CI (`build`, `test`).
2. PR `develop` → `main` (merge commit).
3. GitHub Actions собирает образ `ghcr.io/tsu-ai-bank/ai-bank-backend` с тегами `latest` и `<sha коммита>`.
4. На сервере `aibank-update.timer` раз в 5 минут запускает `deploy/update.sh`:
   `git pull` ветки `main` + `docker compose up -d` (подтягивает новый `latest`).

То есть через ~5–10 минут после мержа в `main` релиз сам на проде. Заходить на сервер не нужно.

Выкатить сразу, не дожидаясь таймера:

```sh
sudo systemctl start aibank-update.service
journalctl -u aibank-update.service -n 50 --no-pager
```

## Проверить, что всё живо

```sh
curl -s http://localhost/api/health
dc ps
```

Снаружи: `http://92.63.67.24/api/health` → `ok`.

## Логи

```sh
dc logs -f --tail 100 api            # приложение
dc logs --tail 100 nginx             # входящие запросы
journalctl -u aibank-update.service -n 50 --no-pager   # автообновление
journalctl -u aibank-backup.service -n 50 --no-pager   # бэкап
```

Логи контейнеров ротируются: 3 файла по 10 МБ на сервис.

## Откат на предыдущую версию

1. Остановить автообновление, иначе через 5 минут оно вернёт `latest`:

   ```sh
   sudo systemctl stop aibank-update.timer
   ```

2. Взять полный sha рабочего коммита в `main` (GitHub → Commits) и поднять его образ:

   ```sh
   sudo IMAGE_TAG=<полный sha> docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
   ```

3. Починить в коде, смержить фикс в `main`, вернуть автообновление:

   ```sh
   sudo systemctl start aibank-update.timer
   ```

## Бэкапы базы

- `aibank-backup.timer` каждую ночь в 03:00 (Томск) запускает `deploy/backup.sh`.
- Дампы (`pg_dump -Fc`) лежат в `/var/backups/aibank/`:
  `daily/` — последние 7, `weekly/` — 4 воскресных.
- Каждый дамп проверяется `pg_restore --list` перед сохранением.

Сделать бэкап прямо сейчас (например, перед миграцией):

```sh
sudo systemctl start aibank-backup.service
ls -lh /var/backups/aibank/daily/
```

### Восстановление

> ⚠️ Процедура ещё не проверена на реальных данных — проверим после появления моделей (#13).
> Восстановление **перезаписывает** текущую базу. Сначала сделай свежий бэкап.

```sh
dc stop api
dc exec -T postgres sh -c 'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists --no-owner' \
  < /var/backups/aibank/daily/<файл>.dump
dc start api
curl -s http://localhost/api/health
```

## Известные проблемы

### Сайт не открывается снаружи, а на сервере `curl localhost` работает

Скорее всего, применение правил фаервола на сервере стёрло правила Docker в цепочке `FORWARD`.
Признак: `sudo iptables -L FORWARD -n` — политика `DROP`, нет строк `DOCKER-USER` / `DOCKER-FORWARD`.

Решение — Docker пересоздаст свои правила:

```sh
sudo systemctl restart docker
```

Контейнеры поднимутся сами (`restart: unless-stopped`). После — проверить `/api/health` снаружи.

## Чего не делать

- Не ставить `ufw` и не трогать `iptables` — фаерволом управляют админы ТГУ.
- Не перезагружать сервер без согласования с админами.
- Не делать `do-release-upgrade`.
- Не коммитить `.env` — секреты только на сервере.