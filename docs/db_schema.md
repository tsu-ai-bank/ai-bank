# Схема базы данных

## Обозначения
 `PK` — первичный ключ, `FK` — внешний ключ, `UNIQUE` — уникальное значение, `NOT NULL` — обязательное поле, `NULL` — поле может отсутствовать.

## Таблицы

### `faculties` — факультеты

| Поле | Тип | Ограничения | Назначение |
|---|---|---|---|
| `id` | `BIGINT` | PK | Идентификатор факультета |
| `code` | `VARCHAR(64)` | UNIQUE, NOT NULL | Краткий код, например `IPMKN` |
| `name` | `VARCHAR(255)` | NOT NULL | Название факультета |

Факультет связан со своими компетенциями, модераторами и учебными паспортами. Привязка нужна для последующего подключения других факультетов.

### `sources` — источники

| Поле | Тип | Ограничения | Назначение |
|---|---|---|---|
| `id` | `BIGINT` | PK | Идентификатор источника |
| `domain` | `VARCHAR(255)` | UNIQUE, NOT NULL | Домен сайта |
| `name` | `VARCHAR(255)` | NULL | Название сайта |

Домен сохраняется в нижнем регистре, без протокола и пути. 

### `organizations` — организации

| Поле | Тип | Ограничения | Назначение |
|---|---|---|---|
| `id` | `BIGINT` | PK | Идентификатор организации |
| `name` | `VARCHAR(255)` | NOT NULL | Название организации |
| `normalized_name` | `VARCHAR(255)` | NOT NULL, INDEX | Название в нормализованном виде для поиска совпадений |
| `inn` | `VARCHAR(12)` | NULL, UNIQUE | ИНН, если он известен |

Одна организация может упоминаться в нескольких документах. `normalized_name` не уникален. Можно попробовать сопоставлять по ИНН при наличии у организации

### `raw_documents` — сырые документы

| Поле | Тип | Ограничения | Назначение |
|---|---|---|---|
| `id` | `BIGINT` | PK | Идентификатор документа |
| `source_id` | `BIGINT` | FK → `sources.id`, NOT NULL | Сайт, с которого получен текст |
| `organization_id` | `BIGINT` | FK → `organizations.id`, NULL | Организация, если удалось её определить |
| `url` | `TEXT` | UNIQUE, NOT NULL | Ссылка на исходную публикацию |
| `title` | `TEXT` | NOT NULL | Заголовок |
| `description` | `TEXT` | NULL | Краткое описание |
| `published_at` | `DATE` | NULL, INDEX | Дата публикации |
| `collected_at` | `TIMESTAMPTZ` | NOT NULL, DEFAULT `now()` | Дата и время сбора |
| `text` | `TEXT` | NOT NULL | Основной текст публикации |
| `status` | `VARCHAR(16)` | NOT NULL, DEFAULT `RAW` | Статус обработки |

Допустимые значения `status`:

| Статус | Значение |
|---|---|
| `RAW` | Документ сохранён, обработка ещё не проводилась |
| `REJECTED` | Документ отклонён |
| `CANDIDATE` | Найдена потенциальная задача для студентов |
| `GENERATED` | Сгенерирован учебный паспорт |
| `APPROVED` | Учебный проект прошёл проверку модератора |

`published_at` может отсутствовать. `collected_at` заполняется при сохранении документа. 

### `faculty_competencies` — компетенции факультетов

| Поле | Тип | Ограничения | Назначение |
|---|---|---|---|
| `id` | `BIGINT` | PK | Идентификатор компетенции |
| `faculty_id` | `BIGINT` | FK → `faculties.id`, NOT NULL | Факультет |
| `code` | `VARCHAR(64)` | NOT NULL | Код компетенции |
| `name` | `VARCHAR(255)` | NOT NULL | Название |
| `description` | `TEXT` | NULL | Описание |

Ограничение: `UNIQUE (faculty_id, code)`.

AI-модуль будет получать компетенции факультета из этой таблицы.

### `project_passports` — учебные паспорта

| Поле | Тип | Ограничения | Назначение |
|---|---|---|---|
| `id` | `BIGINT` | PK | Идентификатор паспорта |
| `raw_document_id` | `BIGINT` | FK → `raw_documents.id`, NOT NULL | Документ, по которому создан проект |
| `faculty_id` | `BIGINT` | FK → `faculties.id`, NOT NULL | Факультет |
| `title` | `TEXT` | NOT NULL | Название проекта |
| `recommended_course` | `SMALLINT` | NULL, значение от 1 до 4 | Рекомендуемый курс |
| `passport_data` | `JSONB` | NOT NULL | Содержание паспорта |
| `moderation_status` | `VARCHAR(16)` | NOT NULL, DEFAULT `PENDING` | Результат проверки паспорта |
| `moderated_by_id` | `BIGINT` | FK → `moderators.id`, NULL | Модератор, принявший решение |
| `moderated_at` | `TIMESTAMPTZ` | NULL | Дата решения |
| `created_at` | `TIMESTAMPTZ` | NOT NULL, DEFAULT `now()` | Дата создания |
| `updated_at` | `TIMESTAMPTZ` | NOT NULL, DEFAULT `now()` | Дата последнего изменения |

`passport_data` содержит семь частей учебного паспорта:

1. Бэклог на четыре спринта.
2. Роли участников команды.
3. Трудоёмкость в часах.
4. Рекомендуемый курс и обоснование.
5. Технологический стек: no-code и web-сценарии.
6. Бизнес-ценность.
7. Вопросы для Dev.


Предполагаемые значения `moderation_status`: `PENDING`, `APPROVED`, `REJECTED`. 

### `moderators` — модераторы

| Поле | Тип | Ограничения | Назначение |
|---|---|---|---|
| `id` | `BIGINT` | PK | Идентификатор модератора |
| `faculty_id` | `BIGINT` | FK → `faculties.id`, NOT NULL | Факультет |
| `login` | `VARCHAR(150)` | UNIQUE, NOT NULL | Логин |
| `password_hash` | `TEXT` | NOT NULL | Хэш пароля |
| `role` | `VARCHAR(32)` | NOT NULL | Роль пользователя |
| `is_active` | `BOOLEAN` | NOT NULL, DEFAULT `TRUE` | Активность учётной записи |
| `created_at` | `TIMESTAMPTZ` | NOT NULL, DEFAULT `now()` | Дата создания |

Авторизация выполняется в самом сервисе. В базе хранится только `password_hash` - то есть хэш-пароля, а не исходный пароль.

## Связи между таблицами

Для каждой связи указано минимальное и максимальное количество связанных записей с обеих сторон.

- `0..N` — запись может не иметь связанных записей либо иметь несколько.
- `1..1` — у записи должна быть ровно одна связанная запись.
- `0..1` — связанная запись может отсутствовать, но их не может быть больше одной.

Связи `1:N` реализуются внешним ключом в таблице на стороне `N`. Если связь обязательна для дочерней записи, внешний ключ имеет ограничение `NOT NULL`. Если связь необязательная, допускается `NULL`. Для связей `M:N` применяется промежуточная таблица с внешними ключами на обе связанные сущности.

###  Список связей
![ER-схема базы данных в нотации Баркера](db_schema.svg)

| Родительская таблица | Дочерняя таблица | Дочерних записей у одной родительской | Родительских записей у одной дочерней | Внешний ключ | Обязательность FK |
|---|---|---|---|---|---|
| `faculties` | `faculty_competencies` | `0..N` | `1..1` | `faculty_competencies.faculty_id` → `faculties.id` | `NOT NULL` |
| `faculties` | `moderators` | `0..N` | `1..1` | `moderators.faculty_id` → `faculties.id` | `NOT NULL` |
| `faculties` | `project_passports` | `0..N` | `1..1` | `project_passports.faculty_id` → `faculties.id` | `NOT NULL` |
| `sources` | `raw_documents` | `0..N` | `1..1` | `raw_documents.source_id` → `sources.id` | `NOT NULL` |
| `organizations` | `raw_documents` | `0..N` | `0..1` | `raw_documents.organization_id` → `organizations.id` | `NULL` разрешён |
| `raw_documents` | `project_passports` | `0..N` | `1..1` | `project_passports.raw_document_id` → `raw_documents.id` | `NOT NULL` |
| `moderators` | `project_passports` | `0..N` | `0..1` | `project_passports.moderated_by_id` → `moderators.id` | `NULL` разрешён |


### Связь факультетов с документами

Один документ может использоваться несколькими факультетами, и один факультет может создавать учебные паспорта по нескольким документам. На уровне предметной области это связь `M:N` между `faculties` и `raw_documents` **для тех пар, по которым создан паспорт**.

В схеме эта связь представлена таблицей `project_passports`:

- `project_passports.faculty_id` → `faculties.id`;
- `project_passports.raw_document_id` → `raw_documents.id`.

`project_passports` также хранит данные проекта, поэтому является самостоятельной сущностью, а не только таблицей для соединения двух ключей. Отдельную таблицу связи для этих же паспортов добавлять не нужно.

**ограничение:** `UNIQUE (raw_document_id, faculty_id)`, если для одной пары «документ — факультет» должен существовать только один актуальный паспорт. 

### Ограничения между связанными таблицами

1. `raw_documents.source_id`, `project_passports.raw_document_id`, `project_passports.faculty_id`, `faculty_competencies.faculty_id` и `moderators.faculty_id` не допускают `NULL`.
2. `raw_documents.organization_id` и `project_passports.moderated_by_id` допускают `NULL`.
3. `faculty_competencies` имеет уникальную пару `(faculty_id, code)`; одна и та же компетенция с одинаковым кодом не повторяется в пределах факультета.
4.Модератор проверяет паспорта только своего факультета или нескольких факультетов..

## Сохранение документов

Парсер передаёт название организации, URL, заголовок, описание, дату публикации, домен и текст. Backend проверяет URL, затем находит или создаёт источник и организацию и сохраняет новый документ со статусом `RAW`.

При повторном получении того же URL запись не добавляется. Функция `save_raw_documents()` должна возвращать количество сохранённых и пропущенных документов. 
