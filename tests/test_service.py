"""
Tests of the service routes: the main page, the status bar and the media files.
Тесты служебных маршрутов: главная страница, строка статуса и медиафайлы.
"""

from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
import pytest
from fastapi.testclient import TestClient
from configs.config import ProjectDirs
from database_handler import DatabaseHandler
from utils import status_messages


def test_index_without_dialogs(client: TestClient):
    """The main page opens and shows no chat counter when there are no dialogs / Страница без счетчика чатов"""
    response = client.get('/')
    assert response.status_code == 200
    assert response.headers['content-type'].startswith('text/html')
    assert '<span id="tg-chats-count"></span>' in response.text


def test_index_with_dialogs(client: TestClient, tg_handler: SimpleNamespace):
    """The page shows the number of chats and their titles, negative dialog IDs go to the URL as they are"""
    tg_handler.current_state.dialog_list = [SimpleNamespace(dialog_id=-1001234, title='Test chat')]
    response = client.get('/')
    assert response.status_code == 200
    assert '(1)' in response.text
    assert 'Test chat' in response.text
    assert '/tg_messages/-1001234' in response.text


def test_status_output(client: TestClient):
    """The status bar returns the current messages as JSON / Строка статуса возвращает сообщения в виде JSON"""
    status_messages.mess_update('Test operation', 'Test report', new_list=True)
    response = client.get('/status_output')
    assert response.status_code == 200
    data = response.json()
    assert set(data) == {'sb_operation', 'sb_report'}
    assert 'Test operation' in data['sb_operation']
    assert 'Test report' in data['sb_report']


def test_media_file(client: TestClient, work_dir: Path):
    """A file from the media folder is served from the temporary working directory / Раздача медиафайла"""
    (work_dir / ProjectDirs.media_dir / 'photo.txt').write_text('media content', encoding='utf-8')
    response = client.get(f'/{ProjectDirs.media_dir}/photo.txt')
    assert response.status_code == 200
    assert response.text == 'media content'


def test_media_file_not_found(client: TestClient):
    """A missing media file gives 404 in JSON, not a plain-text page / Отсутствующий файл - 404 в JSON"""
    response = client.get(f'/{ProjectDirs.media_dir}/missing.jpg')
    assert response.status_code == 404
    assert 'error' in response.json()


def test_index_highlights_own_saved_messages(client: TestClient, db_handler: DatabaseHandler,
                                             monkeypatch: pytest.MonkeyPatch):
    """In the database list only the messages of the logged-in account (`sender_id` equals `tg_me.id`) are indented,
    as in the Telegram list / В списке БД с отступом только сообщения владельца аккаунта, как в списке Telegram"""
    def saved_group(number: int, sender_id: int | None) -> SimpleNamespace:
        return SimpleNamespace(grouped_id=f'42_{number}', date=datetime(2026, 1, number, 3, 4, 5), text=f'Text {number}',
                               files_report='1 photo', sender_id=sender_id, dialog=SimpleNamespace(title='Chat'))

    monkeypatch.setattr(db_handler.current_state, 'message_group_list', [
        saved_group(1, 1), saved_group(2, 2), saved_group(3, -1001234567891), saved_group(4, None)])
    response = client.get('/')
    assert response.status_code == 200
    assert 'Text 1' in response.text and 'Text 4' in response.text
    assert response.text.count('my-message-in-list') == 1
    # No empty lines between the messages: the texts here have no line breaks, so a `<br>` in the list would come
    # from the template (the Telegram list has none either) / Пустых строк между сообщениями нет: в списке нет `<br>`
    message_list = response.text.split('id="db_messages"')[1].split('id="db_details"')[0]
    assert '<br>' not in message_list
    # The files report is a block, so it stays on its own line also for a message without text
    # Отчет о файлах - блок, поэтому он на своей строке и у сообщения без текста
    assert message_list.count('<div><b>1 photo</b></div>') == 4
