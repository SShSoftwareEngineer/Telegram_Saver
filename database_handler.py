from datetime import datetime
from typing import List

from sqlalchemy import create_engine, Integer, ForeignKey, Text, String, Table, Column
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, Session

from config.config import ProjectDirs, TableNames, DialogTypes, MessageFileTypes


class Base(DeclarativeBase):
    """ A declarative class for creating tables in the database """


# Relationships Many-to-Many to 'Group', 'Tag' tables
group_tag_links = Table(
    TableNames.group_tag_links, Base.metadata,
    Column('group_id', ForeignKey(f'{TableNames.groups}.grouped_id'), primary_key=True),
    Column('tag_id', ForeignKey(f'{TableNames.tags}.id'), primary_key=True)
)


class Group(Base):
    __tablename__ = TableNames.groups
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    grouped_id: Mapped[str] = mapped_column(String, unique=True, index=True)
    date_time: Mapped[datetime]
    text: Mapped[str] = mapped_column(Text, nullable=True)
    # Relationships to 'Message' table
    messages: Mapped['Message'] = relationship(back_populates='group')
    # Relationships to 'Dialog' table
    dialog_id: Mapped[int] = mapped_column(Integer, ForeignKey(f'{TableNames.dialogs}.dialog_id'))
    dialog: Mapped['Dialog'] = relationship(back_populates='groups')
    # Relationships to 'File' table
    files: Mapped['File'] = relationship(back_populates='group')
    # Relationships to 'Tag' table
    tags: Mapped[List['Tag']] = relationship(secondary=group_tag_links, back_populates='groups')


class Tag(Base):
    __tablename__ = TableNames.tags
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    tag_name: Mapped[str] = mapped_column(Text)
    # Relationships to 'Group' table
    groups: Mapped[List['Group']] = relationship(secondary=group_tag_links, back_populates='tags')


class Message(Base):
    __tablename__ = TableNames.messages
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    message_id: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    from_user: Mapped[str] = mapped_column(Text, nullable=True)
    # Relationships to 'Group' table
    grouped_id: Mapped[int] = mapped_column(Integer, ForeignKey(f'{TableNames.groups}.grouped_id'))
    group: Mapped['Group'] = relationship(back_populates='messages')


class Dialog(Base):
    __tablename__ = TableNames.dialogs
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    dialog_id: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    dialog_title: Mapped[str] = mapped_column(Text)
    # Relationships to 'Group' table
    groups: Mapped['Group'] = relationship(back_populates='dialog')
    # Relationships to 'DialogType' table
    dialog_type_id: Mapped[int] = mapped_column(Integer, ForeignKey(f'{TableNames.dialog_types}.dialog_type_id'))
    dialog_type: Mapped['DialogType'] = relationship(back_populates='dialogs')


class DialogType(Base):
    __tablename__ = TableNames.dialog_types
    dialog_type_id: Mapped[int] = mapped_column(primary_key=True, unique=True)
    name: Mapped[str] = mapped_column(String, unique=True)
    # Relationships to 'Dialog' table
    dialogs: Mapped['Dialog'] = relationship(back_populates='dialog_type')


class File(Base):
    __tablename__ = TableNames.files
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    file_path: Mapped[str] = mapped_column(String, unique=True, index=True)
    web_path: Mapped[str] = mapped_column(String, unique=True, index=True)
    size: Mapped[int] = mapped_column(Integer, nullable=True)
    # Relationships to 'Group' table
    grouped_id: Mapped[int] = mapped_column(Integer, ForeignKey(f'{TableNames.groups}.grouped_id'))
    group: Mapped['Group'] = relationship(back_populates='files')
    # Relationships to 'FileType' table
    file_type_id: Mapped[int] = mapped_column(Integer, ForeignKey(f'{TableNames.file_types}.file_type_id'))
    file_type: Mapped['FileType'] = relationship(back_populates='files')


class FileType(Base):
    __tablename__ = TableNames.file_types
    file_type_id: Mapped[int] = mapped_column(primary_key=True)
    type_name: Mapped[str] = mapped_column(String, unique=True)
    web_name: Mapped[str] = mapped_column(String)
    default_ext: Mapped[str] = mapped_column(String, nullable=True)
    sign: Mapped[str] = mapped_column(String, nullable=True)
    # Relationships to 'File' table
    files: Mapped['File'] = relationship(back_populates='file_type')


def init_database():
    """
    Initializes the database by creating the necessary tables.
    This function is called when the module is imported.
    Инициализирует базу данных, создавая необходимые таблицы.
    Эта функция вызывается при импорте модуля.
    """
    # Creating tables in the database if they do not exist
    # Создаем таблицы в базе данных, если они отсутствуют
    Base.metadata.create_all(engine)
    # Проверяем наличие данных в статической таблице с типами диалогов и добавляем их при необходимости
    for member in DialogTypes:
        member_existing = session.query(DialogType).filter_by(dialog_type_id=member.value).first()
        if member_existing:
            member_existing.name = member.name
        else:
            session.add(DialogType(dialog_type_id=member.value, name=member.name))
    # Проверяем наличие данных в статической таблице с типами файлов и добавляем их при необходимости
    for member in MessageFileTypes:
        member_existing = session.query(FileType).filter_by(file_type_id=member.type_id).first()
        if member_existing:
            member_existing.type_name = member.name.title()
            member_existing.web_name = member.web_name
            member_existing.default_ext = member.default_ext
            member_existing.sign = member.sign
        else:
            session.add(FileType(file_type_id=member.type_id, type_name=member.name, web_name=member.web_name,
                                 default_ext=member.default_ext, sign=member.sign))
    session.commit()


engine = create_engine(f'sqlite:///{ProjectDirs.data_base_name}.db')
session = Session(engine)

init_database()

if __name__ == '__main__':
    pass
