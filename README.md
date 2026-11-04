# ИИ-Банк индустриальных задач

Сервис для ИПМКН ТГУ. Собирает задачи от компаний Томской области (вакансии, новости, сайты МСП), прогоняет их через нейросеть и делает из подходящих учебные паспорта проектов. По этим паспортам потом работают студенты.

## Стек

Python (FastAPI, Celery), React, PostgreSQL, Redis, DeepSeek API. Всё запускается в Docker, деплой через GitHub Actions.

## Что где лежит

- `backend/` — API, парсеры, работа с нейросетью
- `frontend/` — сайт с каталогом задач и кабинет модератора
- `deploy/` — конфиги nginx и скрипты для сервера

### Структура бэкенда

Как и в [Ylab_EXTask](https://github.com/iiqq2/Ylab_EXTask), точка входа,
зависимости и тесты находятся рядом с каталогом исходного кода:

```text
backend/
├── Dockerfile
└── app/
    ├── main.py              # создание FastAPI и подключение API
    ├── requirements.txt     # зависимости приложения
    ├── src/
    │   ├── api/
    │   │   ├── router.py    # общий роутер с префиксом /api
    │   │   └── routers/     # обработчики эндпоинтов, включая health
    │   ├── core/            # настройки и общая инфраструктура
    │   ├── db/              # подключение к БД и миграции
    │   ├── models/          # модели БД
    │   ├── schemas/         # схемы Pydantic
    │   ├── services/        # бизнес-логика, в том числе save_raw_documents
    │   └── workers/         # фоновые задачи
    └── tests/               # каталог для тестов (задача #7)
```

Импорты внутри приложения начинаются с `src`, например
`from src.core.config import get_settings`. Команды локального запуска
выполняются из `backend/app`.

Парсеры из задачи #10 добавляются в `backend/app/parsers/`. Они вызывают
`save_raw_documents` из `src/services/`; модели и доступ к БД находятся
в `src/models/` и `src/db/` соответственно.

## Как работаем с git

- `main` — то, что крутится на сервере.
- `develop` — основная ветка, сюда сливаем готовые задачи.
- Под каждую задачу делаем свою ветку от `develop`, например `feature/hh-parser`, и открываем PR обратно в `develop`.

Напрямую запушить в `main` и `develop` нельзя, только через PR. PR сливается, когда прошли проверки и кто-то из команды посмотрел код.

Как сливать:

- feature → develop: кнопка **Squash and merge**. Все коммиты из ветки склеятся в один, история останется чистой.
- develop → main: только **Create a merge commit**. Если сделать squash, ветки разъедутся и в следующих PR полезут конфликты.

Перед началом новой задачи подтягиваем свежий develop:

    git switch develop
    git pull
    git switch -c feature/название-задачи

## Кто за что отвечает

- Бэкенд — код, модели и миграции БД, эндпоинт `/api/health`, список переменных в `.env.example`.
- Фронтенд — интерфейс каталога и кабинета модератора.
- Парсеры — сбор данных с сайтов.
- Техлид — Docker, CI/CD, сервер, бэкапы.

## Локальный запуск

Нужен Docker.

1. Скопировать `.env.example` в `.env` и заполнить.
2. Запустить `docker compose up --build`.
3. Открыть http://localhost:8080.

Проверка API:

```bash
curl http://localhost:8080/api/health
```

Ожидаемый ответ: `{"status":"ok"}`.

Compose передаёт переменные из корневого `.env` в контейнер API. Пока
внешние сервисы не подключены, API запускается и без этого файла.
Настройки описаны в `backend/app/src/core/config.py`, переменные
перечислены в `.env.example`.
Переменные читаются через `os.environ` и проверяются обычным Pydantic,
который устанавливается вместе с FastAPI. При локальном запуске `.env`
загружает Uvicorn через параметр `--env-file`.
Новые переменные добавляем туда же. Ключи и пароли храним только в `.env`.

### Без Docker, через uv

Из корня репозитория:

```bash
uv python install 3.12
uv venv --python 3.12 backend/.venv
uv pip install --python backend/.venv/bin/python -r backend/app/requirements.txt
source backend/.venv/bin/activate
cd backend/app
uvicorn main:app --reload --env-file ../../.env
```

Перед запуском скопируйте `.env.example` в `.env`. Для запуска с настройками
по умолчанию можно опустить `--env-file ../../.env`.
API доступен по адресу http://localhost:8000/api/health,
Swagger UI — http://localhost:8000/docs.

### Celery и Redis

Celery использует `REDIS_URL` из `.env` для очереди задач и хранения
результатов. Переменная уже есть в `.env.example`. Сервис Redis в основной
Compose добавляется отдельно в задаче #18. Для запуска команд ниже нужен
доступный Redis.

При запуске Python на компьютере, если Redis доступен на локальном порту
6379, задайте в своём `.env` значение `REDIS_URL=redis://localhost:6379/0`.
Значение `redis://redis:6379/0` из `.env.example` предназначено для
контейнеров в одной сети Compose с сервисом `redis`.

После установки зависимостей активируйте `backend/.venv` и перейдите в
`backend/app`, как описано выше. В каждом из терминалов загрузите `.env`:

```bash
set -a
source ../../.env
set +a
```

В первом терминале запустите воркер (параметр `--pool=solo` подходит для
локальной проверки, в том числе на macOS):

```bash
celery -A src.workers.celery_app:celery_app worker --loglevel=info --pool=solo
```

Во втором терминале отправьте задачу и дождитесь результата:

```bash
python -c 'from src.workers.tasks import ping; result = ping.delay(); print(result.id); print(result.get(timeout=15))'
```

Ожидаемый результат — `pong`. В логе воркера задача `workers.ping` должна
перейти в состояние `succeeded`.

В отдельном терминале можно запустить планировщик:

```bash
celery -A src.workers.celery_app:celery_app beat --loglevel=info
```

Заготовка расписания находится в `src/workers/schedule.py`: пока Beat
отправляет `workers.ping` раз в минуту. Здесь же будут добавляться задачи
парсеров. Воркер выполняет задачи, а Beat только ставит их в очередь;
запускайте один экземпляр Beat для этого расписания. Время расписания — UTC.
При запуске без `REDIS_URL` воркер и Beat завершаются с понятной ошибкой;
API при этом продолжает запускаться без Redis.

## Команда

- Шодиёрбек — техлид/девопс
- Владислав — бэкенд
- Юрий — бэкенд
- Вера — парсер
- Владислав 2 — парсер
- Владислав 2 — фронтенд
- ??? - фронтенд
