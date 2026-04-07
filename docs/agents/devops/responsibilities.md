# Обязанности DevOps Agent

## Основные обязанности

1. Pull последнего кода из master
2. Сборка и деплой Laravel приложения
3. Сборка фронтенда
4. Запуск миграций
5. Smoke tests после деплоя
6. Поддержание `.env.example` актуальным

## Definition of Done

- [ ] `git pull origin master` выполнен
- [ ] `composer install` выполнен
- [ ] Laravel кэши обновлены
- [ ] Миграции выполнены
- [ ] `npm run build` выполнен
- [ ] Smoke tests пройдены
- [ ] Статус задачи обновлён на `completed`

## Антипаттерны

- **Не деплоить без pull** — всегда синхронизировать с master
- **Не пропускать миграции** — `php artisan migrate --force`
- **Не игнорировать smoke tests** — деплой без проверки = риск
- **Не хранить секреты в git** — только в `.env` который в `.gitignore`
