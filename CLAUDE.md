# Telegram Saver

Личный архиватор Telegram: Telethon (asyncio) → SQLAlchemy (SQLite, схема под PostgreSQL) → веб-интерфейс
(Jinja2 + vanilla JS, ответы JSON с HTML-фрагментами). Однопользовательское приложение, состояние глобальное.
Подробности - в `README.md`.

## Текущая задача
Миграция веб-слоя с Flask на FastAPI без изменения поведения. План и статус шагов: `MIGRATION_PLAN.md`.

## Правила работы
- Одна сессия = один шаг плана. Читай `MIGRATION_PLAN.md`, делай только свой шаг, отметь его `[x]`.
- Бизнес-логику, модели SQLAlchemy и схему БД не менять без явной просьбы.
- `telegram_handler.py`: бизнес-логику работы с Telegram не менять, но саму работу с Telethon (инициализация,
  event loop, потоки) можно оптимизировать. Каждый такой случай сначала уточнять у пользователя.
- Telethon: sync-роуты (`def`) + общий замок (временное решение). Async-вариант и замена замка - только в
  перспективных работах (`MIGRATION_PLAN.md`).
- Нет аналога механизму Flask → сначала предложить замену и дождаться подтверждения.
- Долгие фоновые задачи - через `lifespan` или отдельный процесс, не `BackgroundTasks`.
- Каждое изменение объяснять 1-2 фразами: что и почему.
- Не коммитить и не пушить: коммитит пользователь в PyCharm. В конце шага дай готовый текст коммита.
- Не запускать код, который подключается к Telegram, без просьбы (запрашивает вход и ходит в сеть).

## Ключевые факты
- Запуск (сейчас Flask): `python telegram_saver.py`, порт 5000. Цель: `uvicorn web.main:app`.
- Конфиг: `configs/config.py` (`PROFILE`, `FormCfg`, `ProjectDirs`); секреты в `configs/.env_dev_1` (не в git).
- Файлы: `telegram_handler.py`, `database_handler.py`, `utils.py` (`status_messages`), `templates/`, `static/js/my_scripts.js`.
- Python >= 3.14, менеджер зависимостей Poetry. Тесты: pytest, Telethon мокается.
- Репозиторий публичный: не добавлять в git `.env*`, `*.db`, `*.session`, `media_storage/`.
- Комментарии и docstring в коде двуязычные (EN / RU) - сохранять этот стиль, стиль PEP 8, длина строки 120.

## Формат коммитов
`type: short summary` по-английски, в повелительном наклонении (`feat`, `fix`, `refactor`, `chore`, `docs`,
`build`, `test`), как в истории проекта.
