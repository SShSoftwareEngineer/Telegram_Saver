from datetime import datetime

from sqlalchemy import create_engine, Integer, ForeignKey, Text, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, Session

# SQLite and MS Excel file name / Имя файла SQLite и MS Excel для экспорта базы данных
_DATA_BASE_NAME = 'telegram_archive'

TABLE_NAMES = {'message': 'messages',
               'dialog': 'dialogs',
               'group': 'groups',
               'file': 'files',
               'file_type': 'file_types'}


class Base(DeclarativeBase):
    """ A declarative class for creating tables in the database """


class Message(Base):
    __tablename__ = TABLE_NAMES['message']
    id: Mapped[int] = mapped_column(primary_key=True)
    dialog_id: Mapped[int] = mapped_column(Integer, ForeignKey(f'{TABLE_NAMES['dialog']}.message_id'))
    group_id: Mapped[int] = mapped_column(Integer, ForeignKey(f'{TABLE_NAMES['group']}.message_id'))
    file_id: Mapped[int] = mapped_column(Integer, ForeignKey(f'{TABLE_NAMES['file']}.message_id'))
    message_id: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    date_time: Mapped[datetime]
    from_id: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text, nullable=True)
    raw_text: Mapped[str] = mapped_column(Text, nullable=True)


class Dialog(Base):
    __tablename__ = TABLE_NAMES['dialog']
    id: Mapped[int] = mapped_column(primary_key=True)
    dialog_id: Mapped[int] = mapped_column(Integer)
    dialog_title: Mapped[str] = mapped_column(Text, nullable=True)
    message: Mapped["Message"] = relationship(back_populates="dialog")


class Group(Base):
    __tablename__ = TABLE_NAMES['group']
    id: Mapped[int] = mapped_column(primary_key=True)
    group_id: Mapped[int] = mapped_column(Integer)
    message: Mapped["Message"] = relationship(back_populates="group")


class File(Base):
    __tablename__ = TABLE_NAMES['file']
    id: Mapped[int] = mapped_column(primary_key=True)
    file_id: Mapped[int] = mapped_column(Integer)
    file_path: Mapped[str] = mapped_column(Text)
    file_name: Mapped[str] = mapped_column(Text)
    type_id: Mapped[int] = mapped_column(Integer, ForeignKey(f'{TABLE_NAMES['file_type']}.id'))
    size: Mapped[int] = mapped_column(Integer)
    thumbnail: Mapped[str] = mapped_column(Text)
    message: Mapped["Message"] = relationship(back_populates="file_id")


class FileType(Base):
    __tablename__ = TABLE_NAMES['file_type']
    id: Mapped[int] = mapped_column(primary_key=True)
    type_name: Mapped[str] = mapped_column(Text)
    file: Mapped["File"] = relationship(back_populates="type_id")


# Connecting to the database. Creating a database connection and session
# Подключение к базе данных. Создаем соединение с базой данных и сессию
engine = create_engine(f'sqlite:///{_DATA_BASE_NAME}.db')
session = Session(engine)
# Creating tables in the database if they do not exist
# Создаем таблицы в базе данных, если они отсутствуют
Base.metadata.create_all(engine)

if __name__ == '__main__':
    pass
