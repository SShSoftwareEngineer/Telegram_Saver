"""
Tests of the database message routes: filters, details, export to HTML, deletion (with tags, the tag list refresh and
the rollback). The Telegram handler is a fake object, the database is real (a temporary SQLite file).
Тесты маршрутов сообщений базы данных: фильтры, детали, экспорт в HTML, удаление (с тегами, обновлением списка тегов и
откатом). Обработчик Telegram - заглушка, база данных - настоящая (временный файл SQLite).
"""

from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session
from configs.config import DialogTypes, FormCfg, GlobalConst, MessageFileTypes, ProjectDirs
from database_handler import (DatabaseHandler, DbCurrentState, DbDialog, DbFile, DbMessageGroup, DbMessageSortFilter,
                              DbTag, message_group_tag_links)

DIALOG_SELECT = FormCfg.db_message_filter['dialog_select']
CURR_TAGS = FormCfg.db_detail_tags['curr_message_tags']
ALL_TAGS = FormCfg.db_detail_tags['all_detail_tags']
CHECKBOX = FormCfg.db_checkbox_list['db_checkbox_list']


@pytest.fixture(autouse=True)
def fresh_state(db_handler: DatabaseHandler) -> None:
    """
    The filter and the current state are class attributes of the handler (shared between tests): give this test its own
    Фильтр и текущее состояние - атрибуты класса обработчика (общие для тестов): даем этому тесту собственные
    """
    db_handler.message_sort_filter = DbMessageSortFilter()
    db_handler.current_state = DbCurrentState()


def add_dialog(session: Session, dialog_id: int, title: str) -> None:
    """Adds a dialog / Добавляет диалог"""
    session.add(DbDialog(dialog_id=dialog_id, title=title, dialog_type_id=DialogTypes.CHANNEL.value))


def add_group(session: Session, number: int, dialog_id: int, text: str,  # pylint: disable=too-many-arguments,too-many-positional-arguments
              tags: tuple[str, ...] = (), file_names: tuple[str, ...] = ()) -> str:
    """Adds a message group with tags (the same name is the same tag) and image files; returns its ID
    Добавляет группу сообщений с тегами (одно имя - один тег) и файлами-изображениями; возвращает ее ID"""
    grouped_id = f'{dialog_id}_{number}'
    group = DbMessageGroup(grouped_id=grouped_id, date=datetime(2026, 1, number, 3, 4, 5), text=text,
                           truncated_text=text, files_report='', sender_id=7, dialog_id=dialog_id)
    for name in tags:
        group.tags.append(session.query(DbTag).filter_by(name=name).first() or DbTag(name=name))
    for name in file_names:
        group.files.append(DbFile(file_path=f'chat/{name}', message_id=number, size=10,
                                  file_type_id=MessageFileTypes.IMAGE.type_id))
    session.add(group)
    session.commit()
    return grouped_id


def checkbox(*grouped_ids: str) -> dict:
    """Form with the marked groups: the values carry the prefix the routes remove / Форма с отмеченными группами"""
    return {CHECKBOX: [f'{GlobalConst.select_in_database} {grouped_id}' for grouped_id in grouped_ids]}


# ----------------------------------------------------------------------------------------------------------------------
# Filters / Фильтры
# ----------------------------------------------------------------------------------------------------------------------

def test_apply_filters(client: TestClient, db_handler: DatabaseHandler):
    """The dialog (a repeated field) and the text filters: keys, counter, the list, the cleared details"""
    session = db_handler.session
    add_dialog(session, 1, 'First chat')
    add_dialog(session, 2, 'Second chat')
    add_group(session, 1, 1, 'alpha text')
    add_group(session, 2, 2, 'alpha other')
    add_group(session, 3, 2, 'beta text')
    db_handler.current_state.message_details = {'text': 'old'}
    db_handler.current_state.selected_message_group_id = '1_1'
    form = {DIALOG_SELECT: ['2'], FormCfg.db_message_filter['message_query']: 'alpha',
            FormCfg.db_message_filter['sorting_field']: '0', FormCfg.db_message_filter['sorting_order']: '0'}
    response = client.post('/db_message_apply_filters', data=form)

    assert response.status_code == 200
    data = response.json()
    assert set(data) == {'db_messages', 'db-messages-count', 'db_details', CURR_TAGS}
    assert data['db-messages-count'] == '(1)'
    assert data['db_details'] == '' and data[CURR_TAGS] == ''
    assert 'alpha other' in data['db_messages'] and 'alpha text' not in data['db_messages']
    assert [g.grouped_id for g in db_handler.current_state.message_group_list] == ['2_2']
    assert db_handler.current_state.message_details is None
    assert db_handler.current_state.selected_message_group_id == ''


def test_apply_filters_empty_form_shows_all(client: TestClient, db_handler: DatabaseHandler):
    """Absent fields give no filter (None, as `request.form.get` in Flask): all groups, the filter is reset"""
    session = db_handler.session
    add_dialog(session, 1, 'First chat')
    add_group(session, 1, 1, 'alpha')
    add_group(session, 2, 1, 'beta')
    client.post('/db_message_apply_filters', data={FormCfg.db_message_filter['message_query']: 'alpha'})
    assert len(db_handler.current_state.message_group_list) == 1
    response = client.post('/db_message_apply_filters')
    assert response.status_code == 200
    assert response.json()['db-messages-count'] == '(2)'


def test_apply_filters_by_tag(client: TestClient, db_handler: DatabaseHandler):
    """The tag filter takes the groups that have a matching tag"""
    session = db_handler.session
    add_dialog(session, 1, 'First chat')
    add_group(session, 1, 1, 'tagged', tags=('travel',))
    add_group(session, 2, 1, 'plain')
    response = client.post('/db_message_apply_filters', data={FormCfg.db_message_filter['tag_query']: 'trav'})
    assert response.json()['db-messages-count'] == '(1)'
    assert 'tagged' in response.json()['db_messages']


# ----------------------------------------------------------------------------------------------------------------------
# Details / Детали
# ----------------------------------------------------------------------------------------------------------------------

def test_details_with_tags(client: TestClient, db_handler: DatabaseHandler):
    """The details page, the tag select of the message and the selected group in the state"""
    session = db_handler.session
    add_dialog(session, 1, 'First chat')
    grouped_id = add_group(session, 1, 1, 'Detailed text', tags=('travel', 'food'))
    response = client.get(f'/db_details/{grouped_id}')

    assert response.status_code == 200
    data = response.json()
    assert set(data) == {'db_details', CURR_TAGS}
    assert 'Detailed text' in data['db_details']
    assert '>travel</option>' in data[CURR_TAGS] and '>food</option>' in data[CURR_TAGS]
    assert db_handler.current_state.selected_message_group_id == grouped_id
    assert db_handler.current_state.message_details['message_group_id'] == grouped_id


def test_details_without_tags(client: TestClient, db_handler: DatabaseHandler):
    """A message without tags: an empty tag select, no error (the tags are an empty list, not None)"""
    session = db_handler.session
    add_dialog(session, 1, 'First chat')
    grouped_id = add_group(session, 1, 1, 'No tags here')
    response = client.get(f'/db_details/{grouped_id}')
    assert response.status_code == 200
    assert response.json()[CURR_TAGS] == ''
    assert db_handler.current_state.message_details['tags'] == []


def test_details_of_missing_group_gives_500(error_client: TestClient):
    """An unknown group ID is an error 500 in JSON (as in Flask), not a crash of the server"""
    response = error_client.get('/db_details/1_999')
    assert response.status_code == 500
    assert 'error' in response.json()


# ----------------------------------------------------------------------------------------------------------------------
# Export / Экспорт
# ----------------------------------------------------------------------------------------------------------------------

def test_export_selected_messages(client: TestClient, db_handler: DatabaseHandler, work_dir: Path):
    """Two groups are exported: the HTML file, the copied existing file (the missing one is skipped), the unchecked
    boxes in the response"""
    session = db_handler.session
    add_dialog(session, 1, 'First chat')
    first = add_group(session, 1, 1, 'Exported one', tags=('travel',), file_names=('photo1.jpg',))
    second = add_group(session, 2, 1, 'Exported two', file_names=('missing.jpg',))
    add_group(session, 3, 1, 'Not exported')
    media_file = work_dir / ProjectDirs.media_dir / 'chat' / 'photo1.jpg'
    media_file.parent.mkdir(parents=True)
    media_file.write_bytes(b'image')

    response = client.post('/db_export_selected_message_to_html', data=checkbox(first, second))

    assert response.status_code == 200
    assert response.json() == {f'{GlobalConst.select_in_database} {first}': False,
                               f'{GlobalConst.select_in_database} {second}': False}
    export_dir = work_dir / ProjectDirs.export_dir
    html_files = list(export_dir.glob('* - 2 messages.html'))
    assert len(html_files) == 1
    html = html_files[0].read_text(encoding='utf-8')
    assert 'Exported one' in html and 'Exported two' in html and 'Not exported' not in html
    assert 'travel' in html and 'photo1.jpg' in html
    copied = [path for path in export_dir.rglob('*') if path.is_file() and path.suffix == '.jpg']
    assert [path.name for path in copied] == ['photo1.jpg']
    assert copied[0].read_bytes() == b'image'


def test_export_creates_export_folder_without_files(client: TestClient, db_handler: DatabaseHandler, work_dir: Path):
    """Messages without files: the export folder does not exist yet and is created for the HTML file"""
    session = db_handler.session
    add_dialog(session, 1, 'First chat')
    grouped_id = add_group(session, 1, 1, 'Only text')
    assert not (work_dir / ProjectDirs.export_dir).exists()
    response = client.post('/db_export_selected_message_to_html', data=checkbox(grouped_id))
    assert response.status_code == 200
    assert len(list((work_dir / ProjectDirs.export_dir).glob('* - 1 messages.html'))) == 1


def test_export_nothing_selected(client: TestClient, work_dir: Path):
    """Without marked messages: an empty JSON and no files"""
    response = client.post('/db_export_selected_message_to_html')
    assert response.status_code == 200
    assert response.json() == {}
    assert not (work_dir / ProjectDirs.export_dir).exists()


# ----------------------------------------------------------------------------------------------------------------------
# Deletion / Удаление
# ----------------------------------------------------------------------------------------------------------------------

@pytest.fixture
def two_groups(db_handler: DatabaseHandler) -> tuple[str, str]:
    """The first group (dialog 1) has the tags 'only-first' and 'shared' and a file, the second (dialog 2) has the
    tag 'shared' / Первая группа (диалог 1): теги 'only-first' и 'shared' и файл, вторая (диалог 2): тег 'shared'"""
    session = db_handler.session
    add_dialog(session, 1, 'First chat')
    add_dialog(session, 2, 'Second chat')
    first = add_group(session, 1, 1, 'First', tags=('only-first', 'shared'), file_names=('photo1.jpg',))
    second = add_group(session, 2, 2, 'Second', tags=('shared',))
    db_handler.all_tags_list = db_handler.get_all_tag_list()
    return first, second


def test_delete_selected_group_with_tags(client: TestClient, db_handler: DatabaseHandler,
                                         two_groups: tuple[str, str]):
    """A group with tags is deleted (a bulk DELETE fails on the tag links): its files and links go too, the tag that
    is left without messages disappears, the dialog without messages disappears, the response refreshes the lists"""
    first, second = two_groups
    db_handler.current_state.message_details = {'text': 'old'}
    db_handler.current_state.selected_message_group_id = first
    response = client.post('/db_delete_selected_from_database', data=checkbox(first))

    assert response.status_code == 200
    data = response.json()
    assert set(data) == {'db_messages', 'db-messages-count', 'db_details', CURR_TAGS, ALL_TAGS, DIALOG_SELECT}
    assert data['db-messages-count'] == '(1)'
    assert data['db_details'] == '' and data[CURR_TAGS] == ''
    assert 'Second' in data['db_messages'] and 'First' not in data['db_messages']
    # The database / База данных
    session = db_handler.session
    assert [g.grouped_id for g in session.query(DbMessageGroup)] == [second]
    assert session.query(DbFile).count() == 0
    assert session.execute(select(message_group_tag_links.c.message_group_id)).scalars().all() == [second]
    assert [tag.name for tag in session.query(DbTag)] == ['shared']
    # The lists in the response and in the state / Списки в ответе и в состоянии
    assert '>shared</option>' in data[ALL_TAGS] and 'only-first' not in data[ALL_TAGS]
    assert [tag.name for tag in db_handler.all_tags_list or []] == ['shared']
    assert '>Second chat</option>' in data[DIALOG_SELECT] and 'First chat' not in data[DIALOG_SELECT]
    assert [d.dialog_id for d in db_handler.current_state.dialog_list] == [2]
    assert db_handler.current_state.message_details is None
    assert db_handler.current_state.selected_message_group_id == ''


def test_delete_nothing_selected(client: TestClient, db_handler: DatabaseHandler, two_groups: tuple[str, str]):
    """Without marked messages nothing is deleted"""
    response = client.post('/db_delete_selected_from_database')
    assert response.status_code == 200
    assert response.json()['db-messages-count'] == '(2)'
    assert db_handler.session.query(DbMessageGroup).count() == 2
    assert db_handler.session.query(DbTag).count() == 2


def test_delete_error_rolls_back_everything(error_client: TestClient, db_handler: DatabaseHandler,
                                            two_groups: tuple[str, str], monkeypatch: pytest.MonkeyPatch):
    """An error on the second group: 500 in JSON, the first deletion is rolled back (one transaction), the session
    is usable afterwards (the lock is free)"""
    session = db_handler.session
    real_delete = session.delete
    calls = MagicMock(side_effect=[None, RuntimeError('delete failed')])

    def failing_delete(instance):
        calls()  # the first call passes, the second raises / первый вызов проходит, второй падает
        real_delete(instance)

    monkeypatch.setattr(session, 'delete', failing_delete)
    response = error_client.post('/db_delete_selected_from_database', data=checkbox(*two_groups))

    assert response.status_code == 500
    assert response.json() == {'error': 'RuntimeError: delete failed'}
    assert session.query(DbMessageGroup).count() == 2
    assert session.query(DbFile).count() == 1
    # The next request works / Следующий запрос работает
    monkeypatch.setattr(session, 'delete', real_delete)
    assert error_client.post('/db_delete_selected_from_database', data=checkbox(*two_groups)).status_code == 200
    assert session.query(DbMessageGroup).count() == 0
