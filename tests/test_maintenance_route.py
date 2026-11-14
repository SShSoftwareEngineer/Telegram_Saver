"""
Tests of the maintenance route: the report of files without records, the download of missing files, the database backup,
the refresh of the dialog and tag lists. Nothing is deleted. Telegram is a fake object, the database is real.
Тесты маршрута обслуживания: отчет о файлах без записей, докачка отсутствующих файлов, резервная копия базы данных,
обновление списков диалогов и тегов. Ничего не удаляется. Telegram - заглушка, база данных - настоящая.
"""

import sqlite3
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock
import pytest
from fastapi.testclient import TestClient
from configs.config import DialogTypes, FormCfg, GlobalConst, MessageFileTypes, ProjectDirs
from database_handler import DatabaseHandler, DbDialog, DbFile, DbMessageGroup, DbTag
from utils import status_messages

DIALOG_SELECT = FormCfg.db_message_filter['dialog_select']
ALL_TAGS = FormCfg.db_detail_tags['all_detail_tags']


@pytest.fixture(autouse=True)
def download_mock(tg_handler: SimpleNamespace) -> MagicMock:
    """The fake Telegram handler gets the download method / Заглушка Telegram получает метод скачивания"""
    tg_handler.download_message_file_from_list = MagicMock(return_value='')
    return tg_handler.download_message_file_from_list


def add_message(db_handler: DatabaseHandler, dialog_id: int, title: str, file_paths: tuple[str, ...]) -> None:
    """Adds a dialog with one message group that has the given files / Диалог с одной группой сообщений и файлами"""
    session = db_handler.session
    session.add(DbDialog(dialog_id=dialog_id, title=title, dialog_type_id=DialogTypes.CHANNEL.value))
    group = DbMessageGroup(grouped_id=f'{dialog_id}_1', date=datetime(2026, 1, 1, 3, 4, 5), text='text',
                           truncated_text='text', files_report='', sender_id=7, dialog_id=dialog_id)
    for number, file_path in enumerate(file_paths, start=1):
        group.files.append(DbFile(file_path=file_path, message_id=number, size=10 * number,
                                  file_type_id=MessageFileTypes.IMAGE.type_id))
    session.add(group)
    session.commit()


def make_media_file(work_dir: Path, file_path: str, size: int = 5) -> Path:
    """Creates a media file by its path relative to the media directory / Создает файл медиа по относительному пути"""
    path = work_dir / ProjectDirs.media_dir / file_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b'x' * size)
    return path


def report() -> list[str]:
    """The current status bar report lines / Текущие строки отчета в строке статуса"""
    return status_messages.report_list or []


def test_maintenance_response_keys_and_list_refresh(client: TestClient, db_handler: DatabaseHandler):
    """The response refreshes the dialog and tag selects: the dialog without messages and the unused tag are gone"""
    add_message(db_handler, 1, 'Used chat', ())
    db_handler.session.add(DbDialog(dialog_id=2, title='Unused chat', dialog_type_id=DialogTypes.CHANNEL.value))
    db_handler.session.add(DbTag(name='stale'))
    db_handler.session.commit()

    response = client.post('/db_database_maintenance')

    assert response.status_code == 200
    data = response.json()
    assert set(data) == {DIALOG_SELECT, ALL_TAGS}
    assert '>Used chat</option>' in data[DIALOG_SELECT] and 'Unused chat' not in data[DIALOG_SELECT]
    assert 'stale' not in data[ALL_TAGS]
    assert [dialog.dialog_id for dialog in db_handler.current_state.dialog_list] == [1]
    assert db_handler.session.query(DbTag).count() == 0


def test_maintenance_downloads_missing_files_except_html(client: TestClient, db_handler: DatabaseHandler,
                                                         work_dir: Path, download_mock: MagicMock):
    """The file with a record but not on the disk is downloaded by its relative path; an existing file and a missing
    HTML file are not"""
    add_message(db_handler, 1, 'chat', ('chat/2026-01-01/kept.jpg', 'chat/2026-01-01/missing.jpg',
                                        'chat/2026-01-01/missing.html'))
    make_media_file(work_dir, 'chat/2026-01-01/kept.jpg')

    assert client.post('/db_database_maintenance').status_code == 200

    download_mock.assert_called_once()
    files = download_mock.call_args.args[0]
    assert [(f['file_path'], f['dialog_id'], f['message_id']) for f in files] == [('chat/2026-01-01/missing.jpg', 1, 2)]


def test_maintenance_does_not_call_download_when_nothing_is_missing(client: TestClient, db_handler: DatabaseHandler,
                                                                    work_dir: Path, download_mock: MagicMock):
    """All files are on the disk: no download call"""
    add_message(db_handler, 1, 'chat', ('chat/2026-01-01/kept.jpg',))
    make_media_file(work_dir, 'chat/2026-01-01/kept.jpg')
    assert client.post('/db_database_maintenance').status_code == 200
    download_mock.assert_not_called()


def test_maintenance_reports_files_without_records_and_deletes_nothing(client: TestClient, db_handler: DatabaseHandler,
                                                                       work_dir: Path):
    """The local files without records are listed with sizes and totals (the names are escaped for HTML); the
    files, the directories and the files with records stay as they are"""
    add_message(db_handler, 1, 'chat', ('chat/2026-01-01/kept.jpg',))
    kept = make_media_file(work_dir, 'chat/2026-01-01/kept.jpg')
    orphan = make_media_file(work_dir, 'chat/2026-01-01/a&b.jpg', size=2048)
    video = make_media_file(work_dir, 'old/clip.mp4', size=3 * 2 ** 20)
    other = make_media_file(work_dir, 'chat/2026-01-01/notes.txt')  # not a synchronized extension
    empty_dir = work_dir / ProjectDirs.media_dir / 'empty'
    empty_dir.mkdir()

    assert client.post('/db_database_maintenance').status_code == 200

    lines = report()
    assert any('Local files without a record in the database: 2 (3.00 MB)' in line for line in lines)
    assert any('chat/2026-01-01/a&amp;b.jpg (2.0 KB)' in line for line in lines)
    assert any('old/clip.mp4 (3.00 MB)' in line for line in lines)
    assert not any('kept.jpg' in line or 'notes.txt' in line for line in lines)
    assert all(path.exists() for path in (kept, orphan, video, other, empty_dir))


def test_maintenance_without_orphan_files_reports_zero(client: TestClient, db_handler: DatabaseHandler,
                                                       work_dir: Path):
    """No files without records: the count is 0 and there are no size and no list"""
    add_message(db_handler, 1, 'chat', ('chat/2026-01-01/kept.jpg',))
    make_media_file(work_dir, 'chat/2026-01-01/kept.jpg')
    client.post('/db_database_maintenance')
    assert any(line.endswith('Local files without a record in the database: 0') for line in report())


def test_maintenance_cuts_long_orphan_list(client: TestClient, db_handler: DatabaseHandler, work_dir: Path):
    """More files than the limit: only the limit is listed, then '...'; the count in the header is the full one"""
    add_message(db_handler, 1, 'chat', ())
    total = GlobalConst.status_list_max_items + 5
    for number in range(total):
        make_media_file(work_dir, f'old/file_{number:03d}.jpg')

    client.post('/db_database_maintenance')

    lines = report()
    assert any(f'Local files without a record in the database: {total}' in line for line in lines)
    listed = [line for line in lines if 'old/file_' in line]
    assert len(listed) == GlobalConst.status_list_max_items
    assert 'old/file_000.jpg' in listed[0] and f'old/file_{GlobalConst.status_list_max_items - 1:03d}.jpg' in listed[-1]
    assert sum(line.endswith(' - ...') for line in lines) == 1


def test_maintenance_creates_database_backup(client: TestClient, db_handler: DatabaseHandler, work_dir: Path):
    """The backup file appears in `backup` next to the database and is a valid copy of it"""
    add_message(db_handler, 1, 'chat', ())
    assert client.post('/db_database_maintenance').status_code == 200

    backups = list((work_dir / ProjectDirs.data_base_dir / 'backup').glob(f'{ProjectDirs.data_base_file.stem}_*.db'))
    assert len(backups) == 1
    connection = sqlite3.connect(backups[0])
    try:
        assert connection.execute('SELECT COUNT(*) FROM message_groups').fetchone() == (1,)
    finally:
        connection.close()
    assert any('Database backup created' in line for line in report())
