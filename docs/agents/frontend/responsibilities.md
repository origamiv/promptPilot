# Обязанности Frontend Agent

## Основные обязанности

1. Прочитать `API.md`, `swagger.json` и макеты из `docs/pm/features/{feature_task_id}/`; если в проекте есть `AGENTS.md` и/или папка `docs/features/` — прочитать их
2. Определить используемый frontend-стек проекта
3. Реализация страниц/экранов по макетам UX Designer
4. Создание переиспользуемых компонентов
5. Интеграция с Backend API по контракту Architect
6. Настройка навигации / роутинга

## Definition of Done

- [ ] Прочитаны `API.md`, `swagger.json` из папки фичи
- [ ] Определена и используется технология проекта
- [ ] Все экраны из `docs/pm/features/{feature_task_id}/ux/web/` реализованы
- [ ] API-интеграция соответствует `swagger.json`
- [ ] Состояния loading / error / empty обработаны
- [ ] Ошибки валидации с сервера отображаются у полей
- [ ] Код закоммичен в репозиторий проекта

## Чеклисты по технологиям

### Vue.js 3 (Composition API)
- [ ] `<script setup>` с TypeScript
- [ ] Запросы через Pinia stores, не напрямую в компонентах
- [ ] API-клиент в `resources/js/api/`
- [ ] Типы в `resources/js/types/`
- [ ] Переиспользуемая логика в composables
- [ ] Vue Router для навигации
- [ ] Подробно: [standards/vue3.md](standards/vue3.md)

### Vue.js 2 (Options API)
- [ ] `data()`, `computed`, `methods`, `watch` — по порядку
- [ ] Глобальное состояние через Vuex (модули)
- [ ] API-запросы через сервисный слой, не в компонентах
- [ ] Vue Router 3 для навигации
- [ ] Подробно: [standards/vue2.md](standards/vue2.md)

### React
- [ ] Функциональные компоненты с хуками
- [ ] Состояние через Redux Toolkit или Zustand
- [ ] API-клиент отделён от компонентов
- [ ] React Router для навигации
- [ ] Подробно: [standards/react.md](standards/react.md)

### jQuery
- [ ] Вся логика в отдельных JS-файлах, не inline в HTML
- [ ] AJAX через `$.ajax` / `fetch` с централизованной обработкой ошибок
- [ ] Нет дублирования селекторов — кешировать `$(selector)` в переменные
- [ ] `$(document).ready()` или `DOMContentLoaded` — не inline onload
- [ ] Подробно: [standards/jquery.md](standards/jquery.md)

### Livewire (Laravel Livewire 3)
- [ ] Один Livewire-компонент = один экран / виджет
- [ ] Валидация через `#[Rule]` атрибуты или `rules()`
- [ ] Тяжёлые операции через `wire:loading`
- [ ] Alpine.js для чисто клиентской интерактивности
- [ ] Подробно: [standards/livewire.md](standards/livewire.md)

### Blade (Laravel Blade)
- [ ] Layouts через `@extends` / `x-layouts`
- [ ] Переиспользуемые блоки в анонимных компонентах `resources/views/components/`
- [ ] Нет бизнес-логики в шаблонах — только отображение данных
- [ ] CSRF-токен во всех формах (`@csrf`)
- [ ] Подробно: [standards/blade.md](standards/blade.md)

## Антипаттерны

- **Не делать API-запросы напрямую в компонентах** — только через stores / сервисный слой
- **Не хардкодить URL** — использовать константы или env переменные
- **Не игнорировать loading / error состояния** — пользователь должен понимать что происходит
- **Не дублировать логику** — выносить в composables, сервисы, хелперы
- **Не смешивать технологии** — если проект на Blade, не добавлять Vue без необходимости
