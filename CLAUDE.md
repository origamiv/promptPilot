# PromptPilot — описание проекта

## Что это
PromptPilot — локальный планировщик задач для AI CLI.
Он ставит промпты в очередь, запускает их по расписанию, автоматически повторяет при rate limit и управляется через:
- CLI (`pp ...`)
- Web UI (FastAPI)
- Telegram-бот
- Tray-приложение (для Windows/`pp.exe`)

Проект поддерживает несколько провайдеров: `claude`, `codex`, `qwen`, `cursor` и пользовательские команды через `providers.json`.

## Технологии
- Python 3.10+
- FastAPI + Uvicorn
- SQLite (WAL)
- Click (CLI)
- python-telegram-bot
- pystray + Pillow (tray)

## Основные модули
- `promptpilot/cli.py` — CLI-команды (`add`, `list`, `worker`, `server`, `bot`, `tray`, `provider`)
- `promptpilot/worker.py` — выполнение задач из очереди, retry/backoff, обработка stream-json
- `promptpilot/api.py` — HTTP API и раздача фронтенда (`promptpilot/static/index.html`)
- `promptpilot/bot.py` — Telegram-бот (авторизация по телефону, управление задачами)
- `promptpilot/db.py` — слой SQLite, схема, миграции, CRUD и статистика
- `promptpilot/config.py` — загрузка `.env`, провайдеры, пути, runtime-настройки
- `promptpilot/tray.py` — системный трей и запуск сервисов

## Как запускается
- CLI: `pp <command>`
- Модульно: `python -m promptpilot`
- PyInstaller entrypoint: `main.py`

Частые команды:
- `pp worker` — обработчик очереди
- `pp server` — Web UI/API (по умолчанию `127.0.0.1:8420`)
- `pp bot` — Telegram-бот
- `pp add "..."` — добавить задачу

## Хранение данных и конфигов
- БД: `~/.promptpilot/promptpilot.db` (или `PP_DATA_DIR`)
- Пользовательские провайдеры: `~/.promptpilot/providers.json`
- `.env` ищется в порядке:
  1. рядом с `pp.exe` (если frozen)
  2. текущая директория
  3. `~/.promptpilot/.env`

## Поведение очереди (кратко)
- Статусы задач: `pending`, `running`, `completed`, `failed`, `rate_limited`, `cancelled`
- Выбор следующей задачи: по приоритету (1 выше 10) и времени создания
- При rate limit: exponential backoff с jitter до `MAX_DELAY`
- При перезапуске воркера возможен recovery «зависших» задач через reset-механики

## Назначение репозитория
Этот репозиторий содержит полный код PromptPilot (ядро, API, UI, бот, сборка `pp.exe`) для локального self-hosted использования как универсальной очереди промптов для AI CLI.
