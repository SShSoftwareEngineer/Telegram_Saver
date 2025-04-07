from datetime import datetime
from typing import List

from sqlalchemy import create_engine, Integer, ForeignKey, Text, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, Session

# SQLite and MS Excel file name / Имя файла SQLite и MS Excel для экспорта базы данных
_DATA_BASE_NAME = 'telegram_archive'

TABLE_NAMES = {'message': 'messages',
               'dialog': 'dialogs',
               'group': 'groups',
               'file': 'files',
               'file_type': 'file_types',
               'tag': 'tags',
               'tag_message': 'tags_messages'}


class Base(DeclarativeBase):
    """ A declarative class for creating tables in the database """


class Message(Base):
    __tablename__ = TABLE_NAMES['message']
    id: Mapped[int] = mapped_column(primary_key=True)
    dialog_id: Mapped[int] = mapped_column(Integer, ForeignKey(f'{TABLE_NAMES['dialog']}.dialog_id'))
    group_id: Mapped[int] = mapped_column(Integer, ForeignKey(f'{TABLE_NAMES['group']}.group_id'), nullable=True)
    file_id: Mapped[int] = mapped_column(Integer, ForeignKey(f'{TABLE_NAMES['file']}.file_id'), nullable=True)
    message_id: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    date_time: Mapped[datetime]
    from_user: Mapped[str] = mapped_column(Text, nullable=True)
    text: Mapped[str] = mapped_column(Text, nullable=True)
    raw_text: Mapped[str] = mapped_column(Text, nullable=True)
    tag_messages: Mapped[List['TagMessage']] = relationship('TagMessage', back_populates='message')

    @property
    def tags(self):
        return [tm.tag for tm in self.tag_messages]


class Dialog(Base):
    __tablename__ = TABLE_NAMES['dialog']
    id: Mapped[int] = mapped_column(primary_key=True)
    dialog_id: Mapped[int] = mapped_column(Integer, index=True)
    dialog_title: Mapped[str] = mapped_column(Text, nullable=True)
    message_id: Mapped["Message"] = relationship(back_populates="dialog_id")


class Group(Base):
    __tablename__ = TABLE_NAMES['group']
    id: Mapped[int] = mapped_column(primary_key=True)
    group_id: Mapped[int] = mapped_column(Integer, index=True)
    message_id: Mapped["Message"] = relationship(back_populates="group_id")


class File(Base):
    __tablename__ = TABLE_NAMES['file']
    id: Mapped[int] = mapped_column(primary_key=True)
    file_id: Mapped[int] = mapped_column(Integer, index=True)
    file_path: Mapped[str] = mapped_column(Text)
    file_name: Mapped[str] = mapped_column(Text)
    type_id: Mapped[int] = mapped_column(Integer, ForeignKey(f'{TABLE_NAMES['file_type']}.id'))
    size: Mapped[int] = mapped_column(Integer)
    thumbnail: Mapped[str] = mapped_column(Text)
    message_id: Mapped["Message"] = relationship(back_populates="file_id")


class FileType(Base):
    __tablename__ = TABLE_NAMES['file_type']
    id: Mapped[int] = mapped_column(primary_key=True)
    type_name: Mapped[str] = mapped_column(Text)
    file: Mapped["File"] = relationship(back_populates="type_id")


class Tag(Base):
    __tablename__ = TABLE_NAMES['tag']
    id: Mapped[int] = mapped_column(primary_key=True)
    tag_name: Mapped[str] = mapped_column(Text)
    tag_messages: Mapped[List['TagMessage']] = relationship('TagMessage', back_populates='tag')

    @property
    def messages(self):
        return [tm.message for tm in self.tag_messages]


class TagMessage(Base):
    __tablename__ = TABLE_NAMES['tag_message']
    tag_id: Mapped[int] = mapped_column(Integer, ForeignKey(f'{TABLE_NAMES['tag']}.id'), primary_key=True)
    message_id: Mapped[int] = mapped_column(Integer, ForeignKey(f'{TABLE_NAMES['message']}.id'), primary_key=True)
    tag: Mapped['Tag'] = relationship('Tag', back_populates='tag_messages')
    message: Mapped['Message'] = relationship('Message', back_populates='tag_messages')


# Connecting to the database. Creating a database connection and session
# Подключение к базе данных. Создаем соединение с базой данных и сессию
engine = create_engine(f'sqlite:///{_DATA_BASE_NAME}.db')
session = Session(engine)
# Creating tables in the database if they do not exist
# Создаем таблицы в базе данных, если они отсутствуют
Base.metadata.create_all(engine)

if __name__ == '__main__':
    pass
