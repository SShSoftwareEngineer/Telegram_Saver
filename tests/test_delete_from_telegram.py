"""
Tests of deleting messages from "Saved Messages" in Telegram (F13): `TelegramHandler.delete_messages`, the route
`/tg_delete_selected_messages`, the check-boxes of the saved groups and the button. Telegram is a fake object.
Тесты удаления сообщений из «Избранного» в Telegram (F13): `TelegramHandler.delete_messages`, роут
`/tg_delete_selected_messages`, чек-боксы сохраненных групп и кнопка. Telegram - заглушка.
"""

import re
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
import pytest
from fastapi.testclient import TestClient
from config import FormCfg, GlobalConst
from database_handler import DatabaseHandler
import web.routers.telegram as telegram_routes
from telegram_handler import TelegramHandler, TgMessageGroup
from utils import ChatSource

ME = 1
CHECKBOX = FormCfg.tg_checkbox_list['tg_checkbox_list']


def make_group(number: int, dialog_id: int = ME, ids: tuple[int, ...] = (), saved: bool = False,
               source: ChatSource | None = None) -> TgMessageGroup:
    """Message group of the dialog; an album has several message IDs / Группа сообщений; у альбома несколько ID"""
    group = TgMessageGroup(f'{dialog_id}_{number}', dialog_id)
    group.date = datetime(2026, 1, number, 3, 4, 5)
    group.plain_text = f'Message {number}'
    group.ids = list(ids or (number,))
    group.saved_to_db = saved
    if source:
        group.source_chat_id, group.source_chat_title = source.chat_id, source.title
    return group


def form(*groups: TgMessageGroup) -> dict:
    """Form with the marked groups / Форма с отмеченными группами"""
    return {CHECKBOX: [f'{GlobalConst.select_in_telegram}{group.grouped_id}' for group in groups]}


@pytest.fixture
def favorites(tg_handler: SimpleNamespace) -> list[TgMessageGroup]:
    """The open "Saved Messages" with 3 groups (the second is an album); the fake Telegram deletes the messages
    and the list is read again without them / Открытое «Избранное» с тремя группами (вторая - альбом)"""
    groups = [make_group(1), make_group(2, ids=(20, 21, 22)), make_group(3, saved=True)]
    tg_handler.current_state.selected_dialog_id = ME
    tg_handler.current_state.message_group_list = list(groups)
    tg_handler.delete_messages = MagicMock(return_value=0)

    def reload(_dialog_id: int) -> list[TgMessageGroup]:
        deleted = {i for call in tg_handler.delete_messages.call_args_list for i in call.args[1]}
        return [group for group in groups if not set(group.ids) & deleted]

    tg_handler.get_message_group_list = MagicMock(side_effect=reload)
    return groups


def test_handler_deletes_the_messages_of_saved_messages():
    """The messages go to `client.delete_messages`, the result is the number deleted by Telegram"""
    client = SimpleNamespace(delete_messages=AsyncMock(return_value=[SimpleNamespace(pts_count=2),
                                                                      SimpleNamespace(pts_count=1)]))
    handler = SimpleNamespace(me=SimpleNamespace(id=ME), client=client, get_entity=lambda dialog_id: f'entity {dialog_id}',
                              _run=lambda coro: __import__('asyncio').run(coro))
    assert TelegramHandler.delete_messages(handler, ME, [5, 6, 7]) == 3  # type: ignore[arg-type]
    client.delete_messages.assert_awaited_once_with(f'entity {ME}', [5, 6, 7])


def test_handler_refuses_other_chats():
    """Only the own chat of the account: nothing is sent to Telegram for another chat"""
    client = SimpleNamespace(delete_messages=AsyncMock())
    handler = SimpleNamespace(me=SimpleNamespace(id=ME), client=client)
    with pytest.raises(PermissionError):
        TelegramHandler.delete_messages(handler, -1001, [5])  # type: ignore[arg-type]
    client.delete_messages.assert_not_called()


def test_route_deletes_all_messages_of_the_marked_groups(client: TestClient, tg_handler: SimpleNamespace,
                                                         favorites: list[TgMessageGroup]):
    """The album goes entirely, a saved group can be deleted too; the list is read again, the details are cleared"""
    tg_handler.current_state.message_details = {'some': 'details'}
    response = client.post('/tg_delete_selected_messages', data=form(favorites[1], favorites[2]))

    assert response.status_code == 200
    tg_handler.delete_messages.assert_called_once_with(ME, [20, 21, 22, 3])
    data = response.ui()
    assert set(data) == {'tg_messages', 'tg-messages-count', 'tg_source_filter', 'tg_details'}
    assert data['tg-messages-count'] == '(1)'
    assert data['tg_details'] == ''
    assert 'Message 1' in data['tg_messages'] and 'Message 2' not in data['tg_messages']
    assert tg_handler.current_state.message_details is None
    assert [group.grouped_id for group in tg_handler.current_state.message_group_list] == [favorites[0].grouped_id]


def test_route_keeps_the_copies_in_the_database(client: TestClient, db_handler: DatabaseHandler,
                                                tg_handler: SimpleNamespace, favorites: list[TgMessageGroup]):
    """The deleted saved group is not saved again and the database is not touched by the deletion"""
    from database_handler import DbDialog, DbMessageGroup
    saved = favorites[2]
    db_handler.session.add(DbDialog(dialog_id=ME, title='Saved Messages', dialog_type_id=1))
    db_handler.session.add(DbMessageGroup(grouped_id=saved.grouped_id, date=saved.date, html='', plain_text='',
                                          truncated_text='', sender_id=1, dialog_id=ME))
    db_handler.session.commit()
    client.post('/tg_delete_selected_messages', data=form(saved))
    assert db_handler.message_group_exists(saved.grouped_id)


def test_route_does_nothing_without_marked_groups(client: TestClient, tg_handler: SimpleNamespace,
                                                  favorites: list[TgMessageGroup]):
    """Nothing is marked (or the mark is of an unknown group): nothing is deleted, the page is not changed"""
    for data in ({}, {CHECKBOX: [f'{GlobalConst.select_in_telegram}1_999']}):
        response = client.post('/tg_delete_selected_messages', data=data)
        assert response.status_code == 200 and response.ui() == {}
    tg_handler.delete_messages.assert_not_called()


def test_route_refuses_other_chats(client: TestClient, tg_handler: SimpleNamespace, favorites: list[TgMessageGroup]):
    """In another chat (also with a stale form) nothing is deleted: 403 with the reason for the status bar"""
    tg_handler.current_state.selected_dialog_id = -1001
    response = client.post('/tg_delete_selected_messages', data=form(favorites[0]))
    assert response.status_code == 403
    assert 'Saved Messages' in response.json()['error']
    tg_handler.delete_messages.assert_not_called()


def test_route_drops_the_source_filter_of_the_vanished_source(client: TestClient, tg_handler: SimpleNamespace,
                                                              favorites: list[TgMessageGroup]):
    """The chosen source is gone with the deleted messages: the filter is reset, so the list is not empty"""
    source = ChatSource(-1001, 'Channel')
    favorites[0].source_chat_id, favorites[0].source_chat_title = source.chat_id, source.title
    tg_handler.message_sort_filter.selected_source_list = [source.key]
    tg_handler.current_state.source_chat_list = [source]

    def reload(_dialog_id: int) -> list[TgMessageGroup]:
        left = [group for group in favorites if group is not favorites[0]]
        keys = {group.source.key for group in left if group.source}
        tg_handler.current_state.source_chat_list = [x for x in [source] if x.key in keys]
        selected = tg_handler.message_sort_filter.selected_source_list
        return [group for group in left if not selected or (group.source and group.source.key in selected)]

    tg_handler.get_message_group_list = MagicMock(side_effect=reload)
    response = client.post('/tg_delete_selected_messages', data=form(favorites[0]))
    assert response.status_code == 200
    assert tg_handler.message_sort_filter.selected_source_list is None
    assert response.ui()['tg-messages-count'] == '(2)'


def test_saved_groups_have_a_checkbox_only_in_saved_messages(client: TestClient, tg_handler: SimpleNamespace):
    """In "Saved Messages" a saved group has a check-box (marked `data-saved`) next to the mark; elsewhere not"""
    tg_handler.current_state.selected_dialog_id = ME
    tg_handler.current_state.message_group_list = [make_group(1, saved=True), make_group(2)]
    html = client.get('/').text
    assert html.count('class="tg-message-checkbox"') == 2 and html.count('data-saved="1"') == 1
    tg_handler.current_state.message_group_list = [make_group(1, dialog_id=-1001, saved=True)]
    html = client.get('/').text
    assert 'data-saved' not in html and 'class="tg-message-checkbox"' not in html


def test_marked_saved_group_is_not_saved_again(client: TestClient, tg_handler: SimpleNamespace,
                                               db_handler: DatabaseHandler):
    """The save button skips the groups that are saved already (they have a check-box only for the deletion)"""
    group = make_group(1, saved=True)
    tg_handler.current_state.message_group_list = [group]
    tg_handler.get_dialog_by_id = MagicMock()
    response = client.post('/tg_save_selected_message_to_db', data=form(group))
    assert response.status_code == 200
    tg_handler.get_dialog_by_id.assert_not_called()


def test_action_bar_has_the_radio_buttons_and_do_it(client: TestClient):
    """Save is the default action; the deleting ones start disabled (no "Saved Messages" open); one button 'Do it'"""
    page = client.get('/').text
    radios = re.findall(r'<input type="radio"[^>]*name="tg_action_mode"[^>]*>', page)
    assert [re.search(r'value="(\w+)"', tag).group(1) for tag in radios] == ['save', 'delete', 'save_delete']
    assert 'checked' in radios[0] and 'disabled' not in radios[0]
    assert all('disabled' in tag and 'checked' not in tag for tag in radios[1:])
    assert page.count('doTgAction(') == 1 and 'Do it' in page
    assert 'Save selection to database' not in page and 'Delete selection from Telegram' not in page


def test_favorites_checkboxes_have_no_label_and_the_list_has_the_marker(client: TestClient, tg_handler: SimpleNamespace):
    """"Saved Messages": no "Save" label, tooltips (saved: "Delete"), the list marks itself for `syncTgActionModes`;
    other chats keep the label and have no marker"""
    tg_handler.current_state.message_group_list = [make_group(1, saved=True), make_group(2)]
    page = client.get('/').text
    assert 'data-favorites="1"' in page and 'title="Delete"' in page and 'title="Save / Delete"' in page
    assert '<label for="select_in_telegram' not in page
    tg_handler.current_state.message_group_list = [make_group(2, dialog_id=-1001)]
    page = client.get('/').text
    assert 'data-favorites="1"' not in page and '<label for="select_in_telegram' in page


def test_save_and_delete_saves_first_then_deletes(client: TestClient, tg_handler: SimpleNamespace,
                                                  db_handler: DatabaseHandler, favorites: list[TgMessageGroup],
                                                  monkeypatch: pytest.MonkeyPatch):
    """The saving goes before the deletion; the response has the lists of both steps"""
    calls: list[str] = []
    monkeypatch.setattr(telegram_routes, 'save_groups',
                        lambda request, ids: calls.append('save') or {'db_source_filter': 'FILTER'})
    tg_handler.delete_messages = MagicMock(side_effect=lambda *args: calls.append('delete') or 0)
    response = client.post('/tg_save_and_delete_selected_messages', data=form(favorites[0], favorites[1]))
    assert response.status_code == 200
    assert calls == ['save', 'delete']
    data = response.ui()
    assert data['db_source_filter'] == 'FILTER' and data['tg-messages-count'] == '(1)'
    tg_handler.delete_messages.assert_called_once_with(ME, [1, 20, 21, 22])


def test_save_and_delete_keeps_everything_when_saving_fails(client: TestClient, tg_handler: SimpleNamespace,
                                                            favorites: list[TgMessageGroup],
                                                            monkeypatch: pytest.MonkeyPatch):
    """A failure while saving stops before the deletion: nothing is deleted from Telegram"""
    def fail(request, ids):
        raise RuntimeError('disk full')
    monkeypatch.setattr(telegram_routes, 'save_groups', fail)
    with pytest.raises(RuntimeError):
        client.post('/tg_save_and_delete_selected_messages', data=form(favorites[0]))
    tg_handler.delete_messages.assert_not_called()


def test_save_and_delete_refuses_other_chats_before_saving(client: TestClient, tg_handler: SimpleNamespace,
                                                           favorites: list[TgMessageGroup],
                                                           monkeypatch: pytest.MonkeyPatch):
    """In another chat neither the saving nor the deletion happens"""
    saver = MagicMock(return_value={})
    monkeypatch.setattr(telegram_routes, 'save_groups', saver)
    tg_handler.current_state.selected_dialog_id = -1001
    response = client.post('/tg_save_and_delete_selected_messages', data=form(favorites[0]))
    assert response.status_code == 403
    saver.assert_not_called()
    tg_handler.delete_messages.assert_not_called()


def test_database_filters_redraw_the_source_select(client: TestClient, db_handler: DatabaseHandler):
    """Applying the filters returns the source select, so it shows the filter the list really has"""
    data = client.post('/db_message_apply_filters', data={}).ui()
    assert FormCfg.db_message_filter['source_filter'] in data
