"""
Test infrastructure: no network, no Telegram, no real database or media files.
Тестовая инфраструктура: без сети, без Telegram, без настоящих базы данных и медиафайлов.

Every test runs in its own temporary directory: the paths in `ProjectDirs` (absolute) are replaced by paths inside it,
so a test never touches the real media, export or database. The Telegram handler is a fake object, the database
handler is real but works with a SQLite file in that directory.
Каждый тест выполняется в своей временной директории: пути в `ProjectDirs` (абсолютные) заменяются путями внутри нее,
поэтому тест никогда не трогает настоящие медиа, экспорт и базу данных. Обработчик Telegram - заглушка, обработчик БД -
настоящий, но работает с файлом SQLite в этой директории.
"""

from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock
import pytest
import starlette.testclient
from fastapi.testclient import TestClient
import database_handler
import telegram_handler
import config
from config import HOST, PORT, ProjectDirs
from database_handler import DatabaseHandler
from telegram_handler import TgCurrentState, TgMessageSortFilter
from web.main import app

# The clients talk to the server address, otherwise the request guard rejects the default `testserver` host
# Клиенты обращаются к адресу сервера, иначе защита запросов отклонит хост `testserver` по умолчанию
BASE_URL = f'http://{HOST}:{PORT}'


def _ui(self: starlette.testclient.httpx.Response) -> dict:
    """
    The updates of a successful response of the UI contract (`web/ui.py`) as one dict: element id -> new HTML, or the
    new `checked` state of a checkbox. A response with another body (an error) gives an empty dict, use `json()` there.
    Обновления успешного ответа контракта интерфейса (`web/ui.py`) одним словарем: id элемента -> новый HTML или новое
    состояние `checked` чек-бокса. Ответ с другим телом (ошибка) дает пустой словарь, для него нужен `json()`.
    """
    body = self.json()
    return {**body.get('html', {}), **body.get('checked', {})}


# The test client answers with the response class of the HTTP library Starlette uses (`httpx2` here)
# Тестовый клиент отвечает классом ответа HTTP-библиотеки, которую использует Starlette (здесь `httpx2`)
# `response.ui()` in the tests of the routes that answer by the contract / `response.ui()` в тестах роутов с контрактом
starlette.testclient.httpx.Response.ui = _ui  # type: ignore[attr-defined]


@pytest.fixture(autouse=True)
def work_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """
    Temporary working directory with the folders the application expects.
    Временная рабочая директория с папками, которые ожидает приложение.
    """
    paths = {
        'media_dir': tmp_path / ProjectDirs.media_dir_name,
        'export_dir': tmp_path / ProjectDirs.export_dir.name,
        'cache_dir': tmp_path / ProjectDirs.cache_dir_name,
        'profile_dir': tmp_path,
        'telegram_settings_file': tmp_path / ProjectDirs.telegram_settings_file.name,
        'session_file': tmp_path / ProjectDirs.session_file.name,
        'profile_info_file': tmp_path / ProjectDirs.profile_info_file.name,
        'data_base_dir': tmp_path / ProjectDirs.data_base_dir.name,
        'data_base_file': tmp_path / ProjectDirs.data_base_dir.name / ProjectDirs.data_base_file.name,
    }
    for name, path in paths.items():
        monkeypatch.setattr(ProjectDirs, name, path)
    # A profile is selected (the lifespan refuses to start without one)
    # Профиль выбран (lifespan отказывается стартовать без него)
    monkeypatch.setattr(config, 'PROFILE', 'test')
    # The media files are served by a mount created when the application was imported: point it to the temp directory
    # Медиафайлы отдает монтирование, созданное при импорте приложения: направляем его в временную директорию
    media_mount = next(route for route in app.routes if getattr(route, 'name', None) == 'media_dir')
    monkeypatch.setattr(media_mount.app, 'directory', paths['media_dir'])
    monkeypatch.setattr(media_mount.app, 'all_directories', [paths['media_dir']])
    cache_mount = next(route for route in app.routes if getattr(route, 'name', None) == 'cache_dir')
    monkeypatch.setattr(cache_mount.app, 'directory', paths['cache_dir'])
    monkeypatch.setattr(cache_mount.app, 'all_directories', [paths['cache_dir']])
    paths['data_base_dir'].mkdir()
    paths['media_dir'].mkdir()
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.fixture
def tg_handler(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    """
    Fake TelegramHandler with the attributes the templates and lifespan use. It replaces the cached handler, so
    `get_tg_handler()` returns it and never creates a real client.
    Заглушка TelegramHandler с атрибутами, которые используют шаблоны и lifespan. Заменяет кэшированный обработчик,
    поэтому `get_tg_handler()` возвращает ее и не создает настоящий клиент.
    """
    # The real filter with the defaults, as the real handler sets it (the page shows its dates)
    # Настоящий фильтр с умолчаниями, как его задает настоящий обработчик (страница показывает его даты)
    message_filter = TgMessageSortFilter()
    message_filter.set_default_filters()
    fake = SimpleNamespace(
        me=SimpleNamespace(id=1),
        message_sort_filter=message_filter,
        dialog_sort_filter=MagicMock(),
        current_state=TgCurrentState(),
        # Reading methods: the tests set the return values they need
        # Методы чтения: тесты задают нужные им возвращаемые значения
        get_dialog_list=MagicMock(return_value=[]),
        get_message_group_list=MagicMock(return_value=[]),
        get_message_detail=MagicMock(return_value=None),
        close=MagicMock(),
    )
    monkeypatch.setattr(telegram_handler, '_tg_handler', fake)
    return fake


@pytest.fixture
def db_handler(work_dir: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[DatabaseHandler]:
    """
    Real DatabaseHandler on a temporary SQLite file (created relative to the temporary working directory).
    Настоящий DatabaseHandler на временном файле SQLite (создается относительно временной рабочей директории).
    """
    handler = DatabaseHandler()
    monkeypatch.setattr(database_handler, '_db_handler', handler)
    yield handler
    # The file must be released before pytest deletes the temporary directory (Windows)
    # Файл нужно освободить до того, как pytest удалит временную директорию (Windows)
    handler.session.close()
    handler.engine.dispose()


@pytest.fixture
def client(tg_handler: SimpleNamespace, db_handler: DatabaseHandler) -> Iterator[TestClient]:
    """
    TestClient inside `with`: the application lifespan runs. Server exceptions are re-raised into the test.
    TestClient внутри `with`: выполняется lifespan приложения. Исключения сервера пробрасываются в тест.
    """
    with TestClient(app, base_url=BASE_URL) as test_client:
        yield test_client


@pytest.fixture
def error_client(tg_handler: SimpleNamespace, db_handler: DatabaseHandler) -> Iterator[TestClient]:
    """
    TestClient that returns the 500 response instead of re-raising the exception (to test the error handlers).
    TestClient, который возвращает ответ 500 вместо повторного выброса исключения (для проверки обработчиков ошибок).
    """
    with TestClient(app, base_url=BASE_URL, raise_server_exceptions=False) as test_client:
        yield test_client
