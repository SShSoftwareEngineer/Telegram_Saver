"""
Tests of `TgMessageGroup.add_message`: the sender is stored as a number (`sender_id`), never as a raw Telethon `Peer`
object (SQLite cannot store it: "type 'PeerUser' is not supported"). Telethon messages are fake objects.
Тесты `TgMessageGroup.add_message`: отправитель хранится числом (`sender_id`), а не сырым объектом Telethon `Peer`
(SQLite его не сохранит: "type 'PeerUser' is not supported"). Сообщения Telethon - заглушки.
"""

from datetime import datetime
from types import SimpleNamespace
from telethon.tl.types import PeerChannel, PeerUser
from telegram_handler import TgMessageGroup


def make_message(message_id: int, sender_id: int | None, from_id=None, text: str = 'Hello') -> SimpleNamespace:
    """Fake Telethon message with the attributes `add_message` uses / Заглушка сообщения Telethon"""
    return SimpleNamespace(id=message_id, sender_id=sender_id, from_id=from_id, text=text,
                           date=datetime(2026, 1, 2, 3, 4, message_id))


def test_sender_is_a_number_not_a_peer():
    """A message from a user has the raw `PeerUser` in `from_id`, but the group keeps the number / Число, не Peer"""
    group = TgMessageGroup('42_1', 42)
    group.add_message(make_message(1, 8837960131, from_id=PeerUser(user_id=8837960131)))  # type: ignore[arg-type]
    assert group.sender_id == 8837960131
    assert isinstance(group.sender_id, int)


def test_sender_of_channel_post_and_missing_sender():
    """A channel keeps its marked (negative) ID; a message without a sender (own outgoing message in a private chat)
    gives None / Канал - маркированный (отрицательный) ID; нет отправителя - None"""
    channel_group = TgMessageGroup('-1001_1', -1001)
    channel_post = make_message(1, -1001234567891, from_id=PeerChannel(channel_id=1234567891))
    channel_group.add_message(channel_post)  # type: ignore[arg-type]
    assert channel_group.sender_id == -1001234567891
    own_group = TgMessageGroup('42_2', 42)
    own_group.add_message(make_message(1, None))  # type: ignore[arg-type]
    assert own_group.sender_id is None


def test_first_known_sender_of_a_group_is_kept():
    """The sender is taken from the first message that has one; the later messages do not replace it"""
    group = TgMessageGroup('42_3', 42)
    group.add_message(make_message(1, None))  # type: ignore[arg-type]
    group.add_message(make_message(2, 7))  # type: ignore[arg-type]
    group.add_message(make_message(3, 8))  # type: ignore[arg-type]
    assert group.sender_id == 7
    assert group.ids == [1, 2, 3]
