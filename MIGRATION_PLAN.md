# План миграции Telegram Saver: Flask → FastAPI

Как работать: один шаг = один чат. Новый чат читает `CLAUDE.md` и этот файл, делает только свой шаг,
отмечает его `[x]`, выдаёт текст коммита. Коммитит пользователь в PyCharm. Ветка: `fastapi-migration`.

## Принятые решения
- **Telethon: sync-роуты (`def`) + общий замок** (`threading.Lock`) вокруг всех вызовов Telethon и БД.
  `telegram_handler.py` не переписываем; меняется только момент создания `tg_handler`/`db_handler`
  (из импорта в `lifespan`). Async-версия `TelegramHandler` - в перспективных работах (см. конец файла).
- Однопользовательское приложение: глобальное состояние (`current_state`, фильтры) сохраняем как есть.
- Новый код живёт в пакете `web/` (`main.py`, `deps.py`, `routers/`). Старый Flask в `telegram_saver.py`
  остаётся эталоном до шага 13; после него `telegram_saver.py` - тонкий запускатель uvicorn,
  чтобы `python telegram_saver.py` работал как в README.
- Группировка маршрутов через `APIRouter` (аналог Blueprint), без `prefix=`, чтобы URL остались прежними:
  `routers/telegram.py` (`tg_*`), `routers/database.py` (`db_*` сообщения), `routers/tags.py`,
  `routers/service.py` (`/`, `/status_output`, `maintenance`). Подключаются через `include_router` в `web/main.py`.
- В миграцию входит: git/секреты, зависимости, lifespan, сессия БД, обработка ошибок, тесты, README.
  После неё отдельными коммитами: XSS, CSRF/Origin, защита maintenance.
- Имена полей форм динамические (`FormCfg`) - читаем `await request.form()`, не `Form(...)`.
- Нужна замена механизму Flask `url_for` (в 6 шаблонах): **предложение** - глобал `url_for` в Jinja2
  с Flask-совместимой сигнатурой (`filename`→`path`, `_external`), шаблоны не правим. Подтвердить на шаге 5.

## Шаги миграции

### [x] 0. Подготовка
- Закоммитить в `master` текущие правки (`pyproject.toml`, опечатка в TODO), создать ветку `fastapi-migration`.
- Критерий: `git status` чист, ветка создана.
- Коммит (master): `chore: update pyproject metadata and fix TODO typo`

### [ ] 1. Git и секреты (репозиторий публичный - срочно)
- `.gitignore`: исправить `config/.env` → `configs/.env`; добавить `database/*.db`, `database/backup/`.
- `git rm --cached configs/.env database/telegram_archive.db`; убедиться, что `.env.example` остаётся.
- Очистка истории от этих файлов: `git filter-repo --invert-paths` + force push. Команды даёт Claude,
  выполняет пользователь (перед этим - резервная копия клона).
- Критерий: `git log --all -- database/telegram_archive.db configs/.env` пуст; в .env были только шаблоны,
  в БД - данные сообщений.
- Коммит: `chore: stop tracking .env and sqlite database, fix .gitignore`

### [ ] 2. Зависимости
- `pyproject.toml`: добавить `fastapi`, `uvicorn`, `jinja2`, `python-multipart`, `python-dateutil`, `cryptg`;
  dev: `httpx`, `pytest`. Flask пока оставить. Решить судьбу `requirements.txt` (удалить или генерировать
  из poetry; в нём лишние `Flask-SocketIO` и пакет `dotenv`).
- Критерий: `poetry install` проходит, `python -c "import fastapi, uvicorn, dateutil"` работает.
- Коммит: `build: add fastapi stack and missing dependencies`

### [ ] 3. Ленивая инициализация Telethon и БД
- `tg_handler = TelegramHandler()` и `db_handler = DatabaseHandler()` при импорте заменить на создание
  по требованию (`get_tg_handler()`/`get_db_handler()` или `init()` для `lifespan`). Логику Telethon не менять.
  Старый Flask-код должен продолжать работать.
- БД: `check_same_thread=False`, helper с `rollback` при исключении.
- Критерий: `import telegram_handler` не подключается к Telegram и не запрашивает код; Flask-версия работает.
- Коммит: `refactor: initialize telegram and database handlers lazily`

### [ ] 4. Каркас FastAPI
- `web/main.py`: `FastAPI(lifespan=...)`, инициализация обработчиков в `lifespan`, общий замок в `web/deps.py`.
- Jinja2Templates, `StaticFiles` для `/static` и `/media_storage` (папка создаётся при старте),
  контекстный процессор (12 переменных из `inject_field_names`), глобальный `url_for` (см. решения).
- Роуты `/` и `/status_output`.
- Критерий: `uvicorn web.main:app` стартует, `/` отдаёт ту же страницу, что Flask, `/status_output` - тот же JSON.
- Коммит: `feat: add FastAPI app skeleton with lifespan, templates and static files`

### [ ] 5. Обработка ошибок и тестовая инфраструктура
- Exception handlers: ошибки возвращают JSON (JS ждёт JSON), статусы и логирование вместо `print`.
- `tests/conftest.py`: TestClient, замоканные `TelegramHandler` и тестовая SQLite-БД в памяти/tmp.
- Тесты для `/`, `/status_output`, `/media_storage/...`.
- Критерий: `pytest` зелёный без сети и без Telegram.
- Коммит: `feat: add JSON error handlers and test infrastructure`

### [ ] 6. Роуты Telegram (чтение и фильтры)
- `web/routers/telegram.py`: `/tg_dialogs`, `/tg_messages/{dialog_id}`, `/tg_details/{dialog_id}/{message_group_id}`,
  `/tg_dialog_apply_filters`, `/tg_message_apply_filters`. Учесть отрицательные `dialog_id`.
- Тесты каждого роута: ответ, статус, ключи JSON.
- Критерий: ответы совпадают с Flask-версией по структуре.
- Коммит: `feat: migrate telegram read and filter routes to FastAPI`

### [ ] 7. Сохранение сообщений в БД
- `/tg_save_selected_message_to_db` (самый большой роут): повторяющееся поле формы,
  рендер `export_message.html` вне запроса, транзакция с откатом при ошибке.
- Тест с замоканным скачиванием файлов.
- Коммит: `feat: migrate save-to-database route to FastAPI`

### [ ] 8. Роуты БД
- `/db_message_apply_filters`, `/db_details/{message_group_id}` (случай `None`),
  `/db_export_selected_message_to_html`, `/db_delete_selected_from_database`.
- Коммит: `feat: migrate database message routes to FastAPI`

### [ ] 9. Роуты тегов
- `/db_tag_add`, `/db_tag_remove`, `/db_tag_update`, `/db_tag_update_everywhere`, `/db_all_tag_sorting`;
  общий хелпер вместо пяти копий разбора формы. Случай `selected_message_group_id is None`.
- Коммит: `feat: migrate tag routes to FastAPI`

### [ ] 10. Сервисное обслуживание
- `/db_database_maintenance` без изменения логики (защита - в пост-миграционных работах).
- Тест на временной директории: удаление лишних файлов, бэкап БД.
- Коммит: `feat: migrate database maintenance route to FastAPI`

### [ ] 11. Запуск через uvicorn и ручная проверка
- `telegram_saver.py` → запускатель `uvicorn.run("web.main:app", host="127.0.0.1", port=5000)`.
- Ручной прогон в браузере с реальным Telethon: все кнопки интерфейса, включая сохранение и экспорт.
- Критерий: чек-лист «все маршруты проверены» (пункт 4 критерия готовности).
- Коммит: `feat: run application via uvicorn`

### [ ] 12. Удаление Flask
- Удалить Flask-код и зависимость, `requirements.txt`, неиспользуемое.
- Критерий: `grep -ri flask` по проекту чист, тесты и ручной прогон проходят.
- Коммит: `refactor: remove Flask code and dependency`

### [ ] 13. README и документация
- Переписать Usage (остался от другого проекта), установка и запуск через uvicorn, инструкция по получению
  параметров Telegram, актуализировать docstring в `configs/config.py`, формат даты (`%H:%M :%S`).
- Коммит: `docs: update README for FastAPI and uvicorn`

## После миграции (отдельные коммиты)
- [ ] P1. XSS: убрать `|safe` у текста Telegram (8 мест), экранировать `status_messages` и `innerHTML`;
  переводы строк и `[text](url)` обрабатывать отдельно.
- [ ] P2. CSRF/localhost: проверка `Origin`/`Host` для POST, привязка к `127.0.0.1`, без `debug`.
- [ ] P3. Защита `/db_database_maintenance`: dry-run/лимит удаления, проверка пустой БД и профиля.
- [ ] P4. Конфигурация: `PROFILE` из переменной окружения, абсолютные пути от корня проекта.
- [ ] P5. Мелочи: `logging` вместо `print`, побочные эффекты в list comprehension, переменная цикла
  `tg_message_group` в сохранении.

## Перспективные работы
- Асинхронный `TelegramHandler` (`async def` + `await`, без `run_until_complete`) и async-сессии SQLAlchemy -
  заменит замок и sync-роуты.
- Миграция на PostgreSQL, Alembic.
- Экспорт в JSON/CSV/PDF, резервное копирование по расписанию, Docker.
- Многопользовательский режим (состояние в сессии, а не глобально).
