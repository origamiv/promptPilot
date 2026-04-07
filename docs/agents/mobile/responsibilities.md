# Обязанности Mobile Agent

## Основные обязанности

1. Реализация экранов по PNG макетам UX Designer
2. Настройка навигации (стеки, табы, модали)
3. Создание Zustand stores для состояния
4. API-интеграция по контракту Architect
5. Адаптация под iOS и Android

## Definition of Done

- [ ] Все экраны из `docs/agents/ux/screens/mobile/` реализованы
- [ ] API-интеграция работает по `docs/api/openapi.yaml`
- [ ] Состояния loading/error/empty обработаны
- [ ] Safe areas учтены (SafeAreaView)
- [ ] Код закоммичен в `master`: `git@github.com:origamiv/newsystem.git`
- [ ] Статус задачи обновлён на `completed`

## Антипаттерны

- **Не использовать inline styles** — только StyleSheet.create()
- **Не делать API-запросы в компонентах** — только через stores
- **Не игнорировать keyboard avoiding** — поля ввода должны быть видны при открытой клавиатуре
- **Не использовать фиксированные размеры** — адаптивность через flexbox
