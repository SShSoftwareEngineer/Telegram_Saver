"""
Test infrastructure: no network, no Telegram, no real database or media files.
Тестовая инфраструктура: без сети, без Telegram, без настоящих базы данных и медиафайлов.

Every test runs in its own temporary working directory (the project paths in `ProjectDirs` are relative), the
Telegram handler is a fake object, the database handler is real but works with a SQLite file in that directory.
Каждый тест выполняется в своей временной рабочей директории (пути проекта в `ProjectDirs` относительные), обработчик
Telegram - заглушка, обработчик БД - настоящий, но работает с файлом SQLite в этой директории.
"""

from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock
import pytest
from fastapi.testclient import TestClient
import database_handler
import telegram_handler
from configs.config import ProjectDirs
from database_handler import DatabaseHandler
from telegram_handler import TgCurrentState
from web.main import app


@pytest.fixture(autouse=True)
def work_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """
    Temporary working directory with the folders the application expects.
    Временная рабочая директория с папками, которые ожидает приложение.
    """
    (tmp_path / ProjectDirs.data_base_dir).mkdir()
    (tmp_path / ProjectDirs.media_dir).mkdir()
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
    fake = SimpleNamespace(
        me=SimpleNamespace(id=1),
        message_sort_filter=SimpleNamespace(date_from_default='2026-01-01'),
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
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def error_client(tg_handler: SimpleNamespace, db_handler: DatabaseHandler) -> Iterator[TestClient]:
    """
    TestClient that returns the 500 response instead of re-raising the exception (to test the error handlers).
    TestClient, который возвращает ответ 500 вместо повторного выброса исключения (для проверки обработчиков ошибок).
    """
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client
