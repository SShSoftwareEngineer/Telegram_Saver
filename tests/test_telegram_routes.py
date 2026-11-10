"""
Tests of the Telegram routes: status, JSON keys, state changes and filters. The Telegram handler is a fake object.
Тесты маршрутов Telegram: статус, ключи JSON, изменение состояния и фильтры. Обработчик Telegram - заглушка.
"""

from datetime import datetime
from types import SimpleNamespace
import pytest
from fastapi.testclient import TestClient
from configs.config import FormCfg

# Negative IDs are normal in Telegram: groups and channels / Отрицательные ID - норма в Telegram: группы и каналы
CHANNEL_ID = -1001234567891


def make_dialog(dialog_id: int = CHANNEL_ID, title: str = 'Test chat') -> SimpleNamespace:
    """Fake Telegram dialog / Заглушка диалога Telegram"""
    return SimpleNamespace(dialog_id=dialog_id, title=title)


def make_message_group(dialog_id: int = CHANNEL_ID, number: int = 1, sender_id: int | None = 1) -> SimpleNamespace:
    """Fake message group with the attributes `tg_messages.html` uses (sender 1 is the fake account `tg_me`)
    Заглушка группы сообщений (отправитель 1 - заглушка аккаунта `tg_me`)"""
    return SimpleNamespace(grouped_id=f'{dialog_id}_{number}', dialog_id=dialog_id, date=datetime(2026, 1, 2, 3, 4, 5),
                           text='Hello\nworld', sender_id=sender_id, files_report='1 photo', saved_to_db=False)


def make_details(message_group_id: str = f'{CHANNEL_ID}_1') -> dict:
    """Fake message details with an image and a video / Заглушка деталей сообщения с изображением и видео"""
    return {'dialog_id': CHANNEL_ID, 'dialog_title': 'Test chat', 'message_group_id': message_group_id,
            'date': datetime(2026, 1, 2, 3, 4, 5), 'text': 'Hello\nworld', 'saved_to_db': False,
            'existing_files': [SimpleNamespace(alt_text='Image', file_path='chat/photo 1.jpg'),
                               SimpleNamespace(alt_text='Video', file_path='chat/clip.mp4')]}


def test_get_dialogs(client: TestClient, tg_handler: SimpleNamespace):
    """The dialog list goes to the state and to the response with the counter / Список диалогов и счетчик"""
    tg_handler.get_dialog_list.return_value = [make_dialog(), make_dialog(42, 'Friend')]
    response = client.get('/tg_dialogs')
    assert response.status_code == 200
    data = response.json()
    assert set(data) == {'tg_dialogs', 'tg-chats-count'}
    assert data['tg-chats-count'] == '(2)'
    assert 'Test chat' in data['tg_dialogs'] and 'Friend' in data['tg_dialogs']
    assert f'/tg_messages/{CHANNEL_ID}' in data['tg_dialogs']
    assert len(tg_handler.current_state.dialog_list) == 2


@pytest.mark.parametrize('dialog_id', [CHANNEL_ID, -123456789, 987654321])
def test_get_messages(client: TestClient, tg_handler: SimpleNamespace, dialog_id: int):
    """Messages of a dialog, including negative IDs (channels, groups), become the current state"""
    tg_handler.get_message_group_list.return_value = [make_message_group(dialog_id, 1),
                                                      make_message_group(dialog_id, 2)]
    response = client.get(f'/tg_messages/{dialog_id}')
    assert response.status_code == 200
    data = response.json()
    assert set(data) == {'tg_messages', 'tg-messages-count', 'tg_details'}
    assert data['tg-messages-count'] == '(2)'
    assert data['tg_details'] == ''
    assert f'/tg_details/{dialog_id}/{dialog_id}_1' in data['tg_messages']
    tg_handler.get_message_group_list.assert_called_once_with(dialog_id)
    assert tg_handler.current_state.selected_dialog_id == dialog_id
    assert len(tg_handler.current_state.message_group_list) == 2


def test_get_messages_highlights_own_messages(client: TestClient, tg_handler: SimpleNamespace):
    """Only the messages of the logged-in account (sender ID equals `tg_me.id`) get the own-message style; messages
    of others, of channels (negative ID) and without a sender do not / Подсветка только своих сообщений"""
    tg_handler.get_message_group_list.return_value = [
        make_message_group(number=1, sender_id=1), make_message_group(number=2, sender_id=2),
        make_message_group(number=3, sender_id=-1001234567891), make_message_group(number=4, sender_id=None)]
    response = client.get(f'/tg_messages/{CHANNEL_ID}')
    assert response.status_code == 200
    assert response.json()['tg_messages'].count('my-message-in-list') == 1


def test_get_messages_marks_saved(client: TestClient, tg_handler: SimpleNamespace, monkeypatch: pytest.MonkeyPatch):
    """A message group that is already in the database is marked as saved / Сохраненная группа помечается"""
    group = make_message_group()
    tg_handler.get_message_group_list.return_value = [group]
    monkeypatch.setattr('database_handler.DatabaseHandler.message_group_exists', lambda _self, _id: True)
    response = client.get(f'/tg_messages/{CHANNEL_ID}')
    assert response.status_code == 200
    assert group.saved_to_db is True


def test_get_messages_not_a_number(client: TestClient, tg_handler: SimpleNamespace):
    """A non-numeric dialog ID is rejected as 422 in JSON before Telegram is called / Нечисловой ID - 422 в JSON"""
    response = client.get('/tg_messages/abc')
    assert response.status_code == 422
    assert 'error' in response.json()
    tg_handler.get_message_group_list.assert_not_called()


@pytest.mark.parametrize('dialog_id', [CHANNEL_ID, 987654321])
def test_get_details(client: TestClient, tg_handler: SimpleNamespace, dialog_id: int):
    """Message details are rendered with image and video links, the ID with a minus passes as is"""
    group_id = f'{dialog_id}_1'
    tg_handler.get_message_detail.return_value = make_details(group_id)
    response = client.get(f'/tg_details/{dialog_id}/{group_id}')
    assert response.status_code == 200
    data = response.json()
    assert set(data) == {'tg_details'}
    assert 'Hello<br>world' in data['tg_details']
    assert 'src="/media_storage/chat/photo%201.jpg"' in data['tg_details']
    assert 'src="http://testserver/media_storage/chat/clip.mp4"' in data['tg_details']
    tg_handler.get_message_detail.assert_called_once_with(dialog_id, group_id)
    assert tg_handler.current_state.message_details['message_group_id'] == group_id


def test_get_details_not_a_number(client: TestClient, tg_handler: SimpleNamespace):
    """A non-numeric dialog ID gives 422 / Нечисловой ID диалога - 422"""
    response = client.get('/tg_details/abc/abc_1')
    assert response.status_code == 422
    tg_handler.get_message_detail.assert_not_called()


def test_dialog_apply_filters(client: TestClient, tg_handler: SimpleNamespace):
    """Dialog filters come from the form, the message list and details are cleared / Фильтры диалогов из формы"""
    cfg = FormCfg.tg_dialog_filter
    tg_handler.current_state.message_group_list = [make_message_group()]
    tg_handler.current_state.message_details = make_details()
    tg_handler.get_dialog_list.return_value = [make_dialog()]
    response = client.post('/tg_dialog_apply_filters', data={
        cfg['sorting_field']: '0', cfg['sorting_order']: '1', cfg['dialog_type']: '2',
        cfg['dialog_title_query']: 'chat'})
    assert response.status_code == 200
    data = response.json()
    assert set(data) == {'tg_dialogs', 'tg-chats-count', 'tg-messages-count', 'tg_messages', 'tg_details'}
    assert data['tg-chats-count'] == '(1)'
    assert data['tg-messages-count'] == data['tg_messages'] == data['tg_details'] == ''
    dial_filter = tg_handler.dialog_sort_filter
    dial_filter.sort_field.assert_called_once_with('0')
    dial_filter.sort_order.assert_called_once_with('1')
    dial_filter.dialog_type.assert_called_once_with('2')
    dial_filter.title_query.assert_called_once_with('chat')
    assert tg_handler.current_state.message_group_list == []
    assert tg_handler.current_state.message_details is None


def test_dialog_apply_filters_empty_form(client: TestClient, tg_handler: SimpleNamespace):
    """Missing form fields give None, as `request.form.get` in Flask / Отсутствующие поля формы дают None"""
    response = client.post('/tg_dialog_apply_filters')
    assert response.status_code == 200
    tg_handler.dialog_sort_filter.sort_field.assert_called_once_with(None)
    tg_handler.dialog_sort_filter.title_query.assert_called_once_with(None)


def test_message_apply_filters(client: TestClient, tg_handler: SimpleNamespace):
    """Message filters come from the form, the list is rebuilt for the selected dialog, details are cleared"""
    cfg = FormCfg.tg_message_filter
    tg_handler.current_state.selected_dialog_id = CHANNEL_ID
    tg_handler.current_state.message_details = make_details()
    tg_handler.get_message_group_list.return_value = [make_message_group()]
    response = client.post('/tg_message_apply_filters', data={
        cfg['sorting_order']: '1', cfg['date_from']: '2026-01-01', cfg['date_to']: '2026-02-01',
        cfg['message_query']: 'hello'})
    assert response.status_code == 200
    data = response.json()
    assert set(data) == {'tg_messages', 'tg-messages-count', 'tg_details'}
    assert data['tg-messages-count'] == '(1)'
    assert data['tg_details'] == ''
    mess_filter = tg_handler.message_sort_filter
    assert (mess_filter.sort_order, mess_filter.date_from, mess_filter.date_to, mess_filter.message_query) == (
        '1', '2026-01-01', '2026-02-01', 'hello')
    tg_handler.get_message_group_list.assert_called_once_with(CHANNEL_ID)
    assert tg_handler.current_state.message_details is None


def test_telegram_error_gives_json_500(error_client: TestClient, tg_handler: SimpleNamespace):
    """An error of the Telegram handler gives 500 in JSON and releases the lock / Ошибка Telegram - 500 в JSON"""
    tg_handler.get_dialog_list.side_effect = RuntimeError('boom')
    response = error_client.get('/tg_dialogs')
    assert response.status_code == 500
    assert response.json() == {'error': 'RuntimeError: boom'}
    # The lock is free: the next request does not hang / Замок свободен: следующий запрос не зависает
    tg_handler.get_dialog_list.side_effect = None
    assert error_client.get('/tg_dialogs').status_code == 200
