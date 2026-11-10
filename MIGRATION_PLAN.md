# План миграции Telegram Saver: Flask → FastAPI

Как работать: один шаг = один чат. Новый чат читает `CLAUDE.md` и этот файл, делает только свой шаг,
отмечает его `[x]`, выдаёт текст коммита. Коммитит пользователь в PyCharm. Ветка: `fastapi-migration`.

## Принятые решения
- **Telethon: sync-роуты (`def`) + общий замок** (`threading.Lock`) вокруг вызовов БД и глобального состояния
  (на первых порах и вокруг Telethon). Замок - временное решение, его замена - в перспективных работах.
- **`telegram_handler.py`**: бизнес-логику не меняем, но работу с Telethon оптимизируем: ленивое создание
  `tg_handler`/`db_handler` (шаг 3) и event loop Telethon в фоновом потоке (шаг 3.5). Каждый такой случай
  согласуется заранее. Полностью async-версия `TelegramHandler` - в перспективных работах (см. конец файла).
- **Транзакции БД**: хелпер `transaction()` с `rollback` (шаг 3); применяется в роутах с составной
  записью (шаги 7-9), а обработчик ошибок (шаг 5) только вызывает `rollback()`. Существующие `commit()` в `database_handler.py` не переписываем.
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

### [x] 1. Git и секреты (репозиторий публичный - срочно)
> Выполнено: `.gitignore`, `git rm --cached`. Очистку истории (`filter-repo` + force push) выполняет пользователь.
- `.gitignore`: исправить `config/.env` → `configs/.env`; добавить `database/*.db`, `database/backup/`.
- `git rm --cached configs/.env database/telegram_archive.db`; убедиться, что `.env.example` остаётся.
- Очистка истории от этих файлов: `git filter-repo --invert-paths` + force push. Команды даёт Claude,
  выполняет пользователь (перед этим - резервная копия клона).
- Критерий: `git log --all -- database/telegram_archive.db configs/.env` пуст; в .env были только шаблоны,
  в БД - данные сообщений.
- Коммит: `chore: stop tracking .env and sqlite database, fix .gitignore`

### [x] 2. Зависимости
> Выполнено: зависимости добавлены (верхние границы `<1.0.0`), `requirements.txt` удалён (README описывает только Poetry),
> mypy исправлен. `poetry.lock` в `.gitignore` - в коммит не попадает.
- `pyproject.toml`: добавить `fastapi`, `uvicorn`, `jinja2`, `python-multipart`, `python-dateutil`, `cryptg`;
  dev: `httpx`, `pytest`. Flask пока оставить. Решить судьбу `requirements.txt` (удалить или генерировать
  из poetry; в нём лишние `Flask-SocketIO` и пакет `dotenv`).
- Заодно (согласовано на шаге 0): `[tool.mypy] python_version = ">=3.14"` → `"3.14"` (mypy не принимает диапазон).
- Критерий: `poetry install` проходит, `python -c "import fastapi, uvicorn, dateutil"` работает.
- Коммит: `build: add fastapi stack and missing dependencies`

### [x] 3. Ленивая инициализация Telethon и БД
> Выполнено: фабрики `get_tg_handler()`/`get_db_handler()` (с замком от гонки при создании), `check_same_thread=False`,
> `DatabaseHandler.transaction()`. Проверено одноразовым скриптом без сети; ручной прогон Flask - за пользователем.
- `tg_handler = TelegramHandler()` и `db_handler = DatabaseHandler()` при импорте заменить на фабрики с кэшем
  `get_tg_handler()`/`get_db_handler()` (первый вызов создаёт объект, дальше возвращается он же; создание
  защищено от гонки). В `lifespan` (шаг 4) - по одному вызову каждой. Логику Telethon не менять.
- Старый Flask-код продолжает работать: в `telegram_saver.py` вместо импорта готовых объектов -
  `tg_handler = get_tg_handler()` и `db_handler = get_db_handler()` в начале модуля (остальные ~97 обращений
  не меняются).
- БД: `connect_args={"check_same_thread": False}` в `create_engine` (сессия создаётся в одном потоке, используется
  в потоках пула; защищает её общий замок); хелпер `DatabaseHandler.transaction()` - контекстный менеджер
  (`commit` при успехе, `rollback` при исключении, исключение пробрасывается). Только добавить, не применять.
- Критерий: `import telegram_handler, database_handler` не подключается к Telegram, не запрашивает код и не
  создаёт БД; одноразовый скрипт с замоканными `TelegramClient` и БД во временной папке подтверждает, что
  повторный вызов `get_*_handler()` возвращает тот же объект; Flask-версия работает (ручной прогон пользователем).
- Коммит: `refactor: initialize telegram and database handlers lazily`

### [x] 3.5. Event loop Telethon в фоновом потоке
> Выполнено: loop и daemon-поток создаются в `TelegramHandler.__init__`, хелпер `_run(coro)` (без таймаута, с защитой
> от вызова из потока loop), `close()` (отключение клиента через корутину внутри loop, остановка и закрытие loop).
> Telethon 1.45 игнорирует `loop=`: `client.loop` - loop, запущенный в вызывающем потоке. Поэтому `start()` и
> `disconnect()` вызываются внутри корутин в потоке loop (иначе вход идёт на чужом loop). В Flask - `atexit`.
> Проверено одноразовыми скриптами без сети; ручной прогон Flask - за пользователем.
- Сейчас loop Telethon не крутится между вызовами `run_until_complete` (нет keepalive и фонового переподключения),
  а вызовы из разных потоков конфликтуют («event loop is already running»).
- Loop запускается один раз при создании `TelegramHandler` через `run_forever()` в отдельном потоке (daemon).
  ~10 вызовов `loop.run_until_complete(coro)` заменить на хелпер `_run(coro)` =
  `asyncio.run_coroutine_threadsafe(coro, loop).result()`. Логика Telethon не меняется.
- Остановка: корректное закрытие клиента и loop при завершении (в `lifespan` на шаге 4, в Flask - `atexit`).
- Замок остаётся вокруг БД и состояния; вокруг Telethon он больше не обязателен, но снимается только отдельным
  решением (перспективные работы).
- Критерий: Flask-версия работает, как раньше (ручной прогон пользователем); параллельные запросы не дают
  «loop already running».
- Коммит: `refactor: run telethon event loop in a background thread`

### [x] 4. Каркас FastAPI
> Выполнено: пакет `web/` (`main.py`, `deps.py`, `routers/service.py`). Глобальный `url_for` подтверждён, значения
> путей кодируются как во Flask. `/status_output` без замка (страница опрашивает его во время долгих операций).
> Временные заглушки (501) `tg_get_messages`, `tg_get_details` (`routers/telegram.py`) и `db_get_details`
> (`routers/database.py`) нужны только для `url_for` в шаблонах - заменить реальными роутами на шагах 6 и 8.
> Запускать `uvicorn` с одним воркером и без `--reload`. Проверено одноразовыми скриптами без сети (HTML `/` с данными
> и без, JSON `/status_output`, статика, `lifespan`); ручной запуск `uvicorn web.main:app` - за пользователем.
- `web/main.py`: `FastAPI(lifespan=...)`, инициализация обработчиков в `lifespan`, общий замок в `web/deps.py`.
- Jinja2Templates, `StaticFiles` для `/static` и `/media_storage` (папка создаётся при старте),
  контекстный процессор (12 переменных из `inject_field_names`), глобальный `url_for` (см. решения).
- Роуты `/` и `/status_output`.
- Критерий: `uvicorn web.main:app` стартует, `/` отдаёт ту же страницу, что Flask, `/status_output` - тот же JSON.
- Коммит: `feat: add FastAPI app skeleton with lifespan, templates and static files`

### [x] 5. Обработка ошибок и тестовая инфраструктура
> Выполнено: `web/errors.py` (`register_error_handlers`): ошибки отдаются как `{"error": ...}` (404/405/422/500).
> Обработчик 500 - обычная `def` (Starlette запускает её в потоке): под `state_lock` делает `rollback()`, пишет ошибку
> в статус-бар (с `html.escape`, т.к. строка идёт в `innerHTML`). `tests/`: autouse-фикстура `chdir` во временную папку
> (пути `ProjectDirs` относительные - после P4 заменить на подмену путей), заглушка `TelegramHandler`, настоящий
> `DatabaseHandler` на временном SQLite, подмены через `monkeypatch`. `client` (`with TestClient`, исключения
> пробрасываются) и `error_client` (`raise_server_exceptions=False`). 11 тестов зелёные без сети.
> `transaction()` в обработчике не применяется (там нужен только `rollback()`) - он для шагов 7-9.
> Предупреждение pytest: `httpx` с `starlette.testclient` устарел, рекомендуется `httpx2` - вынесено в перспективные работы.
- Exception handlers: ошибки возвращают JSON (JS ждёт JSON), статусы и логирование вместо `print`.
  Обработчик вызывает `db_handler.session.rollback()`, чтобы одна ошибка не оставляла сессию в состоянии
  `PendingRollbackError` до перезапуска.
- `tests/conftest.py`: TestClient, замоканные `TelegramHandler` и тестовая SQLite-БД в памяти/tmp.
- Тесты для `/`, `/status_output`, `/media_storage/...`.
- Критерий: `pytest` зелёный без сети и без Telegram.
- Коммит: `feat: add JSON error handlers and test infrastructure`

### [x] 6. Роуты Telegram (чтение и фильтры)
> Выполнено: 5 роутов в `web/routers/telegram.py` (заглушки 501 заменены), все `def` под `state_lock` на весь запрос
> (включая вызовы Telethon). В `web/deps.py`: `render_fragment(request, name)` (аналог `render_template`: строка для
> JSON, с контекстным процессором), `FormDep` (`Annotated` + async-зависимость `read_form`: форма читается через
> `await request.form()`, роут остается `def`), `form_str` (None для отсутствующего поля, как `request.form.get`).
> Отличия от Flask (согласованы): `dialog_id: int` - нечисловой ID дает 422 в JSON вместо 500 (отрицательные ID
> каналов и групп проходят); убрана недостижимая ветка `if message_group_id else None` в `tg_get_details`.
> Тесты: `tests/test_telegram_routes.py` (статус, ключи JSON, отрицательные ID, 422, фильтры, ошибка Telegram) и
> ВРЕМЕННЫЙ `tests/test_flask_parity.py` - сравнение JSON и HTML с Flask на одном состоянии-заглушке (удалить на шаге 12).
> Узкие замки (сеть вне замка) и `db_handler` как зависимость - в перспективных работах.
- `web/routers/telegram.py`: `/tg_dialogs`, `/tg_messages/{dialog_id}`, `/tg_details/{dialog_id}/{message_group_id}`,
  `/tg_dialog_apply_filters`, `/tg_message_apply_filters`. Учесть отрицательные `dialog_id`.
- Тесты каждого роута: ответ, статус, ключи JSON.
- Критерий: ответы совпадают с Flask-версией по структуре.
- Коммит: `feat: migrate telegram read and filter routes to FastAPI`

### [x] 7. Сохранение сообщений в БД
> Выполнено: `/tg_save_selected_message_to_db` в `web/routers/telegram.py` (`def` под `state_lock`). Одна транзакция
> `db_handler.transaction()` на группу сообщений (как во Flask: коммит на группу; ошибка откатывает только текущую
> группу), `session.begin()` убран (сессия начинает транзакцию сама), `flush()` перед рендером оставлен (не фиксация,
> откат возможен). `saved_to_db = True` ставится после выхода из `with`. Блок обновления списка диалогов БД и
> пересчета `saved_to_db` вынесен из цикла (один проход после него; закрыт пункт P5 про перекрытие `tg_message_group`).
> Если диалог еще не открывался (список сообщений `None`), роут возвращает пустой JSON (во Flask была ошибка 500;
> страница при пустом JSON ничего не обновляет). Блок выполняется только при непустом выборе (`if selected_messages_ids:`), как раньше во Flask; запросов
> `message_group_exists` стало меньше.
> В `web/deps.py`: `render_fragment(..., **context)` (явные значения перекрывают контекстный процессор; шаблон
> `export_message.html` использует `constants` и `tg_file_types` из него) и `form_list` (аналог `getlist`).
> Тесты: `tests/test_save_route.py` (5 тестов: сохранение двух из трех групп с повторяющимся полем, пустой выбор,
> пересчет флагов, повторное сохранение без дубликатов, ошибка на второй группе). В тесте ошибки откат обеспечивают
> оба слоя (`transaction()` и обработчик 500 из шага 5), поэтому `transaction()` отдельно проверен в
> `tests/test_database_transaction.py` (3 теста: commit, rollback с повторным выбросом, ошибка БД). Сравнения с Flask
> в `test_flask_parity.py` для этого роута нет (роут пишет на диск и в БД, Flask-приложение берет те же заглушки).
- `/tg_save_selected_message_to_db` (самый большой роут): повторяющееся поле формы,
  рендер `export_message.html` вне запроса, транзакция с откатом при ошибке (`db_handler.transaction()`).
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
- Удалить Flask-код и зависимость, `requirements.txt`, неиспользуемое, а также временный `tests/test_flask_parity.py`.
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
- [ ] P5. Мелочи: `logging` вместо `print`, побочные эффекты в list comprehension. (Переменная цикла
  `tg_message_group` в сохранении исправлена на шаге 7 в FastAPI-версии; во Flask-эталоне остается до шага 12.)
- [x] P7. БАГ (найден до миграции на Flask-версии, запуск из PyCharm; исправлен отдельным коммитом `fix:`): сохранение
  сообщения из личного чата или группы давало `Error binding parameter: type 'PeerUser' is not supported` (Flask в
  `debug=True` показывал HTML-страницу ошибки, после чего все запросы давали 500: сессия БД оставалась в
  `PendingRollbackError`, во Flask нет отката; в FastAPI-версии его делает обработчик 500). Причина: в
  `TgMessageGroup.from_id` попадал сырой объект Telethon `message.from_id` (`PeerUser`/`PeerChannel`), а не число;
  сохранялись только посты каналов (`from_id = None`). Исправление: везде `sender_id` (число `message.sender_id`,
  маркированный ID; `None` у собственных исходящих сообщений в личном чате): поле `TgMessageGroup`, шаблон
  `tg_messages.html` (подсветка своих сообщений), столбец `message_groups.sender_id`, `get_export_data`, Flask и FastAPI.
  Для существующей БД SQLite: удалить файл (создастся заново) или выполнить
  `ALTER TABLE message_groups RENAME COLUMN from_id TO sender_id;`. Тесты: `tests/test_message_group.py`.
- [ ] P6. Кнопка «Сохранить в БД» (`tg_action_bar.html`) недоступна, пока нет открытого диалога и отмеченных
  сообщений (сейчас роут при этом ничего не делает, но кнопка нажимается).

## Перспективные работы
- Асинхронный `TelegramHandler` (`async def` + `await`, без `run_until_complete` и отдельного потока loop) и
  async-сессии SQLAlchemy - заменит замок и sync-роуты. Делать после завершения миграции (шаг 13).
- Отказ от глобального `threading.Lock`: сессия SQLAlchemy на запрос (`Depends` с `yield`) и состояние, не
  хранящее ORM-объекты между запросами (иначе `DetachedInstanceError`); для Telethon - сериализация через loop.
  Связано с пунктом выше.
  Сейчас роуты держат замок на весь запрос, включая сетевые вызовы Telethon (`/` ждёт, пока идёт долгий роут).
  Узкие замки (сеть вне замка, под замком только запись состояния) требуют копии фильтров на запрос: методы
  `get_dialog_list`/`get_message_group_list`/`get_message_detail` читают общее состояние и фильтры.
- Тесты при переходе на async: ресурсы с привязкой к event loop (async-движок/сессии SQLAlchemy, async Telethon)
  создавать в `lifespan`, а не лениво; `TestClient` держать в `with` (иначе каждый запрос идёт в новом loop и
  второй падает «another operation is in progress»); для async-тестов - `httpx.AsyncClient` + `ASGITransport` +
  `asgi-lifespan` (`ASGITransport` сам `lifespan` не запускает).
- Тесты: заменить `httpx` на `httpx2` (Starlette считает `httpx` в `TestClient` устаревшим, pytest выдаёт предупреждение).
- Оптимизация фронтенда (не обязательно через HTMX): сейчас роуты отдают JSON с HTML-фрагментами, ключи которого
  совпадают с `id` элементов (`updateElementsFromResponse` в `static/js/my_scripts.js`). Рассмотреть явный контракт
  вместо неявного соответствия `id`, меньше знания сервера о вёрстке, частичные обновления, индикаторы загрузки,
  обработку ошибок. Делать после миграции, поведение при этом меняется.
- Миграция на PostgreSQL, Alembic. ID Telegram не помещаются в `int32` (например, 8837960131 и маркированные ID каналов
  вида `-100...`): столбцы `dialog_id`, `sender_id` и другие ID должны стать `BigInteger`.
- Разбор «Избранного»: список чатов, откуда сообщения были пересланы в Избранное, и фильтр сообщений по выбранному чату.
  `sender_id` для этого не подходит (в Избранном отправитель - сам пользователь); источник пересылки лежит в
  `message.fwd_from`: по документации Telegram `saved_from_peer` - чат, откуда сообщение переслано в Избранное, а
  `from_id`/`from_name` - исходный автор (может быть скрыт). Проверить на реальных сообщениях. Потребуются новые поля
  `TgMessageGroup` и столбцы БД (ID и название чата-источника), поэтому делать вместе с Alembic.
- Экспорт в JSON/CSV/PDF, резервное копирование по расписанию, Docker.
- Многопользовательский режим (состояние в сессии, а не глобально).
