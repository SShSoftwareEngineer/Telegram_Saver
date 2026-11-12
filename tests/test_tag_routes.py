"""
Tests of the tag routes: add, remove, update, update everywhere, sorting of all tags. The Telegram handler is a fake
object, the database is real (a temporary SQLite file).
Тесты маршрутов тегов: добавление, удаление, изменение, изменение везде, сортировка всех тегов. Обработчик Telegram -
заглушка, база данных - настоящая (временный файл SQLite).
"""

import pytest
from fastapi.testclient import TestClient
from configs.config import FormCfg
from database_handler import DatabaseHandler, DbCurrentState
from utils import status_messages
from test_tag_methods import add_group, all_tags, group_tags, option

CURR_TAGS = FormCfg.db_detail_tags['curr_message_tags']
ALL_TAGS = FormCfg.db_detail_tags['all_detail_tags']
EDIT_NAME = FormCfg.db_detail_tags['edit_tag_name']
OLD_NAME = FormCfg.db_detail_tags['old_tag_name']
SORTING = FormCfg.db_detail_tags['tag_sorting_field']
NO_MESSAGE = 'No message selected. Select a message first.'


@pytest.fixture(autouse=True)
def fresh_state(db_handler: DatabaseHandler) -> None:
    """
    The current state is a class attribute of the handler (shared between tests): give this test its own
    Текущее состояние - атрибут класса обработчика (общий для тестов): даем этому тесту собственное
    """
    db_handler.current_state = DbCurrentState()


@pytest.fixture(name='selected')
def selected_group(db_handler: DatabaseHandler) -> str:
    """A group with the tag 'old' that is open in the details / Группа с тегом 'old', открытая в деталях"""
    group_id = add_group(db_handler, 1, ('old',))
    db_handler.current_state.selected_message_group_id = group_id
    return group_id


def nothing_done(data: dict) -> bool:
    """Both tag lists are null: the page script skips them / Оба списка равны null: скрипт страницы их пропускает"""
    return data == {CURR_TAGS: None, ALL_TAGS: None}


# ----------------------------------------------------------------------------------------------------------------------
# Add and remove / Добавление и удаление
# ----------------------------------------------------------------------------------------------------------------------

def test_tag_add(client: TestClient, db_handler: DatabaseHandler, selected: str):
    """The tag is added to the selected message; the response carries both lists"""
    response = client.post('/db_tag_add', data={EDIT_NAME: 'new'})
    assert response.status_code == 200
    data = response.json()
    assert set(data) == {CURR_TAGS, ALL_TAGS}
    assert option('new') in data[CURR_TAGS] and option('old') in data[CURR_TAGS]
    assert option('new') in data[ALL_TAGS]
    assert group_tags(db_handler, selected) == ['new', 'old']
    assert [tag.name for tag in db_handler.all_tags_list] == ['new', 'old']


@pytest.mark.parametrize('form', [{}, {EDIT_NAME: ''}])
def test_tag_add_without_name(client: TestClient, db_handler: DatabaseHandler, selected: str, form: dict):
    """No tag name: nothing changes, both lists are null"""
    response = client.post('/db_tag_add', data=form)
    assert response.status_code == 200 and nothing_done(response.json())
    assert group_tags(db_handler, selected) == ['old']


def test_tag_remove(client: TestClient, db_handler: DatabaseHandler, selected: str):
    """The tag is removed from the message; a tag without messages disappears from the list of all tags"""
    response = client.post('/db_tag_remove', data={EDIT_NAME: 'old'})
    assert response.status_code == 200
    data = response.json()
    assert data[CURR_TAGS] == '' and option('old') not in data[ALL_TAGS]
    assert group_tags(db_handler, selected) == []
    assert all_tags(db_handler) == {}


def test_tag_remove_without_name(client: TestClient, selected: str):
    """No tag name: nothing is done"""
    response = client.post('/db_tag_remove', data={})
    assert nothing_done(response.json())


# ----------------------------------------------------------------------------------------------------------------------
# Update / Изменение
# ----------------------------------------------------------------------------------------------------------------------

def test_tag_update(client: TestClient, db_handler: DatabaseHandler, selected: str):
    """The tag is replaced on the selected message only"""
    other = add_group(db_handler, 2, ('old',))
    response = client.post('/db_tag_update', data={OLD_NAME: 'old', EDIT_NAME: 'new'})
    assert response.status_code == 200
    data = response.json()
    assert option('new') in data[CURR_TAGS] and option('old') not in data[CURR_TAGS]
    assert option('new') in data[ALL_TAGS] and option('old') in data[ALL_TAGS]
    assert group_tags(db_handler, selected) == ['new']
    assert group_tags(db_handler, other) == ['old']


@pytest.mark.parametrize('form', [{}, {OLD_NAME: 'old'}, {EDIT_NAME: 'new'}, {OLD_NAME: 'old', EDIT_NAME: 'old'},
                                  {OLD_NAME: '', EDIT_NAME: 'new'}])
def test_tag_update_incomplete_form(client: TestClient, db_handler: DatabaseHandler, selected: str, form: dict):
    """A missing or empty name, or the same name twice: nothing is done"""
    response = client.post('/db_tag_update', data=form)
    assert response.status_code == 200 and nothing_done(response.json())
    assert group_tags(db_handler, selected) == ['old']


def test_tag_update_everywhere(client: TestClient, db_handler: DatabaseHandler, selected: str):
    """The tag is renamed in all messages that have it"""
    other = add_group(db_handler, 2, ('old', 'food'))
    response = client.post('/db_tag_update_everywhere', data={OLD_NAME: 'old', EDIT_NAME: 'new'})
    assert response.status_code == 200
    data = response.json()
    assert option('new') in data[CURR_TAGS]
    assert option('new') in data[ALL_TAGS] and option('old') not in data[ALL_TAGS]
    assert group_tags(db_handler, selected) == ['new']
    assert group_tags(db_handler, other) == ['food', 'new']


def test_tag_update_everywhere_incomplete_form(client: TestClient, selected: str):
    """The same name twice: nothing is done"""
    response = client.post('/db_tag_update_everywhere', data={OLD_NAME: 'old', EDIT_NAME: 'old'})
    assert nothing_done(response.json())


# ----------------------------------------------------------------------------------------------------------------------
# No selected message / Сообщение не выбрано
# ----------------------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize('url, form', [
    ('/db_tag_add', {EDIT_NAME: 'new'}),
    ('/db_tag_remove', {EDIT_NAME: 'old'}),
    ('/db_tag_update', {OLD_NAME: 'old', EDIT_NAME: 'new'}),
    ('/db_tag_update_everywhere', {OLD_NAME: 'old', EDIT_NAME: 'new'}),
])
def test_no_selected_message(client: TestClient, db_handler: DatabaseHandler, url: str, form: dict):
    """The details are closed (empty ID): nothing is done, no error, the status bar says why"""
    group_id = add_group(db_handler, 1, ('old',))
    assert db_handler.current_state.selected_message_group_id == ''
    response = client.post(url, data=form)
    assert response.status_code == 200 and nothing_done(response.json())
    assert group_tags(db_handler, group_id) == ['old']
    assert any(NO_MESSAGE in report for report in status_messages.report_list or [])


def test_closed_details_reset_the_selection(client: TestClient, db_handler: DatabaseHandler, selected: str):
    """After the filters are applied the details are closed: the tag button does not act on the old message"""
    client.post('/db_message_apply_filters')
    assert db_handler.current_state.selected_message_group_id == ''
    response = client.post('/db_tag_add', data={EDIT_NAME: 'new'})
    assert nothing_done(response.json())
    assert group_tags(db_handler, selected) == ['old']


def test_unknown_selected_message(error_client: TestClient, db_handler: DatabaseHandler):
    """An ID of a message that does not exist: an error in JSON (500), the session is usable afterwards"""
    db_handler.current_state.selected_message_group_id = 'no_such_group'
    response = error_client.post('/db_tag_add', data={EDIT_NAME: 'new'})
    assert response.status_code == 500 and 'error' in response.json()
    assert error_client.post('/db_tag_all_sorting', data={SORTING: '0'}).status_code == 200


# ----------------------------------------------------------------------------------------------------------------------
# Sorting / Сортировка
# ----------------------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize('value, expected', [
    ('0', ['apple', 'banana', 'cherry']),        # by name / по имени
    ('1', ['banana', 'apple', 'cherry']),        # by usage count / по частоте использования
    (None, ['apple', 'banana', 'cherry']),       # no field: by name / нет поля: по имени
    ('9', ['apple', 'banana', 'cherry']),        # unknown value: by name / неизвестное значение: по имени
])
def test_tag_sorting(client: TestClient, db_handler: DatabaseHandler, value: str | None, expected: list[str]):
    """The order of the list of all tags follows the selected sorting"""
    add_group(db_handler, 1, ('banana', 'apple'))
    add_group(db_handler, 2, ('banana', 'cherry'))
    response = client.post('/db_tag_all_sorting', data={} if value is None else {SORTING: value})
    assert response.status_code == 200
    html = response.json()[ALL_TAGS]
    assert sorted(expected, key=html.index) == expected
    assert [tag.name for tag in db_handler.all_tags_list] == expected


def test_tag_sorting_by_last_update(client: TestClient, db_handler: DatabaseHandler):
    """Sorting by the last update: the response has all tags, the sorting is kept in the state"""
    add_group(db_handler, 1, ('first',))
    add_group(db_handler, 2, ('second',))
    response = client.post('/db_tag_all_sorting', data={SORTING: '2'})
    assert response.status_code == 200
    assert option('first') in response.json()[ALL_TAGS] and option('second') in response.json()[ALL_TAGS]
    assert db_handler.current_state.all_tags_list_sorting['field'] == 'updated_at'
