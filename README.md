# PromptPilot

> **Background task queue for AI CLIs** — schedule prompts, retry on rate limits, manage everything via Web UI or Telegram bot.
>
> Works with Claude Code, OpenAI Codex, Qwen Code, Cursor Agent, or any CLI that accepts a prompt argument.

---

Универсальный планировщик промптов для AI CLI — очередь, планирование и автоматический retry.

Работает с **любым** AI CLI: Claude Code, Codex, Qwen Code и другими.

## Скриншоты

> Интерфейс — dark-theme, работает на десктопе и мобильном.

### Список задач

![Список задач](docs/screenshots/tasks.png)

### Канбан-доска

![Канбан-доска](docs/screenshots/kanban.png)

### Исполнители

![Исполнители](docs/screenshots/workers.png)

### Справочник приоритетов

![Приоритеты](docs/screenshots/priorities.png)

### Интерактивный терминал

![Интерактив](docs/screenshots/interactive.png)

---

## Возможности

### Очередь задач и планирование

- **Мульти-провайдер** — Claude, Codex, Qwen, Cursor Agent, или любой свой CLI
- **Очередь задач** с приоритетами (1 — высший, 10 — низший); приоритеты из справочника с иконками (Jira-style)
- **Планирование** — запуск промптов в заданное время
- **Выбор модели** — для Claude Code провайдеров: sonnet / opus / haiku (Web UI + бот)
- **Rate limit detection** — автоматическое определение лимитов API
- **Exponential backoff** — retry с нарастающей задержкой (60s → 1h)
- **Crash recovery** — при перезапуске воркера зависшие задачи возвращаются в очередь
- **Повторяющиеся задачи** — поле Recur: `6h`, `30m`, `daily@09:00` — новая задача создаётся автоматически

### Веб-интерфейс

- **Список задач** — фильтры по статусу, раскрытие деталей, аватары исполнителей, иконки приоритетов
- **Канбан-доска** — per-project доска с настраиваемыми статусами, автообновление каждые 15 сек, пагинация (15 карточек + «Ещё»), URL `/kanban/<project>`
- **Интерактивный терминал** — запуск AI CLI прямо в браузере (через tmux + pyte), поддержка клавиш управления
- **Дашборд стоимости** — затраты за сегодня / неделю / всего по провайдерам
- **History API** — URL-адресация (`/tasks`, `/kanban`, `/workers`, `/priorities`) без hash-маршрутизации
- **⚡ Skills** — раскрывает список скилов Claude Code
- **Пауза воркера** — кнопка ⏸ для временной остановки без потери задач
- **Уведомления об обновлениях** — баннер когда выходит новая версия
- **Ctrl+Enter** — быстрая отправка задачи из формы

### Справочники

- **Статусы задач** — настраиваемые статусы с цветом, порядком отображения в Канбане; статус «Готово» с крон-переносом завершённых задач (через N дней)
- **Приоритеты** — справочник с иконками (SVG, Jira-style), отображаются в карточках задач и канбане
- **Исполнители (Workers)** — таблица исполнителей с аватарами, ролями; привязка исполнителя к задаче; CRUD
- **Промпты** — библиотека шаблонных промптов с быстрым выбором при создании задачи

### Мультиагентная система

- **Агенты** — специализированные AI-агенты: PM, Architect, Backend, Frontend, Mobile, Database, UX, QA, Reviewer, DevOps, Integrations
- **Учётные записи агентов** — управление несколькими аккаунтами на агента, relogin-процедура прямо из Web UI
- **Проекты с цветами** — проекты с уникальными цветами и shortname; агент-цвет в карточках Канбана
- **Иерархия задач** — дочерние задачи через `parent_task_id`; PM-агент создаёт подзадачи для каждого исполнителя

### Telegram бот

- **Список задач** с пагинацией и статусами
- **Создание задачи** через диалог: промпт → провайдер → модель → приоритет → skip-permissions → директория → расписание
- **Продолжение сессии** (💬 Ответить) — диалог с моделью в той же сессии
- **⚡ Скилы** — список и запуск Claude Code скилов
- **Уведомления** — результат или ошибка автоматически после завершения задачи
- **Авторизация по номеру телефона**
- **Пароль на создание задач** (`PP_TASK_PASSWORD`)

### Инфраструктура

- **PostgreSQL** — хранение данных; схема и имена таблиц настраиваются через env
- **CLI + Web UI + Telegram бот** — три интерфейса на выбор
- **Tray-приложение** — двойной клик на `pp.exe`, иконка в трее
- **Standalone .exe** — сборка без зависимостей через PyInstaller

## Установка

### Вариант 1 — Скачать готовый .exe (Windows)

1. Скачай последний релиз: [github.com/ivanarama/PromptPilot/releases](https://github.com/ivanarama/PromptPilot/releases)
2. Распакуй архив `PromptPilot-vX.X.X-windows.zip` в любую папку
3. Заполни `.env` (шаблон уже в архиве)
4. Запусти `start.ps1` или `pp.exe tray`

### Вариант 2 — Из исходников (Python 3.10+)

```bash
git clone https://github.com/ivanarama/PromptPilot.git
cd PromptPilot
pip install -e .
```

Или установка из pip-пакета (из релиза):

```bash
pip install promptpilot-X.X.X-py3-none-any.whl
```

Требования: Python 3.10+, PostgreSQL, хотя бы один AI CLI в PATH (claude, codex, qwen и т.д.).

## Быстрый старт

```bash
# Добавить задачу
pp add "Объясни что такое рекурсия"

# Запустить воркер (выполняет задачи)
pp worker

# В другом терминале — запустить веб-интерфейс
pp server
# Откроется на http://127.0.0.1:8420
```

## Запуск: два режима

### Режим 1 — Tray (рекомендуется для .exe)

Двойной клик на `pp.exe` — иконка появляется в системном трее, worker и server стартуют автоматически.

Правый клик на иконке:

```
▶ Worker          ← кликнуть = остановить
▶ Server          ← кликнуть = остановить
■ Bot             ← кликнуть = запустить (нужен PP_TG_TOKEN в .env)
─────────────────
Запустить все
Остановить все
─────────────────
Открыть Web UI    ← открывает браузер на http://127.0.0.1:8420
─────────────────
Выход             ← останавливает все сервисы и закрывает трей
```

Цвет иконки показывает состояние: 🟢 все работают / 🟠 частично / ⚫ остановлено.

Или явно через команду:

```powershell
pp tray
```

### Режим 2 — CLI (все команды работают)

```powershell
pp worker          # запустить воркер
pp server          # запустить веб-UI
pp bot             # запустить Telegram бот
pp add "промпт"    # добавить задачу
pp list            # список задач
# и т.д.
```

Оба режима работают с одной и той же БД и настройками.

## Файл .env (настройки)

Все настройки — токен бота, путь к `claude.exe`, разрешённые номера — хранятся в `.env` файле.

Скопируй шаблон и заполни:

```powershell
copy .env.example .env
notepad .env
```

`.env` рядом с `pp.exe` (или рядом со скриптом):

```ini
# База данных (PostgreSQL)
PP_DB_DSN=postgresql://user:password@localhost:5432/dbname
# или по частям:
PP_DB_HOST=localhost
PP_DB_PORT=5432
PP_DB_DATABASE=promptpilot
PP_DB_USER=pp
PP_DB_PASSWORD=secret
PP_DB_SCHEMA=hubstaff

# Telegram бот
PP_TG_TOKEN=7123456789:AAF...
PP_TG_ALLOWED_PHONES=+79001234567,+79007654321

# AI CLI
PP_CLAUDE_EXE=C:\Users\YourName\.local\bin\claude.exe
PP_DEFAULT_CLI=claude
```

> **Авторизация Claude:** PromptPilot запускает `claude.exe` как обычный процесс — он наследует окружение текущего пользователя. Достаточно один раз выполнить `claude auth login` на этой машине, больше ничего настраивать не нужно.

Порядок поиска `.env`:
1. Рядом с `pp.exe` — для дистрибуции
2. Текущая рабочая директория — для разработки
3. `~/.promptpilot/.env` — постоянный пользовательский конфиг

Значения из `.env` применяются только если переменная **не задана** в окружении — то есть `$env:PP_TG_TOKEN` всегда перекрывает `.env`.

## PowerShell: запуск одной командой

Запустить воркер + сервер в фоне:

```powershell
.\start.ps1
```

Запустить всё включая Telegram бота:

```powershell
$env:PP_TG_TOKEN = "ваш-токен"
$env:PP_TG_ALLOWED_PHONES = "+79001234567"
.\start.ps1 -Bot
```

Логи пишутся в `.\logs\`. Остановить:

```powershell
.\stop.ps1
```

Скрипт автоматически использует `dist\pp.exe` если он собран, иначе `pp` из PATH.

## Сборка .exe

Сборка standalone-бинаря (не требует Python на целевой машине):

```powershell
.\build.ps1
```

На выходе: `dist\pp.exe`. Использование аналогично:

```powershell
.\dist\pp.exe worker
.\dist\pp.exe server
.\dist\pp.exe bot
.\dist\pp.exe add "промпт"
```

> **Примечание:** при первом запуске `pp.exe` может занять несколько секунд — PyInstaller распаковывает бандл во временную папку.

## CLI

```
pp add "промпт"                        # добавить задачу (дефолтный провайдер)
pp add "промпт" -c codex               # через Codex
pp add "промпт" -c qwen                # через Qwen
pp add "промпт" -c claude-z            # через кастомный алиас
pp add "промпт" -p 1                   # с приоритетом (1 = высший)
pp add "промпт" -a "2026-03-25T03:00"  # запланировать на время
pp add -f prompts.txt                  # добавить из файла (по строке)
pp add "промпт" -d /path/to/project    # задать рабочую директорию

pp list                                # все задачи
pp list -s pending                     # фильтр по статусу
pp status 1                            # детали задачи #1
pp cancel 1                            # отменить задачу
pp delete 1                            # удалить задачу
pp stats                               # статистика
pp purge --days 7                      # удалить старые завершённые задачи

pp worker                              # запустить воркер
pp server                              # запустить веб-UI
pp server -p 9000                      # на другом порту
pp bot                                 # запустить Telegram бот
pp poll-limits-all                     # опросить лимиты всех аккаунтов
```

## Telegram бот

### Настройка

1. Создай бота через [@BotFather](https://t.me/BotFather), получи токен.
2. Задай переменные окружения:

```powershell
$env:PP_TG_TOKEN = "токен-от-botfather"
$env:PP_TG_ALLOWED_PHONES = "+79001234567,+79007654321"
```

3. Запусти:

```powershell
pp bot
```

### Авторизация

При первом открытии бота пользователь видит кнопку **«Поделиться контактом»**. Бот получает номер телефона и сверяет с `PP_TG_ALLOWED_PHONES`. При совпадении — доступ открыт.

Авторизованные пользователи сохраняются в `~/.promptpilot/tg_users.json`. Повторная авторизация при перезапуске не нужна.

Альтернатива env-переменной — файл `~/.promptpilot/tg_config.json`:

```json
{
  "allowed_phones": ["+79001234567", "+79007654321"]
}
```

### Возможности бота

| Функция | Описание |
|---------|----------|
| 📋 Задачи | Список задач с пагинацией и статусами |
| ➕ Добавить задачу | Промпт → провайдер → **модель** → приоритет → skip-permissions → директория → расписание |
| 📊 Статистика | Сводка по статусам |
| 🔌 Провайдеры | Список доступных провайдеров |
| Детали задачи | Промпт, результат, ошибка, кнопки отмены / удаления / сброса |
| 💬 Ответить | Продолжить диалог с моделью в той же сессии |
| ⚡ Скилы (`/skills`) | Список Claude Code скилов; выбор запускает пошаговое создание задачи |
| 🔔 Уведомления | Автоматически присылает результат или ошибку после завершения задачи |

### Продолжение сессии (💬 Ответить)

После завершения задачи в деталях появляется кнопка **💬 Ответить** — если модель спросила что-то или ты хочешь продолжить диалог:

1. Открой детали завершённой задачи → нажми **💬 Ответить**
2. Введи ответ или следующий вопрос
3. Бот создаст новую задачу с флагом `--resume <session_id>` — Claude продолжит разговор в том же контексте

Цепочка не ограничена: каждый «ответ» тоже получает кнопку 💬. Новая задача наследует провайдера, рабочую директорию и флаги оригинальной.

### Защита паролем (PP_TASK_PASSWORD)

Если задана переменная `PP_TASK_PASSWORD`, бот запрашивает пароль перед созданием задачи. При неверном вводе создание отменяется; введённое сообщение автоматически удаляется из чата.

```ini
PP_TASK_PASSWORD=mysecretpassword
```

Просмотр задач и статистика паролем не защищены — только создание.

## Провайдеры

Встроенные провайдеры:

| Имя | Описание | Скилы | Выбор модели |
|-----|----------|-------|--------------|
| `claude` | Claude Code (Anthropic) — дефолт | ✅ | ✅ sonnet / opus / haiku |
| `claude-z` | Claude Code с альтернативным API (GLM, z.ai и др.) | ✅ | ✅ sonnet / opus / haiku |
| `codex` | OpenAI Codex | — | — |
| `qwen` | Qwen Code | — | — |
| `cursor` | Cursor Agent | — | — |

> Любой провайдер с `supports_skills=True` считается Claude Code-совместимым и получает выбор модели автоматически.

Команды управления:

```bash
pp provider                   # список всех
pp provider add <name> ...    # добавить
pp provider remove <name>     # удалить
```

Кастомные провайдеры сохраняются в `~/.promptpilot/providers.json`.

Дефолтный провайдер: переменная `PP_DEFAULT_CLI` (по умолчанию `claude`).

Путь к `claude.exe` по умолчанию: `~/.local/bin/claude.exe`. Переопределяется через `PP_CLAUDE_EXE`.

### Добавление кастомного провайдера

```bash
pp provider add myai \
  --cmd "myai run {prompt}" \
  --desc "My AI Tool"
```

С переменными окружения и поддержкой скилов:

```powershell
pp provider add claude-z `
  --cmd "C:\Users\<username>\.local\bin\claude.exe -p --verbose --output-format stream-json {prompt}" `
  --desc "Claude Code (GLM via z.ai)" `
  --env "ANTHROPIC_BASE_URL=https://api.z.ai/api/anthropic" `
  --env "ANTHROPIC_AUTH_TOKEN=your-token-here" `
  --env "ANTHROPIC_DEFAULT_SONNET_MODEL=glm-4.7" `
  --env "ANTHROPIC_DEFAULT_OPUS_MODEL=glm-4.7"
```

> **Windows:** `subprocess` не видит PowerShell-функции и алиасы — нужен полный путь к исполняемому файлу. `.cmd`/`.bat`-обёртки (npm-инструменты вроде `qwen`, `codex`) находятся автоматически через `shutil.which`.

### Настройка Cursor Agent

```powershell
npm install -g @nothumanwork/cursor-agents-sdk
winget install BurntSushi.ripgrep.MSVC
```

Добавь в `.env`:
```
CURSOR_API_KEY=crsr_your_key_here
```

Ключ: **cursor.com/settings** → **API Keys**. Первый запуск занимает ~60 секунд.

## Скилы Claude Code

Скилы — команды (`/skill-name`) из `~/.claude/commands/`, `~/.claude/skills/` и плагинов Claude Code. Доступны для всех провайдеров с `supports_skills=True`.

### Web UI

При выборе Claude-провайдера под полем промпта появляется кнопка **⚡ Skills**. Нажми — откроется список скилов с описаниями. Выбор подставляет `/skill-name ` в промпт.

### Telegram бот

Кнопка **⚡ Скилы** в главном меню или команда `/skills`. Поддерживает глобальные скилы и скилы конкретного проекта (`📁 Скилы проекта...`).

### REST API

```
GET /api/skills                                — все доступные скилы
GET /api/skills?provider=claude                — только если провайдер поддерживает скилы
GET /api/skills?provider=claude&workdir=/path  — + локальные скилы проекта
```

## Канбан-доска

Полноценный Канбан для отслеживания задач по проектам.

- Выбор проекта → переход на `/kanban/<shortname>` — прямая ссылка на доску
- Колонки = настраиваемые статусы задач (справочник **Статусы задач**)
- Порядок колонок задаётся полем `nom` в справочнике
- Пагинация: 15 карточек на колонку + кнопка «Ещё N»
- Автообновление каждые 15 секунд (инкрементальное, без мерцания)
- На карточках: аватар исполнителя, иконка приоритета, бейджи
- Кнопка «+» над доской — быстрое добавление задачи

```
GET  /api/admin/tasks-statuses          — список статусов для Канбана
POST /api/admin/tasks-statuses          — создать статус
```

## Исполнители (Workers)

Справочник исполнителей — реальных людей или AI-агентов, которым назначаются задачи.

- Аватары (изображения из `static/images/workers/`)
- Роль исполнителя
- Привязка к задаче через поле `worker_id`
- Аватар исполнителя отображается в списке задач и на карточках Канбана
- CRUD через Web UI (раздел «Исполнители»)

## Мультиагентная система

PromptPilot используется как планировщик в мультиагентной системе разработки. Подробная документация в [`docs/README.md`](docs/README.md).

### Агенты

| Агент | Описание |
|-------|----------|
| PM / Orchestrator | Декомпозиция задач, координация агентов |
| Architect | Системный дизайн, API-контракты |
| Backend | Laravel / PHP |
| Frontend | Vue.js |
| Mobile | React Native |
| Database | PostgreSQL, миграции |
| UX Designer | Figma макеты |
| QA | Тесты, тест-планы |
| Reviewer | Code review |
| DevOps | Docker, CI/CD |
| Integrations | Python/Node.js воркеры |

### Учётные записи агентов

У каждого агента может быть несколько учётных записей (claude-аккаунтов). Управление через Web UI (раздел «Учётные записи»):
- CRUD аккаунтов
- Процедура relogin прямо в браузере (через интерактивный терминал)
- Опрос rate limits: `pp poll-limits-all`

### Иерархия задач

- PM-агент получает высокоуровневую задачу
- Создаёт дочерние задачи (`parent_task_id`) для каждого нужного агента
- Статус фичи отслеживается через список дочерних задач

## Интерактивный терминал

Запуск AI CLI прямо в браузере без SSH.

- Требует **tmux** на сервере
- Рендеринг через **pyte** (VT100-эмулятор)
- Поддержка клавиш: Enter, Ctrl+C, Escape, стрелки, Tab
- Панель быстрых клавиш над терминалом
- Автоматическое сворачивание формы при старте

```
GET  /api/interactive/state   — текущее состояние сессии
POST /api/interactive/start   — запустить сессию (provider, workdir)
POST /api/interactive/input   — отправить ввод
GET  /api/interactive/output  — получить вывод (cursor-based polling)
POST /api/interactive/stop    — завершить сессию
```

## Статус «Готово» и крон-перенос

- Статус «Готово» (`shortname: ready`) — архивный статус, не отображается в Канбане
- Крон-задача автоматически переносит задачи из статуса «Успешно завершена» в «Готово» через N дней (по умолчанию 7)
- Запускается в фоне при старте сервера

## Веб-интерфейс

Минималистичный dark-theme UI на `http://127.0.0.1:8420`.

### Разделы меню

| Раздел | Путь | Описание |
|--------|------|----------|
| Задачи | `/tasks` | Список задач с фильтрами и деталями |
| Канбан | `/kanban` | Выбор проекта → Канбан-доска |
| Интерактив | `/interactive` | Интерактивный терминал |
| Агенты | `/agents` | Управление агентами |
| Учётные записи | `/accounts` | Аккаунты агентов, relogin |
| Проекты | `/projects` | Список проектов |
| Статусы задач | `/task-statuses` | Справочник статусов для Канбана |
| Приоритеты | `/priorities` | Справочник приоритетов с иконками |
| Промпты | `/prompts` | Библиотека шаблонных промптов |
| Исполнители | `/workers` | Управление исполнителями |

### Форма добавления задачи

- Выбор провайдера и модели (дропдаун модели — автоматически для Claude Code)
- Выбор приоритета из справочника (с иконкой)
- Выбор исполнителя из справочника
- Чекбокс `--dangerously-skip-permissions`
- **⚡ Skills** — раскрывает список скилов
- Поля: расписание, рабочая директория, повторение
- **Ctrl+Enter** — быстрая отправка

## REST API

```
GET    /api/tasks                      — список задач (?status=pending&limit=50&offset=0)
POST   /api/tasks                      — создать задачу
GET    /api/tasks/{id}                 — детали задачи
PATCH  /api/tasks/{id}                 — обновить (отменить, сменить приоритет)
DELETE /api/tasks/{id}                 — удалить
POST   /api/tasks/{id}/reset           — сбросить зависшую задачу в pending

GET    /api/stats                      — статистика по статусам
GET    /api/stats/costs                — затраты по провайдерам (сегодня / неделя / всего)

GET    /api/worker/status              — состояние воркера (paused/running)
POST   /api/worker/pause               — приостановить воркер
POST   /api/worker/resume              — возобновить воркер

GET    /api/providers                  — провайдеры (description, supports_skills, models)
GET    /api/skills                     — скилы (?provider=claude&workdir=/path)
GET    /api/projects                   — проекты из PP_PROJECTS_ROOT
GET    /api/version                    — текущая версия и наличие обновления
GET    /api/config                     — конфигурация (провайдеры, настройки)

GET    /api/interactive/state          — состояние интерактивной сессии
POST   /api/interactive/start          — запустить сессию
POST   /api/interactive/input          — отправить ввод
GET    /api/interactive/output         — получить вывод (cursor-based)
POST   /api/interactive/stop           — завершить сессию

GET    /api/admin/projects             — CRUD проектов
POST   /api/admin/projects
PATCH  /api/admin/projects/{id}
DELETE /api/admin/projects/{id}

GET    /api/admin/agents               — CRUD агентов
POST   /api/admin/agents
PATCH  /api/admin/agents/{id}
DELETE /api/admin/agents/{id}

GET    /api/admin/agents-accounts      — CRUD учётных записей агентов
POST   /api/admin/agents-accounts
PATCH  /api/admin/agents-accounts/{id}
DELETE /api/admin/agents-accounts/{id}
POST   /api/admin/agents-accounts/{id}/relogin/start
POST   /api/admin/agents-accounts/{id}/relogin/finish
POST   /api/admin/agents-accounts/{id}/relogin/cancel

GET    /api/admin/prompts              — CRUD библиотеки промптов
POST   /api/admin/prompts
PATCH  /api/admin/prompts/{id}
DELETE /api/admin/prompts/{id}

GET    /api/admin/workers              — CRUD исполнителей
POST   /api/admin/workers
PATCH  /api/admin/workers/{id}
DELETE /api/admin/workers/{id}

GET    /api/admin/priorities           — CRUD приоритетов
POST   /api/admin/priorities
PATCH  /api/admin/priorities/{id}
DELETE /api/admin/priorities/{id}
```

## Конфигурация

| Переменная | По умолчанию | Описание |
|---|---|---|
| `PP_DB_DSN` | — | DSN для подключения к PostgreSQL |
| `PP_DB_HOST` | `localhost` | Хост PostgreSQL |
| `PP_DB_PORT` | `5432` | Порт PostgreSQL |
| `PP_DB_DATABASE` | — | Имя базы данных |
| `PP_DB_USER` | — | Пользователь БД |
| `PP_DB_PASSWORD` | — | Пароль БД |
| `PP_DB_SCHEMA` | `hubstaff` | Схема PostgreSQL |
| `PP_DB_TASKS_TABLE` | `tasks` | Имя таблицы задач |
| `PP_DB_SETTINGS_TABLE` | `settings` | Имя таблицы настроек |
| `PP_POLL_INTERVAL` | `5` | Интервал опроса очереди (сек) |
| `AGENT_TIMEOUT` | — | Единый таймаут для всех провайдеров (напр. `900`, `15 min`) |
| `PP_TASK_TIMEOUT` | `300` | Таймаут выполнения задачи (сек) |
| `PP_BASE_DELAY` | `60` | Начальная задержка retry (сек) |
| `PP_MAX_DELAY` | `3600` | Максимальная задержка retry (сек) |
| `PP_MAX_RETRIES` | `5` | Макс. кол-во retry по умолчанию |
| `PP_DEFAULT_CLI` | `claude` | Провайдер по умолчанию |
| `PP_HOST` | `127.0.0.1` | Хост веб-сервера |
| `PP_PORT` | `8420` | Порт веб-сервера |
| `PP_TG_TOKEN` | — | Токен Telegram бота |
| `PP_TG_ALLOWED_PHONES` | — | Разрешённые номера (через запятую) |
| `PP_TASK_PASSWORD` | — | Пароль для создания задач через бота |
| `PP_PROJECTS_ROOT` | — | Корневая папка проектов для быстрого выбора директории |
| `PP_CLAUDE_EXE` | `~/.local/bin/claude.exe` | Путь к claude.exe |

## Статусы задач

| Статус | Описание |
|---|---|
| `pending` | В очереди |
| `running` | Выполняется |
| `completed` | Успешно завершена |
| `failed` | Завершена с ошибкой |
| `rate_limited` | Ожидает retry после rate limit |
| `cancelled` | Отменена |

Дополнительно — настраиваемые **статусы задач** из справочника (`tasks_statuses`), которые отображаются в Канбане. По умолчанию:

| Shortname | Название | Отображение в Канбане |
|-----------|----------|-----------------------|
| `done` | Успешно завершена | Да |
| `ready` | Готово | Нет (архивный) |

## Архитектура

```
promptpilot/
├── config.py       — настройки, провайдеры, скилы, build_cmd
├── models.py       — Pydantic-модели (TaskCreate, TaskInDB, Stats, CostStats…)
├── db.py           — PostgreSQL-слой (schema init, CRUD задач, справочники)
├── worker.py       — воркер (subprocess → любой AI CLI, retry/backoff)
├── cli.py          — CLI (Click)
├── api.py          — REST API (FastAPI): задачи, статистика, интерактив, admin
├── bot.py          — Telegram бот (python-telegram-bot)
├── tg_auth.py      — авторизация по номеру телефона
├── tray.py         — tray-управление worker/server/bot
├── limits.py       — опрос rate limits аккаунтов
├── relogin.py      — процедура relogin через интерактив
├── version.py      — версия и проверка обновлений
└── static/
    ├── index.html          — веб-интерфейс (SPA, History API)
    └── images/
        ├── priorities/     — иконки приоритетов (SVG + PNG)
        └── workers/        — аватары исполнителей

docs/
├── README.md               — документация мультиагентной системы
├── agents/                 — инструкции для каждого агента
├── agents-guide.md         — общее руководство по агентам
├── system/                 — схемы, протоколы, жизненный цикл задачи
└── help/                   — контекстная справка для Web UI

start.ps1           — запустить все сервисы
stop.ps1            — остановить все сервисы
build.ps1           — собрать dist\pp.exe
pp.spec             — конфиг PyInstaller
AGENTS.md           — карта проекта для агентной разработки
```

Воркер и сервер — два отдельных процесса, работающих с одной PostgreSQL БД. Воркер выполняет задачи последовательно (одна за раз), чтобы не упираться в rate limits.
