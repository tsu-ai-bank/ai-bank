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
    ├── requirements-dev.txt # зависимости приложения и инструменты разработки
    ├── pyproject.toml       # настройки pytest и Ruff
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
    └── tests/               # фикстуры и тесты API
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

### Тесты и линтер

Установите зависимости разработки в созданное окружение. Из корня
репозитория:

```bash
uv pip install --python backend/.venv/bin/python -r backend/app/requirements-dev.txt
source backend/.venv/bin/activate
cd backend/app
```

Запуск тестов и проверок кода:

```bash
pytest
ruff check .
ruff format --check .
```

Настройки находятся в `backend/app/pyproject.toml`. Тесты используют
FastAPI TestClient и проверяют реальный маршрут `/api/health`: статус
`200` и JSON `{"status": "ok"}`. Для них не нужны `.env`, запущенный API,
PostgreSQL или Redis.

Ruff проверяет ошибки Python, стиль, порядок импортов и совместимость
с Python 3.12. Исправление поддерживаемых замечаний и форматирование:

```bash
ruff check . --fix
ruff format .
```

В рабочем Docker-образе устанавливается только `requirements.txt`.
`requirements-dev.txt` включает его и добавляет pytest, Ruff и HTTPX.

## Команда

- Шодиёрбек — техлид/девопс
- Владислав — бэкенд
- Юрий — бэкенд
- Вера — парсер
- Владислав 2 — парсер
- Владислав 2 — фронтенд
- ??? - фронтенд
