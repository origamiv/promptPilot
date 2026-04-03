# AGENTS.md — PromptPilot

## Назначение
PromptPilot — локальный self-hosted планировщик задач для AI CLI:
- ставит промпты в очередь,
- запускает их по приоритету и расписанию,
- делает retry при rate limit,
- даёт интерфейсы управления через CLI, Web UI и Telegram-бот.

## Технологический стек
- Python `3.10+`
- CLI: `click`
- API/UI backend: `FastAPI` + `uvicorn`
- База данных: `PostgreSQL` через `psycopg` (schema/tables настраиваются env-переменными)
- Telegram: `python-telegram-bot`
- Desktop tray (Windows): `pystray` + `Pillow`
- Сборка standalone: `PyInstaller` (`pp.spec`, `build.ps1`)

## Поддерживаемые AI-провайдеры
Базовые провайдеры описаны в `promptpilot/config.py`:
- `claude`
- `claude-z`
- `codex`
- `qwen`
- `cursor`
- плюс пользовательские провайдеры из `providers.json`

Провайдер задаёт шаблон команды с плейсхолдером `{prompt}` и опциональные env-переменные.

## Точка входа и запуск
- Основной entrypoint CLI: `pp` -> `promptpilot.cli:cli`
- Модульный запуск: `python -m promptpilot`
- Для PyInstaller: `main.py`

Основные runtime-команды:
- `pp worker` — воркер очереди
- `pp server` — API + Web UI
- `pp bot` — Telegram-бот
- `pp tray` — системный трей (Windows)

## Структура проекта

### Корень репозитория
- `pyproject.toml` — зависимости, метаданные пакета, entrypoints
- `README.md` — пользовательская документация
- `AGENTS.md` — инструкции и карта проекта для агентной разработки
- `main.py` — entrypoint для сборки
- `pp.spec` — конфигурация PyInstaller
- `build.ps1` / `start.ps1` / `stop.ps1` — Windows-скрипты сборки и запуска

### Пакет `promptpilot/`
- `__main__.py` — запуск как Python-модуля
- `version.py` — версия и проверка обновлений
- `models.py` — Pydantic-модели (`TaskCreate`, `TaskInDB`, `Stats`, и т.д.)
- `config.py` — загрузка `.env`, провайдеры, env-конфигурация, discovery Claude skills
- `db.py` — PostgreSQL-слой, schema init, CRUD задач, статистика, служебные таблицы
- `worker.py` — цикл обработки очереди, запуск CLI-процессов, retry/backoff, parsing stream-json
- `api.py` — FastAPI-эндпоинты (tasks/stats/providers/skills/admin/...)
- `bot.py` — Telegram UX (авторизация, создание/просмотр/управление задачами)
- `tg_auth.py` — хранение/проверка Telegram-авторизации
- `tray.py` — tray-управление worker/server/bot
- `cli.py` — набор CLI-команд
- `static/index.html` — фронтенд Web UI

## Данные и конфигурация
- `.env` подхватывается в порядке:
  1. рядом с `pp.exe` (frozen-режим),
  2. текущая директория,
  3. `~/.promptpilot/.env`
- Ключевые env-переменные БД:
  - `PP_DB_DSN` или набор `PP_DB_HOST/PORT/DATABASE/USER/PASSWORD`
  - `PP_DB_SCHEMA` (по умолчанию `hubstaff`)
  - `PP_DB_TASKS_TABLE`, `PP_DB_SETTINGS_TABLE`
- Дополнительно используются:
  - `PP_DEFAULT_CLI`,
  - `PP_PROJECTS_ROOT`,
  - `PP_TASK_PASSWORD`,
  - `PP_HOST`, `PP_PORT`.

## Модель выполнения задач
- Статусы: `pending`, `running`, `completed`, `failed`, `rate_limited`, `cancelled`
- Выбор задачи: минимальный `priority`, затем ранний `created_at`
- При rate limit: exponential backoff с jitter (`BASE_DELAY` -> `MAX_DELAY`)
- Crash recovery: зависшие `running`-задачи можно вернуть в очередь reset-механикой
- Для Claude stream-json извлекаются: текст, метаданные модели, токены, cost, session id

## API-группы (ориентир)
- `/api/tasks*` — CRUD/управление задачами
- `/api/stats*` — общая и cost-статистика
- `/api/worker/*` — пауза/возобновление воркера
- `/api/providers`, `/api/skills`, `/api/projects`
- `/api/admin/*` — админ-CRUD для проектов, агентов, аккаунтов агентов, промптов

## Правила для агентной работы в этом репозитории
- Перед правками проверяй текущий `git status`: рабочее дерево может быть уже изменено.
- Не откатывай чужие изменения без явной команды.
- При изменениях в `db.py` синхронно проверяй влияние на `api.py`, `worker.py`, `bot.py`, `models.py`.
- При изменении формата задачи/статусов обязательно проверяй:
  - CLI-вывод,
  - API response-model,
  - Web UI (`static/index.html`),
  - Telegram-сценарии (`bot.py`).
- Для новых интеграций провайдеров достаточно добавить запись в провайдер-словарь или `providers.json` с корректным `{prompt}`.
