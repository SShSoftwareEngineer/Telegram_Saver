"""
Tests of the source chat of the messages of "Saved Messages" (F12): the search of the chat in `fwd_from`, the titles, the
filter on the Telegram tab and on the database tab, saving to the database. Telegram is a fake object.
Тесты чата-источника сообщений «Избранного» (F12): определение чата по `fwd_from`, названия, фильтр на вкладке
Telegram и на вкладке БД, сохранение в БД. Telegram - заглушка.
"""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock
import pytest
from fastapi.testclient import TestClient
from telethon.tl.types import Chat, ChatPhotoEmpty, MessageFwdHeader, PeerChannel, PeerChat, PeerUser
from config import DialogTypes, FormCfg, GlobalConst
from database_handler import DatabaseHandler, DbDialog, DbMessageGroup, DbMessageSortFilter, DbCurrentState
from telegram_handler import TelegramHandler, TgCurrentState, TgMessageGroup, TgMessageSortFilter, get_message_source
from utils import ChatSource, split_source_keys

ME = 1000
CHANNEL = -1001234567891  # PeerChannel(1234567891) / ID канала с PeerChannel(1234567891)
TG_SOURCE = FormCfg.tg_message_filter['source_select']
DB_SOURCE = FormCfg.db_message_filter['source_select']
DB_SOURCE_FILTER = FormCfg.db_message_filter['source_filter']
DATE = datetime(2026, 1, 2, tzinfo=timezone.utc)


def fwd(**kwargs) -> MessageFwdHeader:
    """A real forward header of Telethon / Настоящий заголовок пересылки Telethon"""
    return MessageFwdHeader(date=DATE, **kwargs)


def make_message(message_id: int, header: MessageFwdHeader | None = None, text: str = 'Hi') -> SimpleNamespace:
    """Fake message of "Saved Messages": the sender is always the user / Заглушка сообщения «Избранного»"""
    return SimpleNamespace(id=message_id, grouped_id=None, sender_id=ME, from_id=None, raw_text=text, entities=None,
                           date=datetime(2026, 1, 2, 3, 4, message_id, tzinfo=timezone.utc), fwd_from=header)


# ----------------------------------------------------------------------------------------------------------------------
# The chat in `fwd_from` / Чат в `fwd_from`
# ----------------------------------------------------------------------------------------------------------------------

def test_source_is_saved_from_peer_first():
    """`saved_from_peer` (the chat) wins over the original author; a group and a channel get the marked IDs"""
    header = fwd(saved_from_peer=PeerChat(chat_id=555), from_id=PeerUser(user_id=42))
    assert get_message_source(make_message(1, header)) == (-555, '')  # type: ignore[arg-type]
    header = fwd(saved_from_peer=PeerChannel(channel_id=1234567891), from_id=PeerUser(user_id=42))
    assert get_message_source(make_message(1, header)) == (CHANNEL, '')  # type: ignore[arg-type]


def test_source_is_the_author_without_saved_from_peer():
    """Without `saved_from_peer` the original author is the source (a private chat: the same person)"""
    header = fwd(from_id=PeerUser(user_id=8837960131))
    assert get_message_source(make_message(1, header)) == (8837960131, '')  # type: ignore[arg-type]


def test_source_is_the_name_of_a_hidden_author():
    """An author who hides the account has only a name: no ID, the name is the title"""
    assert get_message_source(make_message(1, fwd(from_name=' Hidden Bob ')))[1:] == ('Hidden Bob',)  # type: ignore[arg-type]
    assert get_message_source(make_message(1, fwd(from_name='Bob')))[0] is None  # type: ignore[arg-type]


def test_source_of_a_message_that_is_not_forwarded():
    """A message the user wrote has no `fwd_from`: no source; a header without any data is no source too"""
    assert get_message_source(make_message(1)) == (None, '')  # type: ignore[arg-type]
    assert get_message_source(make_message(1, fwd())) == (None, '')  # type: ignore[arg-type]


def test_group_takes_the_source_only_when_asked_and_from_the_first_forwarded_message():
    """Other dialogs ignore the source; in "Saved Messages" an album takes it from the first message that has it"""
    other = TgMessageGroup('x_1', 1)
    other.add_message(make_message(1, fwd(saved_from_peer=PeerChat(chat_id=5))))  # type: ignore[arg-type]
    assert other.source is None
    album = TgMessageGroup('x_2', ME)
    album.add_message(make_message(1), with_source=True)  # type: ignore[arg-type]
    album.add_message(make_message(2, fwd(saved_from_peer=PeerChat(chat_id=5))), with_source=True)  # type: ignore[arg-type]
    album.add_message(make_message(3, fwd(saved_from_peer=PeerChat(chat_id=6))), with_source=True)  # type: ignore[arg-type]
    assert album.source_chat_id == -5 and album.source == ChatSource(-5, '')


def test_source_keys_and_options():
    """The key is the ID or `name:<name>`; the keys split back"""
    assert ChatSource(CHANNEL, 'News').key == str(CHANNEL)
    assert ChatSource(None, 'Bob').key == 'name:Bob'
    assert ChatSource(CHANNEL, '').label == f'Chat {CHANNEL}'
    assert split_source_keys([str(CHANNEL), 'name:Bob', 'junk', '7']) == ([CHANNEL, 7], ['Bob'])


# ----------------------------------------------------------------------------------------------------------------------
# The handler: titles, options, filter / Обработчик: названия, пункты, фильтр
# ----------------------------------------------------------------------------------------------------------------------

def make_handler(messages: list, entity_titles: dict[int, str] | None = None) -> TelegramHandler:
    """The real handler methods on a handler without a connection to Telegram / Методы обработчика без соединения"""
    handler = TelegramHandler.__new__(TelegramHandler)
    handler.me = SimpleNamespace(id=ME)  # type: ignore[assignment]
    handler.all_dialogues_list = [SimpleNamespace(dialog_id=-555, title='Family')]  # type: ignore[list-item]
    handler.message_sort_filter = TgMessageSortFilter()
    handler.current_state = TgCurrentState()
    handler._source_titles = {}  # pylint: disable=protected-access
    handler.get_message_list = lambda dialog_id: messages  # type: ignore[method-assign]
    handler.get_message_file_info = lambda *args: None  # type: ignore[method-assign]
    titles = entity_titles or {}

    def get_entity(entity_id: int) -> SimpleNamespace:
        if entity_id not in titles:
            raise ValueError('Could not find the input entity')
        # A real chat object: Telethon builds the display name from its type / Настоящий объект чата: имя по его типу
        return Chat(id=abs(entity_id), title=titles[entity_id], photo=ChatPhotoEmpty(), participants_count=1,
                    date=DATE, version=1)

    handler.get_entity = get_entity  # type: ignore[method-assign]
    return handler


@pytest.fixture
def forwarded_messages() -> list:
    """Saved messages: from a known group, twice from a channel, from an unknown user, hidden author, own"""
    return [make_message(1, fwd(saved_from_peer=PeerChat(chat_id=555))),
            make_message(2, fwd(saved_from_peer=PeerChannel(channel_id=1234567891))),
            make_message(3, fwd(saved_from_peer=PeerChannel(channel_id=1234567891))),
            make_message(4, fwd(from_id=PeerUser(user_id=77))),
            make_message(5, fwd(from_name='Hidden Bob')),
            make_message(6)]


def test_handler_finds_titles_and_builds_the_options(forwarded_messages: list):
    """The title is taken from the dialogs, else from Telegram, else it stays empty (the label shows the ID); the
    options are the different sources by title, own messages have no source"""
    handler = make_handler(forwarded_messages, {CHANNEL: 'News'})
    groups = handler.get_message_group_list(ME)
    by_message = {group.ids[0]: (group.source_chat_id, group.source_chat_title) for group in groups}
    assert by_message == {1: (-555, 'Family'), 2: (CHANNEL, 'News'), 3: (CHANNEL, 'News'), 4: (77, ''),
                          5: (None, 'Hidden Bob'), 6: (None, '')}
    # Newest forwarding first (as in Telegram), not by title / Сначала самые свежие пересылки (как в Telegram), не по названию
    assert [source.label for source in handler.current_state.source_chat_list] == [
        'Hidden Bob', 'Chat 77', 'News', 'Family']


def test_handler_filters_by_the_source_but_keeps_all_options(forwarded_messages: list):
    """The filter keeps the groups of the selected sources; the options stay the same (made before the filter)"""
    handler = make_handler(forwarded_messages, {CHANNEL: 'News'})
    handler.message_sort_filter.selected_source_list = [str(CHANNEL), 'name:Hidden Bob']
    groups = handler.get_message_group_list(ME)
    assert sorted(group.ids[0] for group in groups) == [2, 3, 5]
    assert len(handler.current_state.source_chat_list) == 4


def test_handler_ignores_the_source_in_other_dialogs(forwarded_messages: list):
    """Another dialog has no sources and no options, and the old filter does not hide its messages"""
    handler = make_handler(forwarded_messages)
    handler.message_sort_filter.selected_source_list = ['1']
    groups = handler.get_message_group_list(42)
    assert len(groups) == 6 and all(group.source is None for group in groups)
    assert handler.current_state.source_chat_list == []


def test_title_is_asked_once_and_a_failure_is_remembered(forwarded_messages: list):
    """A chat Telegram does not know gives an empty title without an error and is not asked again"""
    handler = make_handler(forwarded_messages)
    asked = MagicMock(side_effect=handler.get_entity)
    handler.get_entity = asked  # type: ignore[method-assign]
    handler.get_message_group_list(ME)
    handler.get_message_group_list(ME)
    assert sorted(call.args[0] for call in asked.call_args_list) == sorted([CHANNEL, 77])


def test_filter_resets_by_default():
    """The default filters have no source filter; an empty selection means no filter"""
    message_filter = TgMessageSortFilter()
    message_filter.selected_source_list = ['1']
    message_filter.set_default_filters()
    assert message_filter.selected_source_list is None
    message_filter.selected_source_list = []
    assert message_filter.selected_source_list is None


# ----------------------------------------------------------------------------------------------------------------------
# The Telegram routes / Маршруты Telegram
# ----------------------------------------------------------------------------------------------------------------------

def test_open_dialog_shows_the_filter_and_resets_the_selection(client: TestClient, tg_handler: SimpleNamespace):
    """The sources of "Saved Messages" are drawn as the filter (the title is escaped); a new dialog drops the old
    selection; a dialog without sources has no filter"""
    tg_handler.get_message_group_list.return_value = []
    tg_handler.message_sort_filter.selected_source_list = ['5']
    tg_handler.current_state.source_chat_list = [ChatSource(CHANNEL, '<i>News</i>'), ChatSource(None, 'Bob')]
    data = client.get(f'/tg_messages/{ME}').ui()
    assert tg_handler.message_sort_filter.selected_source_list is None
    assert f'id="{TG_SOURCE}"' in data['tg_source_filter'] and 'Bob' in data['tg_source_filter']
    assert '&lt;i&gt;News&lt;/i&gt;' in data['tg_source_filter']
    tg_handler.current_state.source_chat_list = []
    assert client.get('/tg_messages/42').ui()['tg_source_filter'].strip() == ''


def test_apply_filters_passes_the_selection_and_keeps_it(client: TestClient, tg_handler: SimpleNamespace):
    """The selected sources reach the filter and stay selected in the redrawn list"""
    tg_handler.current_state.selected_dialog_id = ME
    tg_handler.get_message_group_list.return_value = []
    tg_handler.current_state.source_chat_list = [ChatSource(CHANNEL, 'News'), ChatSource(None, 'Bob')]
    data = client.post('/tg_message_apply_filters', data={TG_SOURCE: 'name:Bob'}).ui()
    assert tg_handler.message_sort_filter.selected_source_list == ['name:Bob']
    assert data['tg_source_filter'].count(' selected') == 1 and 'value="name:Bob" selected' in data['tg_source_filter']
    # One line, not a multiple list; the first option drops the filter; a change applies the filters at once
    assert 'multiple' not in data['tg_source_filter'] and '<option value="">' in data['tg_source_filter']
    assert "'/tg_message_apply_filters'" in data['tg_source_filter'] and 'onchange=' in data['tg_source_filter']
    client.post('/tg_message_apply_filters', data={})
    assert tg_handler.message_sort_filter.selected_source_list is None


def test_dialog_filters_clear_the_source_filter(client: TestClient, tg_handler: SimpleNamespace):
    """A new list of chats clears the message list, so the filter by the source goes away with it"""
    tg_handler.current_state.source_chat_list = [ChatSource(1, 'x')]
    tg_handler.message_sort_filter.selected_source_list = ['1']
    tg_handler.get_dialog_list.return_value = []
    data = client.post('/tg_dialog_apply_filters', data={}).ui()
    assert data['tg_source_filter'] == '' and tg_handler.current_state.source_chat_list == []
    assert tg_handler.message_sort_filter.selected_source_list is None


# ----------------------------------------------------------------------------------------------------------------------
# The database / База данных
# ----------------------------------------------------------------------------------------------------------------------

def add_forwarded(db_handler: DatabaseHandler, number: int, chat_id: int | None, title: str | None) -> str:
    """Saves a message group of "Saved Messages" with the source / Сохраняет группу «Избранного» с источником"""
    session = db_handler.session
    if session.get(DbDialog, ME) is None:
        session.add(DbDialog(dialog_id=ME, title='Saved', dialog_type_id=DialogTypes.USER.value))
    grouped_id = f'{ME}_{number}'
    session.add(DbMessageGroup(grouped_id=grouped_id, date=datetime(2026, 1, number, 3, 4, 5), html='x', plain_text='x',
                               truncated_text='x', sender_id=ME, dialog_id=ME, source_chat_id=chat_id,
                               source_chat_title=title))
    session.commit()
    return grouped_id


@pytest.fixture
def forwarded_in_db(db_handler: DatabaseHandler, tg_handler: SimpleNamespace) -> list[str]:
    """The groups: two of the channel (renamed), one of a hidden author, one of an unknown chat, one own; the account
    of the user is the owner of "Saved Messages" (the source filter works only for it)"""
    tg_handler.me.id = ME
    db_handler.message_sort_filter = DbMessageSortFilter()
    db_handler.current_state = DbCurrentState()
    return [add_forwarded(db_handler, 1, CHANNEL, 'Old name'), add_forwarded(db_handler, 2, CHANNEL, 'News'),
            add_forwarded(db_handler, 3, None, 'Hidden Bob'), add_forwarded(db_handler, 4, 77, None),
            add_forwarded(db_handler, 5, None, None)]


def test_database_lists_the_sources(db_handler: DatabaseHandler, forwarded_in_db: list[str]):
    """Every source once, the newest title of a renamed chat, an unknown title shows the ID, own messages are not a
    source; the HTML options are escaped"""
    assert [(source.chat_id, source.title) for source in db_handler.get_source_list()] == [
        (77, ''), (None, 'Hidden Bob'), (CHANNEL, 'News')]
    assert [source.label for source in db_handler.get_source_list()] == ['Chat 77', 'Hidden Bob', 'News']


def test_database_sources_go_by_the_newest_forwarding(db_handler: DatabaseHandler, forwarded_in_db: list[str]):
    """A chat forwarded from again moves to the top of the list (as in Telegram), the order is not by title"""
    add_forwarded(db_handler, 9, CHANNEL, 'News')
    assert [source.label for source in db_handler.get_source_list()] == ['News', 'Chat 77', 'Hidden Bob']


def test_database_filters_by_the_source(client: TestClient, db_handler: DatabaseHandler, forwarded_in_db: list[str]):
    """The filter finds the groups by the chat ID (whatever the saved title) and by the name of a hidden author"""
    def found(keys: list[str]) -> list[str]:
        data = {DB_SOURCE: keys, FormCfg.db_message_filter['dialog_select']: str(ME),
                FormCfg.db_message_filter['date_from']: '2020-01-01'}
        client.post('/db_message_apply_filters', data=data)
        return sorted(group.grouped_id for group in db_handler.current_state.message_group_list)

    assert found([str(CHANNEL)]) == sorted(forwarded_in_db[:2])
    assert found(['name:Hidden Bob']) == [forwarded_in_db[2]]
    assert found([str(CHANNEL), 'name:Hidden Bob', '77']) == sorted(forwarded_in_db[:4])
    assert found(['name:Nobody']) == []
    assert found([]) == sorted(forwarded_in_db)


def test_database_details_show_the_source(db_handler: DatabaseHandler, forwarded_in_db: list[str]):
    """The details tell where the message was forwarded from; own messages have no such line"""
    assert db_handler.get_message_detail(forwarded_in_db[1])['source_title'] == 'News'
    assert db_handler.get_message_detail(forwarded_in_db[3])['source_title'] == 'Chat 77'
    assert db_handler.get_message_detail(forwarded_in_db[4])['source_title'] == ''


def test_database_source_filter_works_only_for_saved_messages_alone(client: TestClient, db_handler: DatabaseHandler,
                                                                     forwarded_in_db: list[str]):
    """The source exists only in "Saved Messages": with no chat chosen, or with other chats too, a stale choice of the
    hidden select is ignored (it must not hide the messages of the other chats)"""
    dialog_select = FormCfg.db_message_filter['dialog_select']
    for data in ({DB_SOURCE: str(CHANNEL)}, {DB_SOURCE: str(CHANNEL), dialog_select: [str(ME), '5']}):
        client.post('/db_message_apply_filters', data={**data, FormCfg.db_message_filter['date_from']: '2020-01-01'})
        assert db_handler.message_sort_filter.selected_source_list is None
        assert len(db_handler.current_state.message_group_list) == 5


def test_source_filters_have_their_own_grid_cells(client: TestClient):
    """The filter of each tab stands in its own cell of the grid (not inside the action bar)"""
    page = client.get('/').text
    assert f'class="tg-source" id="{FormCfg.tg_message_filter["source_filter"]}"' in page
    assert f'class="db-source" id="{FormCfg.db_message_filter["source_filter"]}"' in page


def test_database_details_header_shows_the_source_instead_of_the_dialog(client: TestClient,
                                                                         forwarded_in_db: list[str]):
    """The header of the details names the chat the message came from instead of "Saved"; an own message keeps the
    dialog; there is no separate "Forwarded from" line"""
    forwarded = client.get(f'/db_details/{forwarded_in_db[1]}').ui()['db_details']
    assert 'News' in forwarded and 'Saved' not in forwarded and 'Forwarded from:' not in forwarded
    assert 'Chat 77' in client.get(f'/db_details/{forwarded_in_db[3]}').ui()['db_details']
    assert 'Saved' in client.get(f'/db_details/{forwarded_in_db[4]}').ui()['db_details']


def test_telegram_details_header_shows_the_source_instead_of_the_dialog(client: TestClient, tg_handler: SimpleNamespace):
    """The same in the Telegram details: the source, else the dialog"""
    details = {'dialog_id': ME, 'dialog_title': 'Saved Messages', 'message_group_id': f'{ME}_1',
               'date': datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc), 'html': 'Hi', 'files': [],
               'existing_files': [], 'pending_files': [], 'files_report': '', 'saved_to_db': False,
               'source_id': CHANNEL, 'source_title': '<b>News</b>'}
    tg_handler.get_message_detail.return_value = details
    shown = client.get(f'/tg_details/{ME}/{ME}_1').ui()['tg_details']
    assert '&lt;b&gt;News&lt;/b&gt;' in shown and 'Saved Messages' not in shown
    details['source_title'] = ''
    assert 'Saved Messages' in client.get(f'/tg_details/{ME}/{ME}_1').ui()['tg_details']


def test_database_source_filter_is_one_line_and_keeps_the_choice(client: TestClient, db_handler: DatabaseHandler,
                                                                  forwarded_in_db: list[str]):
    """The filter above the list is a single select with the "all" item, newest forwarding first, applying at once;
    the chosen source stays chosen when the page is drawn again; no sources, no filter"""
    page = client.get('/').text
    assert f'id="{DB_SOURCE}"' in page
    assert 'multiple' not in page.split(f'id="{DB_SOURCE}"')[1].split('</select>')[0]
    assert "'/db_message_apply_filters'" in page.split(f'id="{DB_SOURCE}"')[1].split('</select>')[0]
    client.post('/db_message_apply_filters',
                data={DB_SOURCE: str(CHANNEL), FormCfg.db_message_filter['dialog_select']: str(ME)})
    redrawn = client.get('/').text.split(f'id="{DB_SOURCE}"')[1].split('</select>')[0]
    assert f'value="{CHANNEL}" selected' in redrawn and redrawn.count(' selected') == 1
    db_handler.session.query(DbMessageGroup).update({'source_chat_id': None, 'source_chat_title': None})
    db_handler.session.commit()
    assert f'id="{DB_SOURCE}"' not in client.get('/').text


def test_database_drops_the_choice_of_a_source_without_messages(db_handler: DatabaseHandler,
                                                                forwarded_in_db: list[str]):
    """After a deletion the chosen source may be gone from the list: the choice is dropped, the others stay"""
    db_handler.message_sort_filter.selected_source_list = ['name:Hidden Bob', str(CHANNEL)]
    db_handler.session.query(DbMessageGroup).filter_by(grouped_id=forwarded_in_db[2]).delete()
    db_handler.session.commit()
    db_handler.drop_missing_source_filter()
    assert db_handler.message_sort_filter.selected_source_list == [str(CHANNEL)]
    db_handler.session.query(DbMessageGroup).filter(DbMessageGroup.source_chat_id == CHANNEL).delete()
    db_handler.session.commit()
    db_handler.drop_missing_source_filter()
    assert db_handler.message_sort_filter.selected_source_list is None


def test_save_stores_the_source(client: TestClient, tg_handler: SimpleNamespace, db_handler: DatabaseHandler):
    """Saving a group stores its source chat; a group without a source stores nothing (NULL, not an empty title)"""
    dialog = SimpleNamespace(dialog_id=ME, title='Saved', type=DialogTypes.USER, get_self_dir=lambda: 'saved')
    tg_handler.get_dialog_by_id = MagicMock(return_value=dialog)
    groups = []
    for number, (chat_id, title) in enumerate([(CHANNEL, 'News'), (None, 'Hidden Bob'), (None, '')], start=1):
        group = TgMessageGroup(f'{ME}_{number}', ME)
        group.date = datetime(2026, 1, number, 3, 4, 5)
        group.html = group.plain_text = group.truncated_text = 'x'
        group.sender_id = ME
        group.source_chat_id, group.source_chat_title = chat_id, title
        groups.append(group)
    tg_handler.current_state.message_group_list = groups
    checkbox = FormCfg.tg_checkbox_list['tg_checkbox_list']
    response = client.post('/tg_save_selected_message_to_db',
                           data={checkbox: [f'{GlobalConst.select_in_telegram}{group.grouped_id}' for group in groups]})
    assert response.status_code == 200
    saved = {group.grouped_id: (group.source_chat_id, group.source_chat_title)
             for group in db_handler.session.query(DbMessageGroup)}
    assert saved == {f'{ME}_1': (CHANNEL, 'News'), f'{ME}_2': (None, 'Hidden Bob'), f'{ME}_3': (None, None)}
    # The filter list of the database tab is refreshed in the same answer / Список фильтра БД обновляется в том же ответе
    assert 'News' in response.ui()[DB_SOURCE_FILTER] and 'Hidden Bob' in response.ui()[DB_SOURCE_FILTER]
    assert f'id="{DB_SOURCE}"' in response.ui()[DB_SOURCE_FILTER]
