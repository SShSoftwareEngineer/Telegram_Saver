"""
Tests of the default period of the database tab: the handler starts with the filter "the last N days, sorted by date",
the first list, the counter and the dates in the filter form agree with it.
Тесты периода по умолчанию вкладки БД: обработчик стартует с фильтром "последние N дней, сортировка по дате", первый
список, счетчик и даты в форме фильтра совпадают с ним.
"""

import re
from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from typing import Any
import pytest
from fastapi.testclient import TestClient
from configs.config import DialogTypes, FormCfg, GlobalConst
from database_handler import DatabaseHandler, DbDialog, DbMessageGroup, DbMessageSortFilter
from utils import local_day_start

FILTER_CFG = FormCfg.db_message_filter
DAYS = GlobalConst.db_last_days_by_default
START = local_day_start(DAYS)  # the start of the default period / начало периода по умолчанию
NOW = datetime.now(timezone.utc)


def add_group(handler: DatabaseHandler, grouped_id: str, date: datetime) -> None:
    """Adds a message group with the date (and its dialog) / Добавляет группу сообщений с датой (и ее диалог)"""
    session = handler.session
    if session.get(DbDialog, 1) is None:
        session.add(DbDialog(dialog_id=1, title='Chat', dialog_type_id=DialogTypes.CHANNEL.value))
    session.add(DbMessageGroup(grouped_id=grouped_id, date=date, html='text', plain_text='text', truncated_text='text',
                               files_report='', sender_id=7, dialog_id=1))
    session.commit()


def fill(handler: DatabaseHandler) -> None:
    """
    Groups around the start of the default period: an old one, the last second before the start, the very first moment
    of the period, and two recent ones.
    Группы вокруг начала периода по умолчанию: старая, последняя секунда перед началом, самый первый момент периода и
    две свежие.
    """
    add_group(handler, 'old', NOW - timedelta(days=DAYS + 30))
    add_group(handler, 'before', START - timedelta(seconds=1))
    add_group(handler, 'start', START)
    add_group(handler, 'recent_1', NOW - timedelta(days=3))
    add_group(handler, 'recent_2', NOW - timedelta(days=1))


@pytest.fixture
def started(db_handler: DatabaseHandler) -> Iterator[DatabaseHandler]:
    """A second handler, created on the database that already has the groups: the handler of a restarted application"""
    fill(db_handler)
    handler = DatabaseHandler()
    yield handler
    handler.session.close()
    handler.engine.dispose()


# ----------------------------------------------------------------------------------------------------------------------
# Constants and the filter / Константы и фильтр
# ----------------------------------------------------------------------------------------------------------------------

def test_constants_of_the_tabs():
    """Each tab has its own number of days; the old shared name is gone / У каждой вкладки свое число дней"""
    assert GlobalConst.tg_last_days_by_default > 0 and GlobalConst.db_last_days_by_default > 0
    assert not hasattr(GlobalConst, 'last_days_by_default')


def test_new_filter_is_neutral_and_defaults_are_set_on_request():
    """`DbMessageSortFilter()` has no period (the tests and the routes rely on it); the defaults are set explicitly"""
    message_filter = DbMessageSortFilter()
    assert message_filter.date_from is None and message_filter.date_to is None
    message_filter.set_default_filters()
    assert message_filter.date_from == START and message_filter.date_to is None
    assert message_filter.sorting_field == message_filter.sort_by_date and message_filter.sort_order is True
    assert message_filter.selected_dialog_list is None and message_filter.message_query is None
    assert message_filter.tag_query is None and message_filter.tag_match_all is False


def test_defaults_replace_what_was_set():
    """The defaults reset every field of a used filter, the period too / Умолчания сбрасывают все поля фильтра"""
    message_filter = DbMessageSortFilter()
    message_filter.date_from = '2026-01-01'
    message_filter.date_to = '2026-01-31'
    message_filter.message_query = 'text'
    message_filter.tag_query = 'a; b'
    message_filter.tag_match_all = '1'
    message_filter.selected_dialog_list = [1]
    message_filter.set_default_filters()
    assert message_filter.date_from == START and message_filter.date_to is None
    assert message_filter.message_query is None and message_filter.tag_query is None
    assert message_filter.tag_match_all is False and message_filter.selected_dialog_list is None


# ----------------------------------------------------------------------------------------------------------------------
# Start of the handler / Старт обработчика
# ----------------------------------------------------------------------------------------------------------------------

def test_handler_starts_with_an_empty_list_and_the_default_period(started: DatabaseHandler):
    """Like the Telegram tab, the list is empty until the filter is applied; the default filter is set all the same"""
    assert started.current_state.message_group_list == []
    assert started.message_sort_filter.date_from == START
    assert started.message_sort_filter.sorting_field == started.message_sort_filter.sort_by_date


def test_default_filter_gives_the_period_newest_first(started: DatabaseHandler):
    """Applying the default filter gives the groups of the period (its first moment included), newest first"""
    ids = [group.grouped_id for group in started.get_message_group_list()]
    assert ids == ['recent_2', 'recent_1', 'start']


def test_handler_filter_is_its_own(db_handler: DatabaseHandler, started: DatabaseHandler):
    """Each handler has its own filter object, not the class attribute shared by all of them"""
    assert started.message_sort_filter is not db_handler.message_sort_filter


def test_empty_database_starts_with_an_empty_list(db_handler: DatabaseHandler):
    """A new database: an empty list, the period is set all the same / Новая БД: пустой список, период задан"""
    assert db_handler.current_state.message_group_list == []
    assert db_handler.message_sort_filter.date_from == START


# ----------------------------------------------------------------------------------------------------------------------
# The page / Страница
# ----------------------------------------------------------------------------------------------------------------------

def field_tag(page: str, field: Any) -> str:
    """The `<input>` tag of a form field of the page / Тег `<input>` поля формы на странице"""
    match = re.search(rf'<input[^>]*id="{field}"[^>]*>', page, re.S)
    assert match, f'the field {field} is not on the page'
    return match.group(0)


def test_page_counter_list_and_date_agree(client: TestClient, started: DatabaseHandler,
                                          monkeypatch: pytest.MonkeyPatch):
    """First load: no list and no counter, the date field has the start of the period; once the list is loaded
    the counter shows its length"""
    monkeypatch.setattr('database_handler._db_handler', started)
    page = client.get('/').text
    assert '<span id="db-messages-count"></span>' in page
    assert page.count('class="db-message-checkbox"') == 0
    assert f'value="{START:%Y-%m-%d}"' in field_tag(page, FILTER_CFG['date_from'])
    assert 'value=""' in field_tag(page, FILTER_CFG['date_to'])
    started.current_state.message_group_list = started.get_message_group_list()  # what "Apply" does
    page = client.get('/').text
    assert '<span id="db-messages-count">(3)</span>' in page
    assert page.count('class="db-message-checkbox"') == 3


def test_page_shows_the_current_filter_dates(client: TestClient, db_handler: DatabaseHandler):
    """After the filter is applied the page (also a reloaded one) shows its dates, and an empty date stays empty"""
    fill(db_handler)
    form = {FILTER_CFG['date_from']: '2026-01-05', FILTER_CFG['date_to']: '2026-02-10',
            FILTER_CFG['sorting_field']: '0', FILTER_CFG['sorting_order']: '1'}
    assert client.post('/db_message_apply_filters', data=form).status_code == 200
    page = client.get('/').text
    assert 'value="2026-01-05"' in field_tag(page, FILTER_CFG['date_from'])
    assert 'value="2026-02-10"' in field_tag(page, FILTER_CFG['date_to'])
    form[FILTER_CFG['date_from']] = ''
    form[FILTER_CFG['date_to']] = ''
    assert client.post('/db_message_apply_filters', data=form).status_code == 200
    page = client.get('/').text
    assert 'value=""' in field_tag(page, FILTER_CFG['date_from'])
    assert 'value=""' in field_tag(page, FILTER_CFG['date_to'])
    # the counter agrees with the list after the reload too / счетчик совпадает со списком и после перезагрузки
    assert f'<span id="db-messages-count">({page.count('class="db-message-checkbox"')})</span>' in page


def test_filter_form_has_no_stray_template_tag(client: TestClient):
    """The `#}` that was left after the id of the date field is gone / Лишний `#}` после id поля даты убран"""
    assert '#}' not in client.get('/').text
