"""
Tests of the UTC dates: the database stores dates in UTC (`UtcDateTime`), Telegram dates are kept in UTC, the user
always sees the local time of the system (templates, file names, directories). The tests do not depend on the time zone
of the machine: the expected values are built with `astimezone()` and with fixed offsets.
Тесты дат в UTC: база данных хранит даты в UTC (`UtcDateTime`), даты Telegram хранятся в UTC, пользователь всегда видит
локальное время системы (шаблоны, имена файлов, каталоги). Тесты не зависят от часового пояса машины: ожидаемые значения
строятся через `astimezone()` и фиксированные смещения.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from fastapi.testclient import TestClient
from sqlalchemy import text
from configs.config import DialogTypes, GlobalConst, MessageFileTypes
from database_handler import DatabaseHandler, DbCurrentState, DbDialog, DbMessageGroup, DbMessageSortFilter, DbTag
from telegram_handler import TgFile, TgMessageGroup, TgMessageSortFilter
from utils import parse_date_string, to_local, to_utc
from web.deps import local_dt

UTC = timezone.utc
MINUS_5 = timezone(timedelta(hours=-5))
# 23:30 on January 2 at UTC-5 is 04:30 on January 3 in UTC: the local and the UTC dates differ
# 23:30 2 января при UTC-5 - это 04:30 3 января в UTC: локальная дата и дата UTC различаются
EVENING = datetime(2026, 1, 2, 23, 30, tzinfo=MINUS_5)


def add_group(db_handler: DatabaseHandler, grouped_id: str, date: datetime, dialog_id: int = 1) -> None:
    """Adds a message group with the date (and its dialog) / Добавляет группу сообщений с датой (и ее диалог)"""
    session = db_handler.session
    if session.get(DbDialog, dialog_id) is None:
        session.add(DbDialog(dialog_id=dialog_id, title='Chat', dialog_type_id=DialogTypes.CHANNEL.value))
    session.add(DbMessageGroup(grouped_id=grouped_id, date=date, html='text', plain_text='text', truncated_text='text',
                               files_report='', sender_id=7, dialog_id=dialog_id))
    session.commit()


def found(db_handler: DatabaseHandler, date_from: datetime | None = None, date_to: datetime | None = None) -> list[str]:
    """IDs of the groups found by the date filter / ID групп, найденных фильтром по дате"""
    db_handler.message_sort_filter = DbMessageSortFilter()
    db_handler.message_sort_filter._date_from = date_from  # pylint: disable=protected-access
    db_handler.message_sort_filter._date_to = date_to  # pylint: disable=protected-access
    return sorted(group.grouped_id for group in db_handler.get_message_group_list())


# ----------------------------------------------------------------------------------------------------------------------
# Helpers / Помощники
# ----------------------------------------------------------------------------------------------------------------------

def test_to_utc_keeps_the_moment():
    """An aware datetime in any zone gives the same moment in UTC / Aware дата-время в любом поясе - тот же момент"""
    result = to_utc(EVENING)
    assert result == EVENING and result.utcoffset() == timedelta(0)
    assert (result.year, result.month, result.day, result.hour, result.minute) == (2026, 1, 3, 4, 30)


def test_naive_datetime_is_local_time():
    """A naive datetime is local time of the system (the Python rule), not UTC / Наивная дата - локальное время"""
    naive = datetime(2026, 1, 2, 12, 0)
    assert to_utc(naive) == naive.astimezone()
    assert to_local(naive).replace(tzinfo=None) == naive


def test_to_local_keeps_the_moment():
    """The local datetime is the same moment as the UTC one / Локальная дата-время - тот же момент, что и UTC"""
    moment = datetime(2026, 1, 3, 4, 30, tzinfo=UTC)
    assert to_local(moment) == moment
    assert to_local(moment).utcoffset() == moment.astimezone().utcoffset()


# ----------------------------------------------------------------------------------------------------------------------
# Database column / Столбец базы данных
# ----------------------------------------------------------------------------------------------------------------------

def test_database_stores_utc_and_returns_aware_utc(db_handler: DatabaseHandler):
    """Stored: the UTC wall time (SQLite has no zone). Read: the same moment as an aware datetime in UTC"""
    add_group(db_handler, '1_1', EVENING)
    stored = db_handler.session.execute(text(f'SELECT date FROM {DbMessageGroup.__tablename__}')).scalar_one()
    assert stored.startswith('2026-01-03 04:30:00')
    db_handler.session.expire_all()
    value = db_handler.session.get(DbMessageGroup, '1_1').date  # type: ignore[union-attr]
    assert value == EVENING and value.utcoffset() == timedelta(0)


def test_tag_creation_time_is_utc(db_handler: DatabaseHandler):
    """The default of `DbTag.updated_at` is the current moment in UTC / Значение по умолчанию - текущий момент в UTC"""
    db_handler.session.add(DbTag(name='tag'))
    db_handler.session.commit()
    db_handler.session.expire_all()
    value = db_handler.session.query(DbTag).one().updated_at
    assert value.utcoffset() == timedelta(0)
    assert abs(datetime.now(UTC) - value) < timedelta(minutes=1)


def test_date_filter_compares_moments(db_handler: DatabaseHandler):
    """The group is at 04:30 UTC: a filter bound in another zone is compared as a moment, not as a wall time"""
    add_group(db_handler, '1_1', EVENING)
    assert found(db_handler, date_from=datetime(2026, 1, 3, 4, 30, tzinfo=UTC)) == ['1_1']
    assert found(db_handler, date_from=datetime(2026, 1, 3, 4, 31, tzinfo=UTC)) == []
    assert found(db_handler, date_from=datetime(2026, 1, 2, 23, 30, tzinfo=MINUS_5)) == ['1_1']
    assert found(db_handler, date_from=datetime(2026, 1, 2, 23, 31, tzinfo=MINUS_5)) == []
    assert found(db_handler, date_to=datetime(2026, 1, 3, 4, 30, tzinfo=UTC)) == ['1_1']
    assert found(db_handler, date_to=datetime(2026, 1, 3, 4, 29, tzinfo=UTC)) == []


def test_naive_date_filter_is_local_time(db_handler: DatabaseHandler):
    """A naive filter date (a form value) is local time: the group at the local noon is found from that very moment"""
    local_noon = datetime(2026, 1, 2, 12, 0).astimezone()
    add_group(db_handler, '1_1', local_noon)
    assert found(db_handler, date_from=datetime(2026, 1, 2, 12, 0)) == ['1_1']
    assert found(db_handler, date_from=datetime(2026, 1, 2, 12, 1)) == []
    assert found(db_handler, date_to=datetime(2026, 1, 2, 12, 0)) == ['1_1']
    assert found(db_handler, date_to=datetime(2026, 1, 2, 11, 59)) == []


def test_sorting_by_date_is_by_moment(db_handler: DatabaseHandler):
    """The groups in different zones are ordered by the moment (all of them are stored in UTC)"""
    add_group(db_handler, '1_1', datetime(2026, 1, 3, 4, 0, tzinfo=UTC))   # 04:00 UTC
    add_group(db_handler, '1_2', datetime(2026, 1, 2, 23, 30, tzinfo=MINUS_5))  # 04:30 UTC
    add_group(db_handler, '1_3', datetime(2026, 1, 3, 5, 0, tzinfo=UTC))   # 05:00 UTC
    db_handler.message_sort_filter = DbMessageSortFilter()
    db_handler.message_sort_filter.sort_order = '1'  # ascending / по возрастанию
    assert [group.grouped_id for group in db_handler.get_message_group_list()] == ['1_1', '1_2', '1_3']


# ----------------------------------------------------------------------------------------------------------------------
# Telegram side / Сторона Telegram
# ----------------------------------------------------------------------------------------------------------------------

def make_message(message_id: int, date: datetime) -> SimpleNamespace:
    """Fake Telethon message (Telethon gives aware dates in UTC) / Заглушка сообщения (даты aware в UTC)"""
    return SimpleNamespace(id=message_id, sender_id=7, from_id=None, raw_text='Hello', entities=None, date=date)


def test_telegram_group_keeps_the_utc_date_of_the_first_message():
    """The group date stays UTC (not converted to local) and is the earliest date of its messages"""
    group = TgMessageGroup('42_1', 42)
    group.add_message(make_message(2, datetime(2026, 1, 3, 4, 31, tzinfo=UTC)))  # type: ignore[arg-type]
    group.add_message(make_message(1, datetime(2026, 1, 3, 4, 30, tzinfo=UTC)))  # type: ignore[arg-type]
    assert group.date == datetime(2026, 1, 3, 4, 30, tzinfo=UTC)
    assert group.date.utcoffset() == timedelta(0)  # type: ignore[union-attr]


def test_directory_and_file_names_use_the_local_date():
    """The directory of a message group is the local date, the file name starts with the local time"""
    moment = datetime(2026, 1, 3, 4, 30, 15, tzinfo=UTC)
    group = TgMessageGroup('42_1', 42)
    group.add_message(make_message(1, moment))  # type: ignore[arg-type]
    assert group.get_self_dir() == moment.astimezone().strftime('%Y-%m-%d')
    file_name = TgFile.get_self_file_name(moment, MessageFileTypes.CONTENT, '42_1', 0,
                                          MessageFileTypes.CONTENT.default_ext)
    assert file_name.startswith(moment.astimezone().strftime('%H-%M-%S'))


def test_sorting_of_groups_with_and_without_date():
    """A group without a date does not break the sorting of aware dates (aware and naive do not compare)"""
    dated = TgMessageGroup('42_1', 42)
    dated.add_message(make_message(1, datetime(2026, 1, 3, 4, 30, tzinfo=UTC)))  # type: ignore[arg-type]
    undated = TgMessageGroup('42_2', 42)
    assert TgMessageSortFilter().sort_message_group_list([undated, dated]) == [dated, undated]


def test_filter_dates_are_aware():
    """The dates of the Telegram filter are aware: Telethon takes a naive datetime for UTC (the filter was shifted)"""
    message_filter = TgMessageSortFilter()
    message_filter.set_default_filters()
    assert message_filter.date_from is not None and message_filter.date_from.tzinfo is not None
    parsed = parse_date_string('2026-01-15')
    assert parsed is not None and parsed.tzinfo is not None
    assert parsed.replace(tzinfo=None) == datetime(2026, 1, 15)  # local midnight / локальная полночь
    assert parse_date_string('') is None


# ----------------------------------------------------------------------------------------------------------------------
# Display / Показ
# ----------------------------------------------------------------------------------------------------------------------

def test_local_dt_filter_shows_the_local_time():
    """The template filter formats the date in the local time of the system / Фильтр шаблона - локальное время"""
    moment = datetime(2026, 1, 3, 4, 30, 15, tzinfo=UTC)
    assert local_dt(moment, GlobalConst.message_datetime_format) == moment.astimezone().strftime(
        GlobalConst.message_datetime_format)


def test_database_details_show_the_local_time(client: TestClient, db_handler: DatabaseHandler):
    """The message details (a route, a template) show the local time of the stored UTC date"""
    db_handler.current_state = DbCurrentState()
    add_group(db_handler, '1_1', EVENING)
    response = client.get('/db_details/1_1')
    assert response.status_code == 200
    assert EVENING.astimezone().strftime(GlobalConst.message_datetime_format) in response.json()['db_details']
