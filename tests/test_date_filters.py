"""
Tests of the date filters (both tabs): the form sends ISO `YYYY-MM-DD` (day and month are never swapped), the period is
whole local days (the last day is included), the dates are boundaries of the local day of the system. The tests do not
depend on the time zone of the machine: the expected values are local times converted with `astimezone()`.
Тесты фильтров по дате (обе вкладки): форма присылает ISO `YYYY-MM-DD` (день и месяц не меняются местами), период -
целые локальные сутки (последний день включается), даты - границы локального дня системы. Тесты не зависят от
часового пояса машины: ожидаемые значения - локальное время, переведенное через `astimezone()`.
"""

from datetime import datetime, time, timedelta
import pytest
from fastapi.testclient import TestClient
from configs.config import DialogTypes, FormCfg, GlobalConst
from database_handler import DatabaseHandler, DbCurrentState, DbDialog, DbMessageGroup, DbMessageSortFilter
from telegram_handler import TgMessageSortFilter
from utils import local_day_start, parse_date_string

FILTER_CFG = FormCfg.db_message_filter


def local(year: int, month: int, day: int, hour: int = 0, minute: int = 0, second: int = 0,
          microsecond: int = 0) -> datetime:  # pylint: disable=too-many-arguments,too-many-positional-arguments
    """Aware datetime built from local wall time / Aware дата-время из локального «настенного» времени"""
    return datetime(year, month, day, hour, minute, second, microsecond).astimezone()


# ----------------------------------------------------------------------------------------------------------------------
# Parsing / Разбор
# ----------------------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize('value, expected', [
    ('2026-11-05', (2026, 11, 5)),  # the day is not a month: was read as May 11 / день не месяц: читалось как 11 мая
    ('2026-01-02', (2026, 1, 2)),   # was read as February 1 / читалось как 1 февраля
    ('2026-12-12', (2026, 12, 12)),
    ('2026-03-04', (2026, 3, 4)),
    ('2026-01-15', (2026, 1, 15)),
    ('2026-12-31', (2026, 12, 31)),
    ('  2026-11-05  ', (2026, 11, 5)),  # the edges are trimmed / края обрезаются
])
def test_parse_keeps_day_and_month(value: str, expected: tuple[int, int, int]):
    """ISO dates are read as year-month-day; the start is 00:00:00, the end 23:59:59.999999, both are local"""
    start = parse_date_string(value)
    end = parse_date_string(value, end_of_day=True)
    assert start is not None and end is not None
    assert start.tzinfo is not None and end.tzinfo is not None
    assert start.replace(tzinfo=None) == datetime(*expected)
    assert end.replace(tzinfo=None) == datetime(*expected, 23, 59, 59, 999999)
    assert start == local(*expected) and end == local(*expected, 23, 59, 59, 999999)


@pytest.mark.parametrize('value', [None, '', '   ', 'abc', '05.11.2026', '11/05/2026', '2026-13-01', '2026-02-30',
                                   '2026-11', '2026-11-05 10:00'])
def test_parse_other_formats_switch_the_filter_off(value: str | None):
    """The empty value and everything that is not an ISO date give None (the filter is off), never a wrong date"""
    assert parse_date_string(value) is None
    assert parse_date_string(value, end_of_day=True) is None


def test_local_day_start():
    """The start of the local day, N days ago: midnight, aware / Начало локального дня N дней назад: полночь, aware"""
    today = local_day_start()
    assert today.tzinfo is not None
    assert today.replace(tzinfo=None) == datetime.combine(datetime.now().date(), time.min)
    earlier = local_day_start(30)
    assert earlier.replace(tzinfo=None) == datetime.combine((datetime.now() - timedelta(days=30)).date(), time.min)


# ----------------------------------------------------------------------------------------------------------------------
# Filter objects / Объекты фильтров
# ----------------------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize('filter_class', [TgMessageSortFilter, DbMessageSortFilter])
def test_filter_setters_take_whole_days(filter_class):
    """`date_from` is the start of its day, `date_to` is the end of its day (the last day is included)"""
    message_filter = filter_class()
    message_filter.date_from = '2026-01-15'
    message_filter.date_to = '2026-01-15'
    assert message_filter.date_from == local(2026, 1, 15)
    assert message_filter.date_to == local(2026, 1, 15, 23, 59, 59, 999999)


@pytest.mark.parametrize('filter_class', [TgMessageSortFilter, DbMessageSortFilter])
def test_filter_setters_clear_on_empty_or_invalid(filter_class):
    """An empty or invalid value switches the date off / Пустое или неверное значение выключает дату"""
    message_filter = filter_class()
    for value in ('', None, 'not a date', '15.01.2026'):
        message_filter.date_from = '2026-01-15'
        message_filter.date_to = '2026-01-15'
        message_filter.date_from = value
        message_filter.date_to = value
        assert message_filter.date_from is None and message_filter.date_to is None


def test_telegram_default_start_is_the_local_day_start():
    """The default start of the Telegram filter is a local midnight (like the date in the form field)"""
    message_filter = TgMessageSortFilter()
    message_filter.set_default_filters()
    start = message_filter.date_from
    assert start is not None and start.tzinfo is not None and start.replace(tzinfo=None).time() == time(0)
    assert start == local_day_start(GlobalConst.tg_last_days_by_default)


# ----------------------------------------------------------------------------------------------------------------------
# Boundaries of the period in the database / Границы периода в базе данных
# ----------------------------------------------------------------------------------------------------------------------

@pytest.fixture
def boundary_groups(db_handler: DatabaseHandler) -> DatabaseHandler:
    """
    Groups around the local day of January 15: the last second before it, its first and last moments, a noon, and the
    first moment of the next day.
    Группы вокруг локального дня 15 января: последняя секунда перед ним, его первый и последний моменты, полдень и
    первый момент следующего дня.
    """
    session = db_handler.session
    session.add(DbDialog(dialog_id=1, title='Chat', dialog_type_id=DialogTypes.CHANNEL.value))
    moments = {'1_1': local(2026, 1, 14, 23, 59, 59), '1_2': local(2026, 1, 15, 0, 0, 0),
               '1_3': local(2026, 1, 15, 12, 0, 0), '1_4': local(2026, 1, 15, 23, 59, 59),
               '1_5': local(2026, 1, 15, 23, 59, 59, 999999), '1_6': local(2026, 1, 16, 0, 0, 0)}
    for grouped_id, moment in moments.items():
        session.add(DbMessageGroup(grouped_id=grouped_id, date=moment, html='text', plain_text='text',
                                   truncated_text='text', files_report='', sender_id=7, dialog_id=1))
    session.commit()
    return db_handler


def period(db_handler: DatabaseHandler, date_from: str | None, date_to: str | None) -> list[str]:
    """IDs of the groups found for the period given as form strings / ID групп, найденных за период (строки формы)"""
    message_filter = DbMessageSortFilter()
    message_filter.date_from = date_from  # type: ignore[assignment]
    message_filter.date_to = date_to  # type: ignore[assignment]
    db_handler.message_sort_filter = message_filter
    return sorted(group.grouped_id for group in db_handler.get_message_group_list())


def test_one_day_period_includes_the_whole_day(boundary_groups: DatabaseHandler):
    """From and to are the same day: from its first moment to its last, nothing before or after it"""
    assert period(boundary_groups, '2026-01-15', '2026-01-15') == ['1_2', '1_3', '1_4', '1_5']


def test_last_day_is_included_and_next_day_is_not(boundary_groups: DatabaseHandler):
    """`date_to` includes the message of 23:59:59.999999 and excludes the next midnight"""
    assert period(boundary_groups, None, '2026-01-15') == ['1_1', '1_2', '1_3', '1_4', '1_5']
    assert period(boundary_groups, None, '2026-01-14') == ['1_1']


def test_first_day_includes_its_midnight(boundary_groups: DatabaseHandler):
    """`date_from` includes the message of 00:00:00 and excludes the last second of the previous day"""
    assert period(boundary_groups, '2026-01-15', None) == ['1_2', '1_3', '1_4', '1_5', '1_6']
    assert period(boundary_groups, '2026-01-16', None) == ['1_6']


def test_two_day_period_and_empty_period(boundary_groups: DatabaseHandler):
    """A period of two days, a period before all messages and a reversed period (from is later than to)"""
    assert period(boundary_groups, '2026-01-14', '2026-01-16') == ['1_1', '1_2', '1_3', '1_4', '1_5', '1_6']
    assert period(boundary_groups, '2026-01-10', '2026-01-13') == []
    assert period(boundary_groups, '2026-01-16', '2026-01-15') == []


def test_no_dates_no_period(boundary_groups: DatabaseHandler):
    """Without dates every group is found / Без дат находятся все группы"""
    assert period(boundary_groups, None, None) == ['1_1', '1_2', '1_3', '1_4', '1_5', '1_6']


def test_filter_route_uses_whole_local_days(client: TestClient, boundary_groups: DatabaseHandler):
    """The same period through the route (form strings): the counter has the groups of the whole last day"""
    boundary_groups.message_sort_filter = DbMessageSortFilter()
    boundary_groups.current_state = DbCurrentState()
    form = {FILTER_CFG['date_from']: '2026-01-15', FILTER_CFG['date_to']: '2026-01-15',
            FILTER_CFG['sorting_field']: '0', FILTER_CFG['sorting_order']: '0'}
    response = client.post('/db_message_apply_filters', data=form)
    assert response.status_code == 200
    assert response.json()['db-messages-count'] == '(4)'
