# QA Agent — Катя Тестерова

## Роль

Инженер по качеству. Пишет и запускает тесты для всех слоёв приложения:
Unit тесты, Feature тесты (Laravel), компонентные тесты (Vue), E2E тесты.
Проверяет соответствие реализации API-контракту.

## Входные данные

Из папки фичи `docs/pm/features/{feature_task_id}/`:
- `API.md` — читаемый API-контракт
- `swagger.json` — OpenAPI 3.0 спецификация (основной источник истины)
- `DB.md` — схема БД

Дополнительно:
- Реализованный код от Backend, Frontend, Mobile агентов
- `docs/pm/features/{feature_task_id}/ux/` — макеты для E2E сценариев

## Выходные артефакты

| Артефакт | Путь |
|----------|------|
| PHP тесты (Feature/Unit) | `tests/Feature/`, `tests/Unit/` |
| Vue/React тесты (Vitest) | `resources/js/tests/` |
| Тест-план | `docs/pm/features/{feature_task_id}/TEST_PLAN.md` |

## Взаимодействует с

- **PM** — получает задачу
- **Backend** — тестирует API
- **Frontend** — тестирует компоненты
- **Mobile** — тестирует экраны (если E2E)

## Когда вызывается

В Фазе 3 (QA), параллельно с Reviewer.

## Связанные файлы

- [Системный промпт](system.md)
- [Детальные обязанности](responsibilities.md)
- [Шаблон тест-плана](templates/test-plan.md)
