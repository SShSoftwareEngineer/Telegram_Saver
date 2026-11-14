"""
Tests of the tag methods of `DatabaseHandler`: add, remove, update for one message group and update everywhere. The
database is real (a temporary SQLite file). The tests fix the behavior the routes rely on and check that a composite
operation (update) is one transaction.
Тесты методов тегов `DatabaseHandler`: добавление, удаление, изменение у одной группы сообщений и изменение везде.
База данных настоящая (временный файл SQLite). Тесты фиксируют поведение, на которое опираются роуты, и проверяют, что
составная операция (изменение) выполняется одной транзакцией.
"""

from datetime import datetime
import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import NoResultFound
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
    group = DbMessageGroup(grouped_id=grouped_id, date=datetime(2026, 1, number), text='text', truncated_text='text',
                           files_report='', sender_id=7, dialog_id=1)
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
# add_tag_to_message_group
# ----------------------------------------------------------------------------------------------------------------------

def test_add_new_tag(db_handler: DatabaseHandler):
    """A new tag is created, linked to the group, counted; both select strings contain it"""
    group_id = add_group(db_handler, 1)
    current, everything = db_handler.add_tag_to_message_group('travel', group_id)
    assert group_tags(db_handler, group_id) == ['travel']
    assert all_tags(db_handler) == {'travel': 1}
    assert option('travel') in current and option('travel') in everything


def test_add_existing_tag_to_another_group(db_handler: DatabaseHandler):
    """The same name is the same tag: no duplicate, the count grows"""
    first = add_group(db_handler, 1, ('travel',))
    second = add_group(db_handler, 2)
    db_handler.add_tag_to_message_group('travel', second)
    assert group_tags(db_handler, first) == group_tags(db_handler, second) == ['travel']
    assert all_tags(db_handler) == {'travel': 2}


def test_add_same_tag_twice(db_handler: DatabaseHandler):
    """Adding a tag the group already has changes nothing"""
    group_id = add_group(db_handler, 1, ('travel',))
    db_handler.add_tag_to_message_group('travel', group_id)
    assert group_tags(db_handler, group_id) == ['travel']
    assert all_tags(db_handler) == {'travel': 1}


def test_add_to_unknown_group(db_handler: DatabaseHandler):
    """A group that does not exist: NoResultFound (the routes check the ID beforehand)"""
    with pytest.raises(NoResultFound):
        db_handler.add_tag_to_message_group('travel', 'no_such_group')


# ----------------------------------------------------------------------------------------------------------------------
# remove_tag_from_message_group
# ----------------------------------------------------------------------------------------------------------------------

def test_remove_tag_used_elsewhere(db_handler: DatabaseHandler):
    """The tag leaves the group, stays in the database for the other group with a smaller count"""
    first = add_group(db_handler, 1, ('travel', 'food'))
    second = add_group(db_handler, 2, ('travel',))
    current, everything = db_handler.remove_tag_from_message_group('travel', first)
    assert group_tags(db_handler, first) == ['food']
    assert group_tags(db_handler, second) == ['travel']
    assert all_tags(db_handler) == {'travel': 1, 'food': 1}
    assert option('travel') not in current and option('food') in current
    assert option('travel') in everything


def test_remove_last_usage_deletes_tag(db_handler: DatabaseHandler):
    """A tag without messages is deleted from the database"""
    group_id = add_group(db_handler, 1, ('travel',))
    _, everything = db_handler.remove_tag_from_message_group('travel', group_id)
    assert group_tags(db_handler, group_id) == []
    assert all_tags(db_handler) == {}
    assert option('travel') not in everything


def test_remove_tag_the_group_does_not_have(db_handler: DatabaseHandler):
    """Nothing changes for a tag that is not on the group"""
    first = add_group(db_handler, 1, ('travel',))
    second = add_group(db_handler, 2, ('food',))
    db_handler.remove_tag_from_message_group('food', first)
    assert group_tags(db_handler, first) == ['travel']
    assert group_tags(db_handler, second) == ['food']
    assert all_tags(db_handler) == {'travel': 1, 'food': 1}


# ----------------------------------------------------------------------------------------------------------------------
# update_tag_from_message_group
# ----------------------------------------------------------------------------------------------------------------------

def test_update_tag_of_one_group(db_handler: DatabaseHandler):
    """The tag is replaced on this group only; the other group keeps the old one"""
    first = add_group(db_handler, 1, ('old',))
    second = add_group(db_handler, 2, ('old',))
    current, everything = db_handler.update_tag_from_message_group('old', 'new', first)
    assert group_tags(db_handler, first) == ['new']
    assert group_tags(db_handler, second) == ['old']
    assert all_tags(db_handler) == {'old': 1, 'new': 1}
    assert option('new') in current and option('old') not in current
    assert option('new') in everything and option('old') in everything


def test_update_tag_deletes_unused_old_tag(db_handler: DatabaseHandler):
    """The old tag is deleted if no other message uses it"""
    group_id = add_group(db_handler, 1, ('old',))
    db_handler.update_tag_from_message_group('old', 'new', group_id)
    assert all_tags(db_handler) == {'new': 1}


def test_update_tag_the_group_does_not_have(db_handler: DatabaseHandler):
    """The old tag is not on the group: nothing changes, the new tag is not created"""
    group_id = add_group(db_handler, 1, ('travel',))
    add_group(db_handler, 2, ('old',))
    db_handler.update_tag_from_message_group('old', 'new', group_id)
    assert group_tags(db_handler, group_id) == ['travel']
    assert all_tags(db_handler) == {'travel': 1, 'old': 1}


def test_update_tag_to_the_tag_the_group_already_has(db_handler: DatabaseHandler):
    """Renaming into a tag the group has: the old one is gone, no duplicate link"""
    group_id = add_group(db_handler, 1, ('old', 'new'))
    db_handler.update_tag_from_message_group('old', 'new', group_id)
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
    current, everything = db_handler.update_tag_everywhere('old', 'new', first)
    assert group_tags(db_handler, first) == ['new']
    assert group_tags(db_handler, second) == ['food', 'new']
    assert group_tags(db_handler, third) == ['food']
    assert all_tags(db_handler) == {'new': 2, 'food': 2}
    assert current is not None and option('new') in current
    assert option('new') in everything and option('old') not in everything


def test_update_tag_everywhere_selected_group_without_the_tag(db_handler: DatabaseHandler):
    """The selected group does not have the tag: its tag select is not returned (None), other groups are renamed"""
    selected = add_group(db_handler, 1, ('food',))
    other = add_group(db_handler, 2, ('old',))
    current, _ = db_handler.update_tag_everywhere('old', 'new', selected)
    assert current is None
    assert group_tags(db_handler, other) == ['new']
    assert group_tags(db_handler, selected) == ['food']


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

def test_update_tag_failure_keeps_old_tag(db_handler: DatabaseHandler, monkeypatch: pytest.MonkeyPatch):
    """A failure while adding the new tag rolls back the removal of the old one (one transaction)"""
    group_id = add_group(db_handler, 1, ('old',))

    def fail(*_args):
        raise RuntimeError('boom')

    monkeypatch.setattr(DatabaseHandler, '_attach_tag', fail)
    with pytest.raises(RuntimeError):
        db_handler.update_tag_from_message_group('old', 'new', group_id)
    assert group_tags(db_handler, group_id) == ['old']
    assert all_tags(db_handler) == {'old': 1}


def test_update_tag_everywhere_failure_changes_nothing(db_handler: DatabaseHandler, monkeypatch: pytest.MonkeyPatch):
    """A failure on the second group rolls back the change of the first one too"""
    first = add_group(db_handler, 1, ('old',))
    second = add_group(db_handler, 2, ('old',))
    original = DatabaseHandler._attach_tag  # pylint: disable=protected-access
    calls = []

    def fail_on_second(self, message_group, tag_name):
        calls.append(tag_name)
        if len(calls) == 2:
            raise RuntimeError('boom')
        original(self, message_group, tag_name)

    monkeypatch.setattr(DatabaseHandler, '_attach_tag', fail_on_second)
    with pytest.raises(RuntimeError):
        db_handler.update_tag_everywhere('old', 'new', first)
    assert group_tags(db_handler, first) == group_tags(db_handler, second) == ['old']
    assert all_tags(db_handler) == {'old': 2}
