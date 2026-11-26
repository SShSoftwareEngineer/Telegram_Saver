"""
Tests of the tag routes: add, remove, update, update everywhere, sorting of all tags. The tag buttons act on the
messages checked in the list of the database tab, not on the message open in the details. The Telegram handler is a
fake object, the database is real (a temporary SQLite file).
Тесты маршрутов тегов: добавление, удаление, изменение, изменение везде, сортировка всех тегов. Кнопки тегов действуют
на сообщения, отмеченные в списке вкладки БД, а не на сообщение, открытое в деталях. Обработчик Telegram - заглушка,
база данных - настоящая (временный файл SQLite).
"""

import re
import pytest
from fastapi.testclient import TestClient
from config import FormCfg, GlobalConst
from database_handler import DatabaseHandler, DbCurrentState
from utils import status_messages
from test_tag_methods import add_group, all_tags, group_tags, option

CURR_TAGS = FormCfg.db_detail_tags['curr_message_tags']
ALL_TAGS = FormCfg.db_detail_tags['all_detail_tags']
EDIT_NAME = FormCfg.db_detail_tags['edit_tag_name']
OLD_NAME = FormCfg.db_detail_tags['old_tag_name']
SORTING = FormCfg.db_detail_tags['tag_sorting_field']
CHECKBOX = FormCfg.db_checkbox_list['db_checkbox_list']
NO_MESSAGES = 'No messages checked. Check the messages first.'


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


def box(grouped_id: str) -> str:
    """ID of the checkbox of a message group: the value the page sends and the key the response uses to uncheck it
    ID чек-бокса группы сообщений: значение, которое отправляет страница, и ключ, которым ответ снимает галочку"""
    return f'{GlobalConst.select_in_database} {grouped_id}'


def checked(*grouped_ids: str, **form) -> dict:
    """A form with the checked messages (the values carry the prefix the routes remove) and other fields
    Форма с отмеченными сообщениями (значения несут префикс, который роуты убирают) и другими полями"""
    fields = {'edit_name': EDIT_NAME, 'old_name': OLD_NAME}  # short names used in the tests / короткие имена в тестах
    return {CHECKBOX: [box(grouped_id) for grouped_id in grouped_ids],
            **{fields[key]: value for key, value in form.items()}}


def nothing_done(data: dict) -> bool:
    """The response has no tag lists (an empty update) / В ответе нет списков тегов (пустое обновление)"""
    return data == {}


def reported(text: str) -> bool:
    """The status bar has a report with the text / В строке статуса есть отчет с этим текстом"""
    return any(text in report for report in status_messages.report_list or [])


# ----------------------------------------------------------------------------------------------------------------------
# Add and remove / Добавление и удаление
# ----------------------------------------------------------------------------------------------------------------------

def test_tag_add_to_the_checked_messages(client: TestClient, db_handler: DatabaseHandler, selected: str):
    """The tag goes to all the checked messages and not to the unchecked one; the open message is among them, so its
    tag list is refreshed; the status bar says how many messages got the tag; the checked messages are unchecked
    when the operation is over (the response sets their checkboxes to False)"""
    second = add_group(db_handler, 2)
    third = add_group(db_handler, 3)
    response = client.post('/db_tag_add', data=checked(selected, second, edit_name='new'))
    assert response.status_code == 200
    data = response.ui()
    assert set(data) == {CURR_TAGS, ALL_TAGS, box(selected), box(second)}
    assert data[box(selected)] is False and data[box(second)] is False
    assert option('new') in data[CURR_TAGS] and option('old') in data[CURR_TAGS]
    assert option('new') in data[ALL_TAGS]
    assert group_tags(db_handler, selected) == ['new', 'old']
    assert group_tags(db_handler, second) == ['new']
    assert group_tags(db_handler, third) == []
    assert [tag.name for tag in db_handler.all_tags_list or []] == ['new', 'old']
    assert reported('Tag "new" added to 2 of 2 checked messages')


def test_open_message_is_not_the_target(client: TestClient, db_handler: DatabaseHandler, selected: str):
    """The message open in the details is not checked: it gets no tag, and its tag field is not touched"""
    second = add_group(db_handler, 2)
    response = client.post('/db_tag_add', data=checked(second, edit_name='new'))
    data = response.ui()
    assert CURR_TAGS not in data and option('new') in data[ALL_TAGS]
    assert group_tags(db_handler, selected) == ['old']
    assert group_tags(db_handler, second) == ['new']


def test_tags_work_with_closed_details(client: TestClient, db_handler: DatabaseHandler):
    """Closed details (no open message) do not matter: the checked messages get the tag, no tag field is returned"""
    first, second = add_group(db_handler, 1), add_group(db_handler, 2)
    assert db_handler.current_state.selected_message_group_id == ''
    data = client.post('/db_tag_add', data=checked(first, second, edit_name='new')).ui()
    assert CURR_TAGS not in data and option('new') in data[ALL_TAGS]
    assert group_tags(db_handler, first) == group_tags(db_handler, second) == ['new']


def test_closed_details_after_filters_do_not_matter(client: TestClient, db_handler: DatabaseHandler, selected: str):
    """After the filters are applied the details are closed; the checked messages still get the tag"""
    client.post('/db_message_apply_filters')
    assert db_handler.current_state.selected_message_group_id == ''
    client.post('/db_tag_add', data=checked(selected, edit_name='new'))
    assert group_tags(db_handler, selected) == ['new', 'old']


@pytest.mark.parametrize('form', [{}, {'edit_name': ''}])
def test_tag_add_without_name(client: TestClient, db_handler: DatabaseHandler, selected: str, form: dict):
    """No tag name: nothing changes, both lists are null"""
    response = client.post('/db_tag_add', data=checked(selected, **form))
    assert response.status_code == 200 and nothing_done(response.ui())
    assert group_tags(db_handler, selected) == ['old']


def test_tag_remove_from_the_checked_messages(client: TestClient, db_handler: DatabaseHandler, selected: str):
    """The tag is removed from the checked messages only; a tag without messages disappears from the list of all tags"""
    second = add_group(db_handler, 2, ('old',))
    third = add_group(db_handler, 3, ('old',))
    response = client.post('/db_tag_remove', data=checked(selected, second, edit_name='old'))
    assert response.status_code == 200
    data = response.ui()
    assert data[CURR_TAGS] == '' and option('old') in data[ALL_TAGS]  # the third message still has it
    assert data[box(selected)] is False and data[box(second)] is False and box(third) not in data
    assert group_tags(db_handler, selected) == group_tags(db_handler, second) == []
    assert group_tags(db_handler, third) == ['old']
    assert all_tags(db_handler) == {'old': 1}
    assert reported('Tag "old" removed from 2 of 2 checked messages')
    response = client.post('/db_tag_remove', data=checked(third, edit_name='old'))
    assert option('old') not in response.ui()[ALL_TAGS]
    assert all_tags(db_handler) == {}


def test_tag_remove_without_name(client: TestClient, selected: str):
    """No tag name: nothing is done"""
    response = client.post('/db_tag_remove', data=checked(selected))
    assert nothing_done(response.ui())


# ----------------------------------------------------------------------------------------------------------------------
# Update / Изменение
# ----------------------------------------------------------------------------------------------------------------------

def test_tag_update_in_the_checked_messages(client: TestClient, db_handler: DatabaseHandler, selected: str):
    """The tag is replaced in the checked messages that have it; the unchecked message and a checked one without the
    tag are left alone"""
    other = add_group(db_handler, 2, ('old',))
    without = add_group(db_handler, 3, ('food',))
    response = client.post('/db_tag_update', data=checked(selected, without, old_name='old', edit_name='new'))
    assert response.status_code == 200
    data = response.ui()
    assert option('new') in data[CURR_TAGS] and option('old') not in data[CURR_TAGS]
    assert option('new') in data[ALL_TAGS] and option('old') in data[ALL_TAGS]
    assert group_tags(db_handler, selected) == ['new']
    assert group_tags(db_handler, other) == ['old']
    assert group_tags(db_handler, without) == ['food']
    assert reported('Tag "old" changed to "new" in 1 of 2 checked messages')
    # Both checked messages are unchecked, also the one the tag was not changed in: the operation is over for them
    assert data[box(selected)] is False and data[box(without)] is False and box(other) not in data


@pytest.mark.parametrize('form', [{}, {'old_name': 'old'}, {'edit_name': 'new'},
                                  {'old_name': 'old', 'edit_name': 'old'}, {'old_name': '', 'edit_name': 'new'}])
def test_tag_update_incomplete_form(client: TestClient, db_handler: DatabaseHandler, selected: str, form: dict):
    """A missing or empty name, or the same name twice: nothing is done"""
    response = client.post('/db_tag_update', data=checked(selected, **form))
    assert response.status_code == 200 and nothing_done(response.ui())
    assert group_tags(db_handler, selected) == ['old']


def test_tag_update_everywhere(client: TestClient, db_handler: DatabaseHandler, selected: str):
    """The tag is renamed in all messages that have it, checked or not; the open message has it, so it is refreshed"""
    other = add_group(db_handler, 2, ('old', 'food'))
    response = client.post('/db_tag_update_everywhere', data=checked(old_name='old', edit_name='new'))
    assert response.status_code == 200
    data = response.ui()
    assert option('new') in data[CURR_TAGS]
    assert option('new') in data[ALL_TAGS] and option('old') not in data[ALL_TAGS]
    assert group_tags(db_handler, selected) == ['new']
    assert group_tags(db_handler, other) == ['food', 'new']
    assert reported('Tag "old" renamed to "new" in 2 messages')


def test_tag_update_everywhere_needs_nothing_checked_and_no_open_message(client: TestClient,
                                                                          db_handler: DatabaseHandler):
    """Renaming everywhere works with nothing checked and the details closed; no error, no tag field returned"""
    first, second = add_group(db_handler, 1, ('old',)), add_group(db_handler, 2, ('old',))
    assert db_handler.current_state.selected_message_group_id == ''
    data = client.post('/db_tag_update_everywhere', data={OLD_NAME: 'old', EDIT_NAME: 'new'}).ui()
    assert CURR_TAGS not in data and option('new') in data[ALL_TAGS]
    assert group_tags(db_handler, first) == group_tags(db_handler, second) == ['new']


def test_tag_update_everywhere_leaves_the_checks(client: TestClient, db_handler: DatabaseHandler, selected: str):
    """Renaming everywhere does not work on the checked messages, so their checkboxes are not touched"""
    second = add_group(db_handler, 2)
    form = checked(selected, second, old_name='old', edit_name='new')
    data = client.post('/db_tag_update_everywhere', data=form).ui()
    assert set(data) == {CURR_TAGS, ALL_TAGS}


def test_checks_stay_when_nothing_was_done(client: TestClient, db_handler: DatabaseHandler, selected: str):
    """No tag name, or an incomplete form: nothing is done, so the checkboxes stay checked (the response has no keys)"""
    cases: tuple[tuple[str, dict], ...] = (
        ('/db_tag_add', {}), ('/db_tag_remove', {'edit_name': ''}), ('/db_tag_update', {'edit_name': 'x'}))
    for url, form in cases:
        response = client.post(url, data=checked(selected, **form))
        assert nothing_done(response.ui())


def test_tag_update_everywhere_incomplete_form(client: TestClient, selected: str):
    """The same name twice: nothing is done"""
    response = client.post('/db_tag_update_everywhere', data=checked(old_name='old', edit_name='old'))
    assert nothing_done(response.ui())


# ----------------------------------------------------------------------------------------------------------------------
# No checked messages, unknown messages, errors / Нет отмеченных сообщений, неизвестные сообщения, ошибки
# ----------------------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize('url, form', [
    ('/db_tag_add', {'edit_name': 'new'}),
    ('/db_tag_remove', {'edit_name': 'old'}),
    ('/db_tag_update', {'old_name': 'old', 'edit_name': 'new'}),
])
@pytest.mark.parametrize('open_message', [True, False], ids=['details open', 'details closed'])
def test_no_checked_messages(client: TestClient, db_handler: DatabaseHandler, url: str, form: dict,
                             open_message: bool):
    """Nothing is checked: nothing is done (even with a message open in the details), no error, the status says why"""
    group_id = add_group(db_handler, 1, ('old',))
    if open_message:
        db_handler.current_state.selected_message_group_id = group_id
    response = client.post(url, data=checked(**form))
    assert response.status_code == 200 and nothing_done(response.ui())
    assert group_tags(db_handler, group_id) == ['old']
    assert reported(NO_MESSAGES)


def test_unknown_checked_messages_are_skipped(client: TestClient, db_handler: DatabaseHandler):
    """An ID of a message that does not exist (the page is not refreshed after a deletion) is skipped, no error"""
    group_id = add_group(db_handler, 1)
    response = client.post('/db_tag_add', data=checked(group_id, 'no_such_group', edit_name='new'))
    assert response.status_code == 200
    assert group_tags(db_handler, group_id) == ['new']
    assert reported('Tag "new" added to 1 of 2 checked messages')


def test_error_gives_json_500_and_the_session_stays_usable(error_client: TestClient, db_handler: DatabaseHandler,
                                                           monkeypatch: pytest.MonkeyPatch):
    """A failure while changing the tags: an error in JSON (500), nothing is changed, the next request works"""
    first, second = add_group(db_handler, 1), add_group(db_handler, 2)

    def boom(*_args):
        raise RuntimeError('boom')

    monkeypatch.setattr(DatabaseHandler, '_attach_tag', boom)
    response = error_client.post('/db_tag_add', data=checked(first, second, edit_name='new'))
    assert response.status_code == 500 and 'error' in response.json()
    assert group_tags(db_handler, first) == group_tags(db_handler, second) == []
    assert error_client.post('/db_tag_all_sorting', data={SORTING: '0'}).status_code == 200


# ----------------------------------------------------------------------------------------------------------------------
# The page / Страница
# ----------------------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize('url', ['/db_tag_add', '/db_tag_remove', '/db_tag_update', '/db_tag_update_everywhere'])
def test_tag_buttons_send_the_checked_messages(client: TestClient, url: str):
    """The configuration of every tag button has the checkboxes of the message list: the page sends the checked ones"""
    page = client.get('/').text
    match = re.search(rf'onclick="pressFormButton\(([^"]*?){url}\'', page)
    assert match, f'the button of {url} is not on the page'
    assert 'db-message-checkbox' in match.group(1)


def test_script_fires_change_when_a_response_unchecks_a_box(client: TestClient):
    """The page script fires `change` for a checkbox the response unchecks, so the counter of the checked messages
    ("2 / 10") is updated; setting `checked` from code does not do it"""
    script = client.get('/static/js/my_scripts.js').text
    assert "dispatchEvent(new Event('change'" in script


def test_tag_buttons_have_hints(client: TestClient):
    """The buttons say what they act on: the checked messages, or all messages for the rename everywhere"""
    page = client.get('/').text
    assert page.count('the checked messages') >= 3 and 'checked or not' in page


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
    html = response.ui()[ALL_TAGS]
    assert sorted(expected, key=html.index) == expected
    assert [tag.name for tag in db_handler.all_tags_list or []] == expected


def test_tag_sorting_by_last_update(client: TestClient, db_handler: DatabaseHandler):
    """Sorting by the last update: the response has all tags, the sorting is kept in the state"""
    add_group(db_handler, 1, ('first',))
    add_group(db_handler, 2, ('second',))
    response = client.post('/db_tag_all_sorting', data={SORTING: '2'})
    assert response.status_code == 200
    assert option('first') in response.ui()[ALL_TAGS] and option('second') in response.ui()[ALL_TAGS]
    assert db_handler.current_state.all_tags_list_sorting['field'] == 'created_at'
