from datetime import datetime
from typing import List

from sqlalchemy import create_engine, Integer, ForeignKey, Text, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, Session

from config.config import ProjectDirs, Constants, TableNames


class Base(DeclarativeBase):
    """ A declarative class for creating tables in the database """


class Message(Base):
    __tablename__ = TableNames.messages
    id: Mapped[int] = mapped_column(primary_key=True)
    dialog_id: Mapped[int] = mapped_column(Integer, ForeignKey(f'{TableNames.dialogs}.dialog_id'))
    grouped_id: Mapped[int] = mapped_column(Integer, ForeignKey(f'{TableNames.groups}.grouped_id'), nullable=True)
    file_id: Mapped[int] = mapped_column(Integer, ForeignKey(f'{TableNames.files}.file_id'), nullable=True)
    message_id: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    from_user: Mapped[str] = mapped_column(Text, nullable=True)
    tag_messages: Mapped[List['TagMessage']] = relationship('TagMessage', back_populates='message')

    @property
    def tags(self):
        return [tm.tag for tm in self.tag_messages]


class Dialog(Base):
    __tablename__ = TableNames.dialogs
    id: Mapped[int] = mapped_column(primary_key=True)
    dialog_id: Mapped[int] = mapped_column(Integer, index=True)
    dialog_title: Mapped[str] = mapped_column(Text, nullable=True)
    message_id: Mapped['Message'] = relationship(back_populates='dialog_id')


class Group(Base):
    __tablename__ = TableNames.groups
    id: Mapped[int] = mapped_column(primary_key=True)
    grouped_id: Mapped[int] = mapped_column(Integer, index=True)
    date_time: Mapped[datetime]
    text: Mapped[str] = mapped_column(Text, nullable=True)
    message_id: Mapped['Message'] = relationship(back_populates='grouped_id')


class File(Base):
    __tablename__ = TableNames.files
    id: Mapped[int] = mapped_column(primary_key=True)
    file_id: Mapped[int] = mapped_column(Integer, index=True)
    file_path: Mapped[str] = mapped_column(Text)
    file_name: Mapped[str] = mapped_column(Text)
    size: Mapped[int] = mapped_column(Integer)
    type_id: Mapped[int] = mapped_column(Integer, ForeignKey(f'{TableNames.file_types}.id'))
    message_id: Mapped['Message'] = relationship(back_populates='file_id')


class FileType(Base):
    __tablename__ = TableNames.file_types
    id: Mapped[int] = mapped_column(primary_key=True)
    type_name: Mapped[str] = mapped_column(Text)
    file: Mapped['File'] = relationship(back_populates='type_id')


class Tag(Base):
    __tablename__ = TableNames.tags
    id: Mapped[int] = mapped_column(primary_key=True)
    tag_name: Mapped[str] = mapped_column(Text)
    tag_messages: Mapped[List['TagMessage']] = relationship('TagMessage', back_populates='tag')

    @property
    def messages(self):
        return [tm.message for tm in self.tag_messages]


class TagMessage(Base):
    __tablename__ = TableNames.tags_messages
    tag_id: Mapped[int] = mapped_column(Integer, ForeignKey(f'{TableNames.tags}.id'), primary_key=True)
    message_id: Mapped[int] = mapped_column(Integer, ForeignKey(f'{TableNames.messages}.id'), primary_key=True)
    tag: Mapped['Tag'] = relationship('Tag', back_populates=TableNames.tags_messages)
    message: Mapped['Message'] = relationship('Message', back_populates=TableNames.tags_messages)


# Connecting to the database. Creating a database connection and session
# Подключение к базе данных. Создаем соединение с базой данных и сессию
engine = create_engine(f'sqlite:///{Constants.data_base_name}.db')
session = Session(engine)
# Creating tables in the database if they do not exist
# Создаем таблицы в базе данных, если они отсутствуют
Base.metadata.create_all(engine)

if __name__ == '__main__':
    pass
