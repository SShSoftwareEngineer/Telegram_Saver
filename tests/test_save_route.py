"""
Tests of `/tg_save_selected_message_to_db`: saving to the database and the file system, the transaction per message
group, the repeated form field. The Telegram handler is a fake object, file downloading is a mock, the database is real.
Тесты `/tg_save_selected_message_to_db`: сохранение в БД и файловую систему, транзакция на группу сообщений, повторяющееся
поле формы. Обработчик Telegram - заглушка, скачивание файлов - мок, база данных - настоящая.
"""

from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock
import pytest
from fastapi.testclient import TestClient
from configs.config import DialogTypes, FormCfg, GlobalConst, MessageFileTypes, ProjectDirs
from database_handler import DatabaseHandler, DbDialog, DbFile, DbMessageGroup
from telegram_handler import TgFile, TgMessageGroup

DIALOG_ID = -1001234567891
CHECKBOX = FormCfg.tg_checkbox_list['tg_checkbox_list']
DIALOG_SELECT = FormCfg.db_message_filter['dialog_select']


@pytest.fixture
def tg_dialog(tg_handler: SimpleNamespace) -> SimpleNamespace:
    """Fake Telegram dialog that `get_dialog_by_id` returns / Заглушка диалога, которую возвращает get_dialog_by_id"""
    dialog = SimpleNamespace(dialog_id=DIALOG_ID, title='Test chat', type=DialogTypes.CHANNEL,
                             get_self_dir=lambda: 'Test chat_1001234567891')
    tg_handler.get_dialog_by_id = MagicMock(return_value=dialog)
    tg_handler.download_message_file = MagicMock(return_value='downloaded')
    return dialog


def make_group(number: int, with_file: bool = True) -> TgMessageGroup:
    """Real message group (with a real image file object) of the fake dialog / Группа сообщений с файлом-изображением"""
    group = TgMessageGroup(f'{DIALOG_ID}_{number}', DIALOG_ID)
    group.date = datetime(2026, 1, number, 3, 4, 5)
    group.text = f'Message {number}\nsecond line'
    group.truncated_text = f'Message {number}'
    group.sender_id = 7
    group.files_report = '1 photo'
    if with_file:
        group.files.append(TgFile(DIALOG_ID, group.grouped_id, None, number, '', f'photo{number}.jpg',  # type: ignore[arg-type]
                                  f'chat/photo{number}.jpg', 'Image', 100 + number, MessageFileTypes.IMAGE))
    return group


def checkbox(*groups: TgMessageGroup) -> dict:
    """Form with the marked groups: the values carry the prefix the route removes / Форма с отмеченными группами"""
    return {CHECKBOX: [f'{GlobalConst.select_in_telegram}{group.grouped_id}' for group in groups]}


def test_save_selected_groups(client: TestClient, tg_handler: SimpleNamespace, tg_dialog: SimpleNamespace,
                              db_handler: DatabaseHandler, work_dir: Path):
    """Two of three groups (the repeated field) are saved: database, HTML files, flags, JSON keys"""
    groups = [make_group(1), make_group(2), make_group(3)]
    tg_handler.current_state.message_group_list = groups
    response = client.post('/tg_save_selected_message_to_db', data=checkbox(groups[0], groups[2]))

    assert response.status_code == 200
    data = response.json()
    assert set(data) == {'tg_messages', 'tg-messages-count', DIALOG_SELECT}
    assert data['tg-messages-count'] == '(3)'
    assert f'<option value="{DIALOG_ID}" >Test chat</option>' in data[DIALOG_SELECT]
    # The database: the dialog, two groups, for each an image and an HTML file / База данных: диалог, две группы, файлы
    session = db_handler.session
    assert session.query(DbDialog).filter_by(dialog_id=DIALOG_ID).one().title == 'Test chat'
    assert {g.grouped_id for g in session.query(DbMessageGroup)} == {groups[0].grouped_id, groups[2].grouped_id}
    saved = session.query(DbMessageGroup).filter_by(grouped_id=groups[0].grouped_id).one()
    assert (saved.text, saved.sender_id, saved.dialog.title) == ('Message 1\nsecond line', 7, 'Test chat')
    assert sorted(f.file_type_id for f in saved.files) == sorted(
        [MessageFileTypes.IMAGE.type_id, MessageFileTypes.CONTENT.type_id])
    # The HTML file is in the file system and in the database / HTML файл есть в файловой системе и в базе данных
    html_record = next(f for f in saved.files if f.file_type_id == MessageFileTypes.CONTENT.type_id)
    # The path is relative to the media directory, like the paths of the other files / Путь относительно директории медиа
    assert not html_record.file_path.startswith(ProjectDirs.media_dir)
    html_path = work_dir / ProjectDirs.media_dir / html_record.file_path
    assert html_path.parent == work_dir / ProjectDirs.media_dir / 'Test chat_1001234567891' / '2026-01-01'
    html = html_path.read_text(encoding='utf-8')
    assert html_record.size == len(html.encode('utf-8'))
    assert 'Message 1<br>second line' in html and 'src="photo1.jpg"' in html
    # Files are downloaded for the selected groups only; the flags follow the database
    # Файлы скачиваются только для выбранных групп; признаки сохранения соответствуют базе данных
    assert tg_handler.download_message_file.call_count == 2
    assert [g.saved_to_db for g in groups] == [True, False, True]


def test_save_nothing_selected(client: TestClient, tg_handler: SimpleNamespace, tg_dialog: SimpleNamespace,
                               db_handler: DatabaseHandler, monkeypatch: pytest.MonkeyPatch):
    """Without marked groups nothing is saved or downloaded, the database lists and the flags are not touched
    (as in Flask), the response keys are the same / Без отметок ничего не сохраняется и состояние не меняется"""
    group = make_group(1)
    group.saved_to_db = True  # the database is empty: a flag refresh would reset it / БД пуста: пересчет сбросил бы
    tg_handler.current_state.message_group_list = [group]
    get_dialog_list = MagicMock()
    monkeypatch.setattr(db_handler, 'get_dialog_list', get_dialog_list)
    response = client.post('/tg_save_selected_message_to_db')
    assert response.status_code == 200
    assert set(response.json()) == {'tg_messages', 'tg-messages-count', DIALOG_SELECT}
    assert db_handler.session.query(DbMessageGroup).count() == 0
    tg_handler.download_message_file.assert_not_called()
    get_dialog_list.assert_not_called()
    assert group.saved_to_db is True


def test_save_before_any_dialog_is_opened(client: TestClient, tg_handler: SimpleNamespace,
                                          db_handler: DatabaseHandler):
    """The message list is None until a dialog is opened: an empty JSON and no error (Flask gave 500)"""
    assert tg_handler.current_state.message_group_list is None
    response = client.post('/tg_save_selected_message_to_db')
    assert response.status_code == 200
    assert response.json() == {}
    assert db_handler.session.query(DbMessageGroup).count() == 0


def test_save_refreshes_saved_flags(client: TestClient, tg_handler: SimpleNamespace, tg_dialog: SimpleNamespace):
    """The flags of unmarked groups are re-read from the database, so a group saved earlier is marked as saved"""
    first, second = make_group(1), make_group(2)
    tg_handler.current_state.message_group_list = [first, second]
    client.post('/tg_save_selected_message_to_db', data=checkbox(first))
    assert (first.saved_to_db, second.saved_to_db) == (True, False)
    # A stale flag: the group is in the database but the list says otherwise / Устаревший признак
    second.saved_to_db = False
    first.saved_to_db = False
    client.post('/tg_save_selected_message_to_db', data=checkbox(second))
    assert (first.saved_to_db, second.saved_to_db) == (True, True)


def test_save_resaves_group_without_duplicates(client: TestClient, tg_handler: SimpleNamespace,
                                               tg_dialog: SimpleNamespace, db_handler: DatabaseHandler):
    """Saving the same group again updates the records (upsert), it does not duplicate them / Повтор без дубликатов"""
    group = make_group(1)
    tg_handler.current_state.message_group_list = [group]
    for _ in range(2):
        assert client.post('/tg_save_selected_message_to_db', data=checkbox(group)).status_code == 200
    assert db_handler.session.query(DbMessageGroup).count() == 1
    assert db_handler.session.query(DbFile).count() == 2


def test_save_error_rolls_back_only_failed_group(error_client: TestClient, tg_handler: SimpleNamespace,
                                                 tg_dialog: SimpleNamespace, db_handler: DatabaseHandler):
    """An error on the second group: 500 in JSON, the first group stays saved, the second is rolled back, the
    session is usable (the lock is free) / Ошибка на второй группе: первая сохранена, вторая откатана"""
    groups = [make_group(1), make_group(2)]
    tg_handler.current_state.message_group_list = groups
    tg_handler.download_message_file.side_effect = [True, RuntimeError('download failed')]
    response = error_client.post('/tg_save_selected_message_to_db', data=checkbox(*groups))

    assert response.status_code == 500
    assert response.json() == {'error': 'RuntimeError: download failed'}
    assert [g.grouped_id for g in db_handler.session.query(DbMessageGroup)] == [groups[0].grouped_id]
    assert db_handler.session.query(DbFile).filter_by(grouped_id=groups[1].grouped_id).count() == 0
    assert groups[0].saved_to_db is True and groups[1].saved_to_db is False
    # The next request works / Следующий запрос работает
    tg_handler.download_message_file.side_effect = None
    assert error_client.post('/tg_save_selected_message_to_db', data=checkbox(groups[1])).status_code == 200
    assert db_handler.session.query(DbMessageGroup).count() == 2


def test_saved_message_is_deleted_with_its_html_and_empty_directories(
        client: TestClient, tg_handler: SimpleNamespace, tg_dialog: SimpleNamespace, work_dir: Path):
    """The HTML file path is relative to the media directory, so deleting the message removes the HTML file and the
    directories left empty (the dialog and date directories); the media directory stays
    Путь HTML файла относительный к директории медиа, поэтому удаление сообщения удаляет HTML файл и оставшиеся пустыми
    директории (диалога и даты); директория медиа остается"""
    group = make_group(1, with_file=False)
    tg_handler.current_state.message_group_list = [group]
    assert client.post('/tg_save_selected_message_to_db', data=checkbox(group)).status_code == 200
    media_dir = work_dir / ProjectDirs.media_dir
    html_files = list(media_dir.rglob('*.html'))
    assert len(html_files) == 1
    response = client.post('/db_delete_selected_from_database', data={
        FormCfg.db_checkbox_list['db_checkbox_list']: [f'{GlobalConst.select_in_database}{group.grouped_id}']})
    assert response.status_code == 200
    assert not html_files[0].exists()
    assert media_dir.is_dir() and not any(media_dir.iterdir())
