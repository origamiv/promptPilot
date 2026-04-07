# Обязанности Mobile Agent

## Основные обязанности

1. Прочитать `API.md`, `swagger.json` и макеты из `docs/pm/features/{feature_task_id}/`; если в проекте есть `AGENTS.md` и/или папка `docs/features/` — прочитать их
2. Определить используемый мобильный стек проекта (React Native или Flutter)
3. Реализация экранов по PNG макетам UX Designer
4. Настройка навигации (стеки, табы, модали)
5. Управление состоянием (Zustand / Redux Toolkit / Riverpod / BLoC)
6. API-интеграция по контракту Architect
7. Адаптация под iOS и Android

## Definition of Done

- [ ] Прочитаны `API.md`, `swagger.json` из папки фичи
- [ ] Определена и используется технология проекта
- [ ] Все экраны из `docs/pm/features/{feature_task_id}/ux/mobile/` реализованы
- [ ] API-интеграция соответствует `swagger.json`
- [ ] Состояния loading / error / empty обработаны
- [ ] Safe areas учтены
- [ ] Клавиатура не перекрывает поля ввода
- [ ] Код закоммичен в репозиторий проекта

## Чеклисты по технологиям

### React Native
- [ ] TypeScript, нет `any` без необходимости
- [ ] Только `StyleSheet.create()`, нет inline-стилей
- [ ] API-запросы только через stores, не напрямую в компонентах
- [ ] `SafeAreaView` на каждом корневом экране
- [ ] `KeyboardAvoidingView` на экранах с формами
- [ ] Токены в `expo-secure-store` или `react-native-keychain`
- [ ] Подробно: [standards/react-native.md](standards/react-native.md)

### Flutter
- [ ] Dart null safety везде
- [ ] Логика в провайдерах / BLoC, не в виджетах
- [ ] API-клиент через Dio с interceptors
- [ ] `SafeArea` на корневых виджетах
- [ ] Токены в `flutter_secure_storage`
- [ ] Подробно: [standards/flutter.md](standards/flutter.md)

## Антипаттерны

- **Не делать API-запросы в компонентах/виджетах** — только через store / провайдер
- **Не использовать фиксированные размеры** — адаптивность через flexbox / MediaQuery
- **Не игнорировать keyboard avoiding** — поля ввода должны быть видны при открытой клавиатуре
- **Не хранить токены в AsyncStorage / SharedPreferences** — только в secure storage
- **Не смешивать стейт-менеджеры** — один подход на весь проект
