"""
Tests of the tag methods of `DatabaseHandler`: add, remove, update for several message groups (the checked messages)
and update everywhere. The database is real (a temporary SQLite file). The tests fix the behavior the routes rely on and
check that an operation on several groups is one transaction.
Тесты методов тегов `DatabaseHandler`: добавление, удаление, изменение для нескольких групп сообщений (отмеченных
сообщений) и изменение везде. База данных настоящая (временный файл SQLite). Тесты фиксируют поведение, на которое
опираются роуты, и проверяют, что операция над несколькими группами выполняется одной транзакцией.
"""

from datetime import datetime
import pytest
from sqlalchemy import func, select
from configs.config import DialogTypes
from database_handler import DatabaseHandler, DbCurrentState, DbDialog, DbMessageGroup, DbTag, message_group_tag_links


@pytest.fixture(autouse=True)
def fresh_state(db_handler: DatabaseHandler) -> None:
    """
    The current state is a class attribute of the handler (shared between tests): give this test its own
    Текущее состояние - атрибут класса обработчика (общий для тестов): даем этому тесту собственное
    """
    db_handler.current_state = DbCurrentState()


def add_group(handler: DatabaseHandler, number: int, tags: tuple[str, ...] = ()) -> str:
    """Adds a message group (the dialog is created once) with tags (the same name is the same tag); returns its ID
    Добавляет группу сообщений (диалог создается один раз) с тегами (одно имя - один тег); возвращает ее ID"""
    session = handler.session
    if not session.get(DbDialog, 1):
        session.add(DbDialog(dialog_id=1, title='Chat', dialog_type_id=DialogTypes.CHANNEL.value))
    grouped_id = f'1_{number}'
    group = DbMessageGroup(grouped_id=grouped_id, date=datetime(2026, 1, number), html='text', plain_text='text',
                           truncated_text='text',
                           sender_id=7, dialog_id=1)
    session.add(group)
    for name in tags:
        group.tags.append(session.query(DbTag).filter_by(name=name).first() or DbTag(name=name))
    session.commit()
    # The usage counts are set the way the application keeps them / Счетчики задаем так, как их ведет приложение
    handler.get_all_tag_list()
    return grouped_id


def group_tags(handler: DatabaseHandler, grouped_id: str) -> list[str]:
    """Sorted tag names of a message group, read from the database / Имена тегов группы из базы данных"""
    handler.session.expire_all()
    stmt = select(DbMessageGroup).where(DbMessageGroup.grouped_id == grouped_id)
    return sorted(tag.name for tag in handler.session.execute(stmt).scalars().one().tags)


def all_tags(handler: DatabaseHandler) -> dict[str, int]:
    """All tags in the database with their usage counts / Все теги в базе данных с количеством использований"""
    handler.session.expire_all()
    return {tag.name: tag.usage_count for tag in handler.session.query(DbTag).all()}


def option(name: str) -> str:
    """The end of a SELECT option with the tag name / Конец элемента option с именем тега"""
    return f'>{name}</option>'


# ----------------------------------------------------------------------------------------------------------------------
# add_tag_to_message_groups
# ----------------------------------------------------------------------------------------------------------------------

def test_add_new_tag(db_handler: DatabaseHandler):
    """A new tag is created, linked to the group, counted; the select strings contain it"""
    group_id = add_group(db_handler, 1)
    change = db_handler.add_tag_to_message_groups('travel', [group_id], group_id)
    assert group_tags(db_handler, group_id) == ['travel']
    assert all_tags(db_handler) == {'travel': 1}
    assert change.changed == 1
    assert change.current_tags_select is not None and option('travel') in change.current_tags_select
    assert option('travel') in change.all_tags_select


def test_add_to_several_groups_at_once(db_handler: DatabaseHandler):
    """All the checked groups get the tag, the unchecked one does not; one tag, the count is the number of groups"""
    first, second, third = (add_group(db_handler, number) for number in (1, 2, 3))
    change = db_handler.add_tag_to_message_groups('travel', [first, second])
    assert group_tags(db_handler, first) == group_tags(db_handler, second) == ['travel']
    assert group_tags(db_handler, third) == []
    assert all_tags(db_handler) == {'travel': 2}
    assert change.changed == 2


def test_add_counts_only_the_groups_that_got_the_tag(db_handler: DatabaseHandler):
    """A group that already has the tag does not count and does not get a duplicate link"""
    first = add_group(db_handler, 1, ('travel',))
    second = add_group(db_handler, 2)
    third = add_group(db_handler, 3)
    change = db_handler.add_tag_to_message_groups('travel', [first, second, third])
    assert change.changed == 2
    assert all_tags(db_handler) == {'travel': 3}
    assert group_tags(db_handler, first) == ['travel']


def test_add_same_tag_twice(db_handler: DatabaseHandler):
    """Adding a tag the group already has changes nothing"""
    group_id = add_group(db_handler, 1, ('travel',))
    change = db_handler.add_tag_to_message_groups('travel', [group_id])
    assert change.changed == 0
    assert group_tags(db_handler, group_id) == ['travel']
    assert all_tags(db_handler) == {'travel': 1}


def test_add_repeated_and_unknown_ids(db_handler: DatabaseHandler):
    """A repeated ID counts once, an ID of a group that does not exist is skipped (no error)"""
    group_id = add_group(db_handler, 1)
    change = db_handler.add_tag_to_message_groups('travel', [group_id, group_id, 'no_such_group'])
    assert change.changed == 1
    assert group_tags(db_handler, group_id) == ['travel']
    assert all_tags(db_handler) == {'travel': 1}


def test_add_to_no_groups(db_handler: DatabaseHandler):
    """No checked groups: nothing changes (the list of all tags is still returned)"""
    group_id = add_group(db_handler, 1, ('food',))
    change = db_handler.add_tag_to_message_groups('travel', [])
    assert change.changed == 0 and change.current_tags_select is None
    assert group_tags(db_handler, group_id) == ['food'] and all_tags(db_handler) == {'food': 1}
    assert option('food') in change.all_tags_select


def test_open_message_tags_only_when_it_was_processed(db_handler: DatabaseHandler):
    """The tags of the open message come back only if it is among the checked groups; otherwise None"""
    first = add_group(db_handler, 1)
    second = add_group(db_handler, 2)
    among = db_handler.add_tag_to_message_groups('travel', [first], current_group_id=first)
    assert among.current_tags_select is not None and option('travel') in among.current_tags_select
    not_among = db_handler.add_tag_to_message_groups('food', [first], current_group_id=second)
    assert not_among.current_tags_select is None
    assert group_tags(db_handler, second) == []  # the open message is not the target / открытое сообщение не цель


# ----------------------------------------------------------------------------------------------------------------------
# remove_tag_from_message_groups
# ----------------------------------------------------------------------------------------------------------------------

def test_remove_tag_used_elsewhere(db_handler: DatabaseHandler):
    """The tag leaves the checked group, stays in the database for the other group with a smaller count"""
    first = add_group(db_handler, 1, ('travel', 'food'))
    second = add_group(db_handler, 2, ('travel',))
    change = db_handler.remove_tag_from_message_groups('travel', [first], first)
    assert group_tags(db_handler, first) == ['food']
    assert group_tags(db_handler, second) == ['travel']
    assert all_tags(db_handler) == {'travel': 1, 'food': 1}
    assert change.changed == 1
    assert change.current_tags_select is not None
    assert option('travel') not in change.current_tags_select and option('food') in change.current_tags_select
    assert option('travel') in change.all_tags_select


def test_remove_from_several_groups_and_last_usage_deletes_tag(db_handler: DatabaseHandler):
    """The tag is removed from all the checked groups; a tag without messages is deleted from the database"""
    first = add_group(db_handler, 1, ('travel',))
    second = add_group(db_handler, 2, ('travel', 'food'))
    change = db_handler.remove_tag_from_message_groups('travel', [first, second])
    assert group_tags(db_handler, first) == [] and group_tags(db_handler, second) == ['food']
    assert all_tags(db_handler) == {'food': 1}
    assert change.changed == 2 and option('travel') not in change.all_tags_select


def test_remove_counts_only_the_groups_that_had_the_tag(db_handler: DatabaseHandler):
    """A checked group without the tag does not count and nothing changes in it or in the unchecked group"""
    first = add_group(db_handler, 1, ('travel',))
    second = add_group(db_handler, 2, ('food',))
    third = add_group(db_handler, 3, ('travel',))
    change = db_handler.remove_tag_from_message_groups('travel', [first, second])
    assert change.changed == 1
    assert group_tags(db_handler, second) == ['food'] and group_tags(db_handler, third) == ['travel']
    assert all_tags(db_handler) == {'travel': 1, 'food': 1}


# ----------------------------------------------------------------------------------------------------------------------
# update_tag_from_message_groups
# ----------------------------------------------------------------------------------------------------------------------

def test_update_tag_of_the_checked_groups_only(db_handler: DatabaseHandler):
    """The tag is replaced in the checked groups; the unchecked group keeps the old one"""
    first = add_group(db_handler, 1, ('old',))
    second = add_group(db_handler, 2, ('old',))
    third = add_group(db_handler, 3, ('old',))
    change = db_handler.update_tag_from_message_groups('old', 'new', [first, second], first)
    assert group_tags(db_handler, first) == group_tags(db_handler, second) == ['new']
    assert group_tags(db_handler, third) == ['old']
    assert all_tags(db_handler) == {'old': 1, 'new': 2}
    assert change.changed == 2
    assert change.current_tags_select is not None
    assert option('new') in change.current_tags_select and option('old') not in change.current_tags_select
    assert option('new') in change.all_tags_select and option('old') in change.all_tags_select


def test_update_tag_deletes_unused_old_tag(db_handler: DatabaseHandler):
    """The old tag is deleted if no other message uses it"""
    group_id = add_group(db_handler, 1, ('old',))
    db_handler.update_tag_from_message_groups('old', 'new', [group_id])
    assert all_tags(db_handler) == {'new': 1}


def test_update_counts_only_the_groups_that_have_the_old_tag(db_handler: DatabaseHandler):
    """A checked group without the old tag is not touched and the new tag is not added to it"""
    with_tag = add_group(db_handler, 1, ('old',))
    without = add_group(db_handler, 2, ('travel',))
    change = db_handler.update_tag_from_message_groups('old', 'new', [with_tag, without])
    assert change.changed == 1
    assert group_tags(db_handler, with_tag) == ['new'] and group_tags(db_handler, without) == ['travel']


def test_update_tag_nobody_has(db_handler: DatabaseHandler):
    """No checked group has the old tag: nothing changes, the new tag is not created"""
    group_id = add_group(db_handler, 1, ('travel',))
    add_group(db_handler, 2, ('old',))
    change = db_handler.update_tag_from_message_groups('old', 'new', [group_id])
    assert change.changed == 0
    assert group_tags(db_handler, group_id) == ['travel']
    assert all_tags(db_handler) == {'travel': 1, 'old': 1}


def test_update_tag_to_the_tag_the_group_already_has(db_handler: DatabaseHandler):
    """Renaming into a tag the group has: the old one is gone, no duplicate link"""
    group_id = add_group(db_handler, 1, ('old', 'new'))
    db_handler.update_tag_from_message_groups('old', 'new', [group_id])
    assert group_tags(db_handler, group_id) == ['new']
    assert all_tags(db_handler) == {'new': 1}


# ----------------------------------------------------------------------------------------------------------------------
# update_tag_everywhere
# ----------------------------------------------------------------------------------------------------------------------

def test_update_tag_everywhere(db_handler: DatabaseHandler):
    """All groups with the tag get the new one, the old one is gone, other tags stay"""
    first = add_group(db_handler, 1, ('old',))
    second = add_group(db_handler, 2, ('old', 'food'))
    third = add_group(db_handler, 3, ('food',))
    change = db_handler.update_tag_everywhere('old', 'new', first)
    assert group_tags(db_handler, first) == ['new']
    assert group_tags(db_handler, second) == ['food', 'new']
    assert group_tags(db_handler, third) == ['food']
    assert all_tags(db_handler) == {'new': 2, 'food': 2}
    assert change.changed == 2
    assert change.current_tags_select is not None and option('new') in change.current_tags_select
    assert option('new') in change.all_tags_select and option('old') not in change.all_tags_select


def test_update_tag_everywhere_does_not_need_the_open_message(db_handler: DatabaseHandler):
    """Without an open message the tag is renamed everywhere all the same; no tags of the open message come back"""
    first = add_group(db_handler, 1, ('old',))
    second = add_group(db_handler, 2, ('old',))
    change = db_handler.update_tag_everywhere('old', 'new')
    assert group_tags(db_handler, first) == group_tags(db_handler, second) == ['new']
    assert change.changed == 2 and change.current_tags_select is None


def test_update_tag_everywhere_open_message_without_the_tag(db_handler: DatabaseHandler):
    """The open message does not have the tag: its tag select is not returned (None), other groups are renamed"""
    open_message = add_group(db_handler, 1, ('food',))
    other = add_group(db_handler, 2, ('old',))
    change = db_handler.update_tag_everywhere('old', 'new', open_message)
    assert change.current_tags_select is None
    assert group_tags(db_handler, other) == ['new']
    assert group_tags(db_handler, open_message) == ['food']


def test_update_tag_everywhere_into_existing_tag(db_handler: DatabaseHandler):
    """Renaming into a tag that exists merges them: one tag, the count is the number of groups"""
    first = add_group(db_handler, 1, ('old',))
    add_group(db_handler, 2, ('new',))
    db_handler.update_tag_everywhere('old', 'new', first)
    assert all_tags(db_handler) == {'new': 2}
    links = db_handler.session.execute(select(func.count()).select_from(message_group_tag_links)).scalar_one()
    assert links == 2


# ----------------------------------------------------------------------------------------------------------------------
# Atomicity / Атомарность
# ----------------------------------------------------------------------------------------------------------------------

def fail_on_second_call(monkeypatch: pytest.MonkeyPatch, name: str) -> None:
    """Makes the second call of the handler method `name` raise; the first call works as usual"""
    original = getattr(DatabaseHandler, name)
    calls: list[str] = []

    def wrapper(self, message_group, tag_name):
        calls.append(tag_name)
        if len(calls) == 2:
            raise RuntimeError('boom')
        return original(self, message_group, tag_name)

    monkeypatch.setattr(DatabaseHandler, name, wrapper)


def test_add_failure_on_second_group_changes_nothing(db_handler: DatabaseHandler, monkeypatch: pytest.MonkeyPatch):
    """A failure on the second group rolls back the tag added to the first one (one transaction for all the groups)"""
    first, second = add_group(db_handler, 1), add_group(db_handler, 2)
    fail_on_second_call(monkeypatch, '_attach_tag')
    with pytest.raises(RuntimeError):
        db_handler.add_tag_to_message_groups('travel', [first, second])
    assert group_tags(db_handler, first) == group_tags(db_handler, second) == []
    assert all_tags(db_handler) == {}


def test_remove_failure_on_second_group_changes_nothing(db_handler: DatabaseHandler, monkeypatch: pytest.MonkeyPatch):
    """A failure on the second group rolls back the removal from the first one"""
    first = add_group(db_handler, 1, ('travel',))
    second = add_group(db_handler, 2, ('travel',))
    fail_on_second_call(monkeypatch, '_detach_tag')
    with pytest.raises(RuntimeError):
        db_handler.remove_tag_from_message_groups('travel', [first, second])
    assert group_tags(db_handler, first) == group_tags(db_handler, second) == ['travel']
    assert all_tags(db_handler) == {'travel': 2}


def test_update_failure_keeps_old_tag(db_handler: DatabaseHandler, monkeypatch: pytest.MonkeyPatch):
    """A failure while adding the new tag rolls back the removal of the old one (one transaction)"""
    group_id = add_group(db_handler, 1, ('old',))

    def fail(*_args):
        raise RuntimeError('boom')

    monkeypatch.setattr(DatabaseHandler, '_attach_tag', fail)
    with pytest.raises(RuntimeError):
        db_handler.update_tag_from_message_groups('old', 'new', [group_id])
    assert group_tags(db_handler, group_id) == ['old']
    assert all_tags(db_handler) == {'old': 1}


def test_update_failure_on_second_group_changes_nothing(db_handler: DatabaseHandler, monkeypatch: pytest.MonkeyPatch):
    """A failure on the second group rolls back the change of the first one too"""
    first = add_group(db_handler, 1, ('old',))
    second = add_group(db_handler, 2, ('old',))
    fail_on_second_call(monkeypatch, '_attach_tag')
    with pytest.raises(RuntimeError):
        db_handler.update_tag_from_message_groups('old', 'new', [first, second])
    assert group_tags(db_handler, first) == group_tags(db_handler, second) == ['old']
    assert all_tags(db_handler) == {'old': 2}


def test_update_tag_everywhere_failure_changes_nothing(db_handler: DatabaseHandler, monkeypatch: pytest.MonkeyPatch):
    """A failure on the second group rolls back the change of the first one too"""
    first = add_group(db_handler, 1, ('old',))
    second = add_group(db_handler, 2, ('old',))
    fail_on_second_call(monkeypatch, '_attach_tag')
    with pytest.raises(RuntimeError):
        db_handler.update_tag_everywhere('old', 'new', first)
    assert group_tags(db_handler, first) == group_tags(db_handler, second) == ['old']
    assert all_tags(db_handler) == {'old': 2}
