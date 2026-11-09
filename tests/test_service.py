"""
Tests of the service routes: the main page, the status bar and the media files.
Тесты служебных маршрутов: главная страница, строка статуса и медиафайлы.
"""

from pathlib import Path
from types import SimpleNamespace
from fastapi.testclient import TestClient
from configs.config import ProjectDirs
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
