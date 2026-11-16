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
- Фронтенд — разработка интерфейса каталога и кабинета модератора.
- Дизайн — требования к интерфейсу и макеты (UI/UX).
- Парсеры — сбор данных с сайтов.
- Техлид/Девопс — Docker, CI/CD, сервер, бэкапы.

## Локальный запуск

Нужен Docker.

1. Скопировать `.env.example` в `.env` и заполнить.
2. Запустить `docker compose up --build`.
3. Открыть http://localhost:8080.

Проверка API:

```bash
curl http://localhost:8080/api/health
```

Ожидаемый ответ: `{"status":"ok"}`. В PowerShell вместо `curl` пишите
`curl.exe`: там `curl` — это псевдоним другой команды.

Файл `.env` обязателен: из него Postgres берёт логин и пароль. Postgres и
Redis поднимаются вместе с API, данные Postgres хранятся в томе
`postgres_data`. Порты базы и Redis наружу не публикуются, они доступны
только контейнерам. Адреса `postgres` и `redis` для контейнера API Compose
подставляет сам, поэтому в `.env` можно держать `localhost` для запуска без
Docker.

Compose передаёт переменные из корневого `.env` в контейнер API.
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
результатов. Переменная уже есть в `.env.example`. Сервис Redis есть в
основном Compose, но порт наружу он не публикует. Для запуска команд ниже
нужен Redis, доступный с вашего компьютера, например свой локальный.

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

### DeepSeek и учебный паспорт

Клиент находится в `backend/app/src/services/deepseek.py`, генерация и
проверка паспорта — в `src/services/passport_generation.py`. Ключ задаётся
только через `DEEPSEEK_API_KEY` в окружении или локальном `.env`.
Для скриптов загрузите `.env` в окружение, как описано для Celery выше.
Промпты находятся в `src/core/prompts.py`, общие константы — рядом,
в `src/core/constants.py`.

| Переменная | По умолчанию | Назначение |
|---|---|---|
| `DEEPSEEK_BASE_URL` | `https://api.deepseek.com` | Базовый адрес API |
| `DEEPSEEK_MODEL` | `deepseek-flash` | Модель генерации |
| `DEEPSEEK_TIMEOUT_SECONDS` | `30` | Таймаут сетевых операций HTTPX, в секундах |
| `DEEPSEEK_MAX_RETRIES` | `3` | Повторы после первого запроса, от 0 до 10 |
| `DEEPSEEK_REQUESTS_PER_MINUTE` | `30` | Частота начала запросов одного клиента |
| `DEEPSEEK_RETRY_BASE_SECONDS` | `1` | Начальная задержка повторов, в секундах |

Клиент использует Chat Completions и JSON Output по
[документации DeepSeek](https://api-docs.deepseek.com/guides/json_mode/).
HTTPX теперь входит в основные зависимости, поскольку используется и
клиентом API, и тестами. Дополнительный SDK не требуется.

Пример вызова внутри асинхронного кода:

```python
from src.schemas.passport_generation import PassportSource
from src.services.deepseek import DeepSeekClient
from src.services.passport_generation import PassportGenerator

# source заполняется исходным текстом документа и компетенциями
# его факультета из БД; компетенции не зашиты в промпт.
async def generate_passport(source: PassportSource):
    async with DeepSeekClient() as client:
        return await PassportGenerator(client).generate(source)
```

`PassportSource` содержит `document_id`, `faculty_id`, `text` и
`competencies`. Схема `ProjectPassport` требует все семь разделов:
`backlog` (четыре спринта), `roles`, `effort`, `course_routing` (курсы 1–4),
`stack` (no-code и web), `business_value`, `custdev_guide`.
Пустые обязательные поля, неверные типы и лишние поля отклоняются.

При успехе возвращается `PassportGenerationResult` со статусом `GENERATED`
и проверенным паспортом. Невалидный JSON, пустой или обрезанный ответ,
ошибки схемы и исчерпанные сетевые повторы дают результат `ERROR` с
описанием ошибки. Исходный документ и компетенции остаются в `result.source`;
его можно передать в `generate` повторно. `result.model_dump(mode="json")`
позволяет сериализовать результат для сохранения.

Это статус попытки генерации. Сервис не меняет `raw_documents.status` и
не удаляет документ. Модели и репозиторий БД ещё разрабатываются в задаче
#13; их вызывающий код должен сохранять результат и отметку ошибки.
`retryable` указывает на возможность повтора после временной ошибки или
невалидного ответа; ошибки авторизации и неверного запроса требуют
исправления настроек.

Сетевые ошибки, таймауты, HTTP 429 и 5xx повторяются с экспоненциальной
задержкой и учётом `Retry-After`. Остальные HTTP-ошибки не повторяются
автоматически. Лимит учитывает и повторные, и параллельные запросы.
Для серии генераций переиспользуйте один `DeepSeekClient`: лимит действует
на его экземпляр, общий лимит нескольких процессов здесь не реализован.

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
FastAPI TestClient для проверки маршрута `/api/health`: статус `200` и
JSON `{"status": "ok"}`. Тесты DeepSeek используют `httpx.MockTransport`
и искусственные часы: проверяют повторы, таймауты, ограничение частоты,
валидацию паспорта и повторную обработку документа. Настоящие запросы
к DeepSeek не выполняются. Для тестов не нужны ключ, `.env`, запущенный
API, PostgreSQL или Redis.

Ruff проверяет ошибки Python, стиль, порядок импортов и совместимость
с Python 3.12. Исправление поддерживаемых замечаний и форматирование:

```bash
ruff check . --fix
ruff format .
```

В рабочем Docker-образе устанавливается только `requirements.txt`.
`requirements-dev.txt` включает его и добавляет pytest и Ruff.

## Команда

- Шодиёрбек — техлид/девопс
- Владислав — бэкенд
- Юрий — бэкенд
- Вера — парсеры
- Владислав 2 — парсеры, фронтенд
- Анжелика — дизайн (UI/UX)
