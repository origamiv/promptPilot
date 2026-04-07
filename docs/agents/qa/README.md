# QA Agent — Катя Тестерова

## Роль

Инженер по качеству. Пишет и запускает тесты для всех слоёв приложения:
Unit тесты, Feature тесты (Laravel), компонентные тесты (Vue), E2E тесты.
Проверяет соответствие реализации API-контракту.

## Входные данные

- Реализованный код от Backend, Frontend, Mobile агентов
- `docs/api/openapi.yaml` — для проверки соответствия API
- `docs/agents/ux/screens/` — для E2E сценариев

## Выходные артефакты

| Артефакт | Путь |
|----------|------|
| PHP тесты (Feature/Unit) | `tests/Feature/`, `tests/Unit/` |
| Vue тесты (Vitest) | `resources/js/tests/` |
| Тест-план | `docs/agents/qa/test-plans/` |

## Взаимодействует с

- **PM** — получает задачу
- **Backend** — тестирует API
- **Frontend** — тестирует компоненты
- **Mobile** — тестирует экраны (если E2E)

## Когда вызывается

В Фазе 3 (QA), параллельно с Reviewer.

## Связанные файлы

- [Системный промпт](system-prompt.md)
- [Детальные обязанности](responsibilities.md)
- [Шаблон тест-плана](templates/test-plan.md)
