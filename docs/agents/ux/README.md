# UX Designer Agent — Оля Пикселева

## Роль

UX/UI дизайнер. Проектирует экраны в Figma и экспортирует макеты в PNG.
Все PNG-файлы хранятся в `docs/agents/ux/screens/` и используются Frontend и Mobile агентами.

## Входные данные

- Описание требуемых экранов от PM-агента
- `docs/api/openapi.yaml` — для понимания данных (от Architect, если уже готов)
- Существующий Figma-проект (ссылка передаётся в промпте)

## Выходные артефакты

| Артефакт | Путь |
|----------|------|
| PNG экраны Web (desktop) | `docs/agents/ux/screens/web/` |
| PNG экраны Mobile (375px) | `docs/agents/ux/screens/mobile/` |
| Описание экранов | `docs/agents/ux/screens/README.md` |

## Взаимодействует с

- **PM** — получает задачу, описание экранов
- **Architect** — берёт структуру данных для отображения
- **Frontend** — передаёт PNG web-макеты
- **Mobile** — передаёт PNG mobile-макеты

## Когда вызывается

В Фазе 1 (проектирование), параллельно с Architect.

## Структура папки screens/

```
docs/agents/ux/screens/
├── README.md              # Описание каждого экрана
├── web/                   # Десктопные макеты (1440px)
│   ├── 01-dashboard.png
│   ├── 02-profile.png
│   └── ...
└── mobile/                # Мобильные макеты (375px)
    ├── 01-home.png
    ├── 02-profile.png
    └── ...
```

## Именование файлов

Формат: `NN-название-экрана.png` (двузначный номер + kebab-case)

Примеры:
- `01-login.png`
- `02-dashboard.png`
- `03-product-list.png`
- `04-product-detail.png`
- `05-checkout.png`

## Связанные файлы

- [Системный промпт](system.md)
- [Детальные обязанности](responsibilities.md)
- [Папка с экранами](screens/)
