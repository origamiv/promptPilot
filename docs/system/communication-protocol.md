# Протокол коммуникации агентов

## Система задач: pilot.our24.ru (PromptPilot)

API доступен по адресу `http://pilot.our24.ru` без авторизации.

## Создание задачи для агента

PM-агент создаёт дочерние задачи через:

```http
POST http://pilot.our24.ru/api/tasks
Content-Type: application/json

{
  "prompt": "<полный промпт для агента>",
  "subject": "<краткое описание ≤50 символов>",
  "parent_task_id": <ID задачи PM-агента>,
  "working_dir": "/www/wwwroot/newsystem",
  "provider": "<имя провайдера агента>",
  "priority": 5,
  "skip_permissions": true
}
```

### Обязательные поля

| Поле | Описание |
|------|----------|
| `prompt` | Полный контекст задачи: что нужно сделать, ссылки на артефакты предыдущих агентов |
| `subject` | Краткое название для отображения в UI (пример: `"Backend: авторизация JWT"`) |
| `parent_task_id` | ID задачи PM-агента — для отображения прогресса в главной карточке |
| `working_dir` | Рабочая директория проекта |
| `provider` | Имя агента в PromptPilot (настраивается в `/api/admin/agents`) |

### Именование subject

Формат: `"<Роль>: <краткое описание действия>"`

Примеры:
- `"Architect: API контракт авторизации"`
- `"Backend: эндпоинты профиля пользователя"`
- `"Frontend: страница дашборда"`
- `"Mobile: экран входа"`
- `"Database: миграции пользователей"`
- `"UX: макеты онбординга"`
- `"QA: тесты API авторизации"`
- `"DevOps: деплой на staging"`

## Обновление статуса задачи

Каждый агент **обязан** обновлять статус своей задачи:

### Начало работы
```http
PATCH http://pilot.our24.ru/api/tasks/{task_id}
Content-Type: application/json

{ "status": "running" }
```

### Успешное завершение
```http
PATCH http://pilot.our24.ru/api/tasks/{task_id}
Content-Type: application/json

{ "status": "completed" }
```

Результат работы агент записывает в файлы в рабочей директории.
Краткое резюме выводится в stdout задачи (поле `result`).

### Ошибка
```http
PATCH http://pilot.our24.ru/api/tasks/{task_id}
Content-Type: application/json

{ "status": "failed" }
```

## Передача артефактов между агентами

Артефакты передаются через **файловую систему** (git-репозиторий проекта):

| Источник | Артефакт | Путь |
|----------|---------|------|
| Architect | API-контракт | `docs/api/openapi.yaml` |
| Architect | ADR | `docs/adr/ADR-NNN-название.md` |
| Architect | Схема БД | `docs/database/schema.md` |
| UX Designer | PNG макеты | `docs/agents/ux/screens/*.png` |
| Database | Миграции | `database/migrations/*.php` |
| Backend | Реализация | `app/`, `routes/` |
| Frontend | Реализация | `resources/js/` |
| Mobile | Реализация | `mobile/` |

### Ссылки в промптах

PM-агент должен явно указывать пути к артефактам в промпте дочернего агента:

```
Прочитай API-контракт: docs/api/openapi.yaml
Изучи схему БД: docs/database/schema.md
Используй макеты из: docs/agents/ux/screens/
```

## Получение ID своей задачи

При старте агент получает ID своей задачи из переменной окружения или из контекста PromptPilot.
Агент должен обновить статус на `running` как можно раньше — чтобы PM и человек видели прогресс.

## Формат финального резюме задачи (stdout)

Агент выводит структурированное резюме по завершении:

```
## Результат: <Роль агента>

**Статус:** завершено / ошибка

**Что сделано:**
- пункт 1
- пункт 2

**Созданные артефакты:**
- `путь/к/файлу` — описание

**Для следующих агентов:**
- что нужно знать следующим агентам
```
