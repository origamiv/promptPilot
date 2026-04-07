# Мультиагентная система разработки

Документация системы для создания веб и мобильных приложений на основе специализированных AI-агентов.

## Стек

| Слой | Технология |
|------|-----------|
| Backend | PHP 8, Laravel 12 |
| База данных | PostgreSQL |
| Web frontend | Vue.js 3 |
| Mobile | React Native |
| Доп. сервисы | Python / Node.js |
| Задачи | [pilot.our24.ru](http://pilot.our24.ru) (PromptPilot) |

## Агенты

| Агент | Имя | Папка | Краткое описание |
|-------|-----|-------|-----------------|
| PM / Orchestrator | Максим Управленцев | [agents/pm](agents/pm/README.md) | Декомпозиция задачи, координация агентов |
| Architect | Артём Зодчев | [agents/architect](agents/architect/README.md) | Системный дизайн, API-контракты, ADR |
| Backend | Сергей Серверов | [agents/backend](agents/backend/README.md) | Laravel 12 / PHP 8 |
| Frontend | Вася Кнопкин | [agents/frontend](agents/frontend/README.md) | Vue.js 3 |
| Mobile | Андрей Свайпов | [agents/mobile](agents/mobile/README.md) | React Native |
| Database | Пётр Базданов | [agents/database](agents/database/README.md) | PostgreSQL, миграции, оптимизация |
| UX Designer | Оля Пикселева | [agents/ux](agents/ux/README.md) | Figma макеты → PNG |
| QA | Катя Тестерова | [agents/qa](agents/qa/README.md) | Тесты, покрытие, тест-планы |
| Reviewer | Антон Придирин | [agents/reviewer](agents/reviewer/README.md) | Code review |
| DevOps | Женя Деплойкин | [agents/devops](agents/devops/README.md) | Docker, CI/CD, деплой |
| Integrations | Лёша Коннекторов | [agents/integrations](agents/integrations/README.md) | Python/Node.js воркеры, очереди |

## Режимы работы агентов

Все агенты работают в одном из двух режимов:

### Auto-режим (без подтверждения)
- Агент выполняет задачу autonomously
- Не запрашивает подтверждения на промежуточные шаги
- Подходит для стандартных задач и исправлений

### Approval-режим (с подтверждением)
1. Агент создает детальный план работы
2. Устанавливает статус задачи "Ожидает подтверждения"
3. Представляет план пользователю
4. После подтверждения реализует план
5. При замечаниях - создает новый план и повторяет цикл

## Как работает система

1. Человек создаёт задачу в [pilot.our24.ru](http://pilot.our24.ru) и назначает её PM-агенту
2. PM-агент декомпозирует задачу и создаёт подзадачи для каждого нужного агента
3. Каждый агент меняет статус задачи: `pending → running → completed`
4. Прогресс по фиче виден в главной карточке PM-задачи через список дочерних задач
5. PM-агент завершает свою задачу финальным отчётом

## Документация системы

### Основные документы
- [Обзор архитектуры](system/overview.md)
- [Схема взаимодействия агентов](system/interaction-scheme.md)
- [Протокол коммуникации](system/communication-protocol.md)
- [Жизненный цикл задачи](system/task-lifecycle.md)

### Настройка и управление
- [Настройка агентов](system/agent-setup.md)
- [Режимы работы агентов](#режимы-работы-агентов)
- [Лучшие практики](system/best-practices.md)

### Сценарии использования
- [Типичные сценарии](system/use-cases.md)
