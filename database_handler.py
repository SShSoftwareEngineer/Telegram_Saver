from datetime import datetime
from typing import List, Any, Type, Dict, TypeVar
from sqlalchemy import create_engine, Integer, ForeignKey, Text, String, Table, Column
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, Session

import configs.config
from configs.config import ProjectDirs, TableNames


class Base(DeclarativeBase):
    """ A declarative class for creating tables in the database """


# TypeVar for model classes, bound to Base
ModelType = TypeVar('ModelType', bound=Base)

# Relationships Many-to-Many to 'MessageGroup', 'DbTag' tables
message_group_tag_links = Table(
    TableNames.message_group_tag_links, Base.metadata,
    Column('message_group_id', ForeignKey(f'{TableNames.message_groups}.grouped_id'), primary_key=True),
    Column('tag_id', ForeignKey(f'{TableNames.tags}.id'), primary_key=True)
)


class DbMessageGroup(Base):
    __tablename__ = TableNames.message_groups
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    grouped_id: Mapped[str] = mapped_column(String, unique=True, index=True)
    date_time: Mapped[datetime]
    text: Mapped[str] = mapped_column(Text, nullable=True)
    truncated_text: Mapped[str] = mapped_column(Text, nullable=True)
    files_report: Mapped[str] = mapped_column(Text, nullable=True)
    from_id: Mapped[int] = mapped_column(Integer, nullable=True)
    reply_to: Mapped[int] = mapped_column(Integer, nullable=True)
    # Relationships to 'DbDialog' table
    dialog_id: Mapped[int] = mapped_column(Integer, ForeignKey(f'{TableNames.dialogs}.dialog_id'))
    dialog: Mapped['DbDialog'] = relationship(back_populates='message_groups')
    # Relationships to 'DbFile' table
    files: Mapped['DbFile'] = relationship(back_populates='message_group')
    # Relationships to 'DbTag' table
    tags: Mapped[List['DbTag']] = relationship(secondary=message_group_tag_links, back_populates='message_groups')


class DbTag(Base):
    __tablename__ = TableNames.tags
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text)
    # Relationships to 'DbMessageGroup' table
    message_groups: Mapped[List['DbMessageGroup']] = relationship(secondary=message_group_tag_links,
                                                                  back_populates='tags')


class DbDialog(Base):
    __tablename__ = TableNames.dialogs
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    dialog_id: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    title: Mapped[str] = mapped_column(Text)
    # Relationships to 'DbMessageGroup' table
    message_groups: Mapped['DbMessageGroup'] = relationship(back_populates='dialog')
    # Relationships to 'DbDialogType' table
    dialog_type_id: Mapped[int] = mapped_column(Integer, ForeignKey(f'{TableNames.dialog_types}.type_id'))
    dialog_type: Mapped['DbDialogType'] = relationship(back_populates='dialogs')


class DbDialogType(Base):
    __tablename__ = TableNames.dialog_types
    type_id: Mapped[int] = mapped_column(primary_key=True, unique=True)
    name: Mapped[str] = mapped_column(String, unique=True)
    # Relationships to 'DbDialog' table
    dialogs: Mapped['DbDialog'] = relationship(back_populates='dialog_type')


class DbFile(Base):
    __tablename__ = TableNames.files
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    message_id: Mapped[int] = mapped_column(Integer)
    file_path: Mapped[str] = mapped_column(String, unique=True)
    size: Mapped[int] = mapped_column(Integer, nullable=True)
    # Relationships to 'DbMessageGroup' table
    grouped_id: Mapped[str] = mapped_column(String, ForeignKey(f'{TableNames.message_groups}.grouped_id'))
    message_group: Mapped['DbMessageGroup'] = relationship(back_populates='files')
    # Relationships to 'DbFileType' table
    file_type_id: Mapped[int] = mapped_column(Integer, ForeignKey(f'{TableNames.file_types}.type_id'))
    file_type: Mapped['DbFileType'] = relationship(back_populates='files')


class DbFileType(Base):
    __tablename__ = TableNames.file_types
    type_id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String, unique=True)
    alt_text: Mapped[str] = mapped_column(String)
    default_ext: Mapped[str] = mapped_column(String)
    sign: Mapped[str] = mapped_column(String)
    # Relationships to 'DbFile' table
    files: Mapped['DbFile'] = relationship(back_populates='file_type')


class DatabaseHandler:
    """
    A class for handling database operations.
    Класс для обработки операций с базой данных.
    """

    def upsert_record(self, model_class: Type[ModelType],
                      filter_fields: Dict[str, Any],
                      update_fields: Dict[str, Any]) -> ModelType:
        """
        Универсальная функция для поиска и обновления/создания записи в любой модели БД
        """
        # Проверяем запись на существование
        existing = self.session.query(model_class).filter_by(**filter_fields).first()
        if existing:
            # Обновляем существующую запись
            for key, value in update_fields.items():
                setattr(existing, key, value)
        else:
            # Создаем новую запись
            existing = model_class(**{**filter_fields, **update_fields})
            self.session.add(existing)
        return existing

    def __init__(self):
        """
        Initializes the database handler by creating an engine, a session, and the necessary tables.
        This function is called when the module is imported.
        Инициализирует обработчик базы данных, создавая движок, сессию и необходимые таблицы.
        Эта функция вызывается при импорте модуля.
        """
        self.engine = create_engine(f'sqlite:///{ProjectDirs.data_base_file}')
        self.session = Session(self.engine)
        # Creating tables in the database if they do not exist
        # Создаем таблицы в базе данных, если они отсутствуют
        Base.metadata.create_all(self.engine)
        # Проверяем наличие данных в статической таблице с типами диалогов и добавляем их при необходимости
        for dialog_type in configs.config.DialogTypes:
            self.upsert_record(DbDialogType, {'type_id': dialog_type.value}, {'name': dialog_type.name})
        # Проверяем наличие данных в статической таблице с типами файлов и добавляем их при необходимости
        for file_type in configs.config.MessageFileTypes:
            self.upsert_record(DbFileType, {'type_id': file_type.type_id},
                               {'name': file_type.name, 'alt_text': file_type.alt_text,
                                'default_ext': file_type.default_ext, 'sign': file_type.sign})
        self.session.commit()


if __name__ == '__main__':
    pass
