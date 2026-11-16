"""
Tests that the Telegram and the database tabs behave the same way: a new filter is neutral and `set_default_filters()`
gives the default period; a page load (also a reload) shows the dates of the current filter and a counter that
equals the length of the list next to it (no counter for an empty list).
Тесты единообразия вкладок Telegram и БД: новый фильтр нейтральный, а `set_default_filters()` дает период по умолчанию;
загрузка страницы (в том числе повторная) показывает даты текущего фильтра и счетчик, равный длине списка рядом с ним
(для пустого списка счетчика нет).
"""

import re
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any
import pytest
from fastapi.testclient import TestClient
from configs.config import FormCfg, GlobalConst
from database_handler import DbMessageSortFilter
import telegram_handler
from telegram_handler import TgMessageSortFilter
from utils import local_day_start

TG_CFG = FormCfg.tg_message_filter
CHANNEL_ID = -1001234567891


def input_tag(page: str, field: Any) -> str:
    """The `<input>` tag of a form field of the page / Тег `<input>` поля формы на странице"""
    match = re.search(rf'<input[^>]*id="{field}"[^>]*>', page, re.S)
    assert match, f'the field {field} is not on the page'
    return match.group(0)


def make_dialog(number: int) -> SimpleNamespace:
    """Fake Telegram dialog / Заглушка диалога Telegram"""
    return SimpleNamespace(dialog_id=CHANNEL_ID - number, title=f'Chat {number}')


def make_group(number: int) -> SimpleNamespace:
    """Fake message group with the attributes `tg_messages.html` uses / Заглушка группы сообщений"""
    return SimpleNamespace(grouped_id=f'{CHANNEL_ID}_{number}', dialog_id=CHANNEL_ID,
                           date=datetime(2026, 1, 2, 3, 4, number, tzinfo=timezone.utc), plain_text='Hello',
                           html='Hello', sender_id=1, files_report='', saved_to_db=False)


# ----------------------------------------------------------------------------------------------------------------------
# The filters of both tabs / Фильтры обеих вкладок
# ----------------------------------------------------------------------------------------------------------------------

TABS = [pytest.param(TgMessageSortFilter, GlobalConst.tg_last_days_by_default, id='telegram'),
        pytest.param(DbMessageSortFilter, GlobalConst.db_last_days_by_default, id='database')]


@pytest.mark.parametrize('filter_class, days', TABS)
def test_new_filter_is_neutral(filter_class, days: int):
    """A new filter has no period on both tabs; only `set_default_filters()` sets the default one"""
    message_filter = filter_class()
    assert message_filter.date_from is None and message_filter.date_to is None
    message_filter.set_default_filters()
    assert message_filter.date_from == local_day_start(days) and message_filter.date_to is None
    assert message_filter.message_query is None


@pytest.mark.parametrize('filter_class, days', TABS)
def test_defaults_replace_the_dates_and_the_query(filter_class, days: int):
    """`set_default_filters()` resets what the user set on both tabs / Умолчания сбрасывают заданное пользователем"""
    message_filter = filter_class()
    message_filter.date_from = '2026-01-05'
    message_filter.date_to = '2026-02-10'
    message_filter.message_query = 'text'
    message_filter.set_default_filters()
    assert message_filter.date_from == local_day_start(days) and message_filter.date_to is None
    assert message_filter.message_query is None


# ----------------------------------------------------------------------------------------------------------------------
# The Telegram page (the database page is in test_db_default_period.py) / Страница Telegram
# ----------------------------------------------------------------------------------------------------------------------

def test_telegram_first_load_has_default_date_and_no_counters(client: TestClient):
    """First load: the date field has the start of the default period, no list, no counters"""
    page = client.get('/').text
    start = local_day_start(GlobalConst.tg_last_days_by_default)
    assert f'value="{start:%Y-%m-%d}"' in input_tag(page, TG_CFG['date_from'])
    assert 'value=""' in input_tag(page, TG_CFG['date_to'])
    assert '<span id="tg-chats-count"></span>' in page
    assert '<span id="tg-messages-count"></span>' in page


def test_telegram_counters_equal_the_lists_after_reload(client: TestClient, tg_handler: SimpleNamespace):
    """A page loaded with the lists in the state shows the counters equal to their lengths (also after a reload)"""
    tg_handler.current_state.dialog_list = [make_dialog(1), make_dialog(2)]
    tg_handler.current_state.message_group_list = [make_group(1), make_group(2), make_group(3)]
    for _ in range(2):  # the second load is a reload / вторая загрузка - это перезагрузка
        page = client.get('/').text
        assert '<span id="tg-chats-count">(2)</span>' in page
        assert '<span id="tg-messages-count">(3)</span>' in page
    tg_handler.current_state.dialog_list = []
    tg_handler.current_state.message_group_list = []
    page = client.get('/').text
    assert '<span id="tg-chats-count"></span>' in page and '<span id="tg-messages-count"></span>' in page


def test_telegram_page_shows_the_current_filter_dates(client: TestClient, tg_handler: SimpleNamespace):
    """After the filter is applied the page (also a reloaded one) shows its dates, and an empty date stays empty"""
    tg_handler.current_state.selected_dialog_id = CHANNEL_ID
    tg_handler.get_message_group_list.return_value = [make_group(1), make_group(2)]
    form = {TG_CFG['sorting_order']: '0', TG_CFG['date_from']: '2026-01-05', TG_CFG['date_to']: '2026-02-10'}
    assert client.post('/tg_message_apply_filters', data=form).status_code == 200
    page = client.get('/').text
    assert 'value="2026-01-05"' in input_tag(page, TG_CFG['date_from'])
    assert 'value="2026-02-10"' in input_tag(page, TG_CFG['date_to'])
    assert '<span id="tg-messages-count">(2)</span>' in page
    form[TG_CFG['date_from']] = ''
    form[TG_CFG['date_to']] = ''
    assert client.post('/tg_message_apply_filters', data=form).status_code == 200
    page = client.get('/').text
    assert 'value=""' in input_tag(page, TG_CFG['date_from'])
    assert 'value=""' in input_tag(page, TG_CFG['date_to'])


# ----------------------------------------------------------------------------------------------------------------------
# The real Telegram handler (the Telethon client is a fake) / Настоящий обработчик Telegram (клиент Telethon - заглушка)
# ----------------------------------------------------------------------------------------------------------------------

def test_telegram_handler_creates_its_own_default_filter(monkeypatch: pytest.MonkeyPatch):
    """Like the database handler, the Telegram handler creates its own filter with the defaults (not the class
    attribute shared by all instances): changing the filter of one handler does not touch the other"""
    class FakeClient:  # pylint: disable=too-few-public-methods
        """No network, no login / Без сети и без входа"""

        def __init__(self, *_args, **_kwargs):
            pass

        async def start(self, *_args, **_kwargs):
            """Login / Вход"""

        async def get_me(self):
            """The account / Аккаунт"""
            return SimpleNamespace(id=1)

        async def get_dialogs(self):
            """No dialogs / Нет диалогов"""
            return []

        async def disconnect(self):
            """Logout / Отключение"""

    monkeypatch.setattr(telegram_handler, 'TelegramClient', FakeClient)
    monkeypatch.setattr(telegram_handler, 'dotenv_values', lambda *_: {
        'SESSION_NAME': 'x', 'API_ID': '1', 'API_HASH': 'x', 'PHONE': 'x', 'PASSWORD': 'x'})
    first, second = telegram_handler.TelegramHandler(), telegram_handler.TelegramHandler()
    try:
        start = local_day_start(GlobalConst.tg_last_days_by_default)
        assert first.message_sort_filter.date_from == start and first.message_sort_filter.date_to is None
        assert first.message_sort_filter is not second.message_sort_filter
        assert first.message_sort_filter is not telegram_handler.TelegramHandler.message_sort_filter
        first.message_sort_filter.date_from = '2026-01-05'  # type: ignore[assignment]
        assert second.message_sort_filter.date_from == start
        assert first.current_state.message_group_list == []  # no list until a chat is selected / нет списка до чата
    finally:
        first.close()
        second.close()
