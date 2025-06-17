from datetime import datetime
from typing import List, Any
from sqlalchemy import create_engine, Integer, ForeignKey, Text, String, Table, Column
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, Session

import configs.config
from configs.config import ProjectDirs, TableNames


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
    # Relationships to 'Dialog' table
    dialog_id: Mapped[int] = mapped_column(Integer, ForeignKey(f'{TableNames.dialogs}.dialog_id'))
    dialog: Mapped['Dialog'] = relationship(back_populates='groups')
    # Relationships to 'Message' table
    messages: Mapped['Message'] = relationship(back_populates='group')
    # Relationships to 'File' table
    files: Mapped['File'] = relationship(back_populates='group')
    # Relationships to 'Tag' table
    tags: Mapped[List['Tag']] = relationship(secondary=group_tag_links, back_populates='groups')

    def __init__(self, **kw: Any):
        super().__init__(**kw)
        # self.tags = []


class Tag(Base):
    __tablename__ = TableNames.tags
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    tag_name: Mapped[str] = mapped_column(Text)
    # Relationships to 'Group' table
    groups: Mapped[List['Group']] = relationship(secondary=group_tag_links, back_populates='tags')

    def __init__(self, **kw: Any):
        super().__init__(**kw)
        # self.groups = []


class Message(Base):
    __tablename__ = TableNames.messages
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    message_id: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    # Relationships to 'Group' table
    grouped_id: Mapped[str] = mapped_column(String, ForeignKey(f'{TableNames.groups}.grouped_id'))
    group: Mapped['Group'] = relationship(back_populates='messages')

    def __init__(self, **kw: Any):
        super().__init__(**kw)
        # self.group = None


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

    def __init__(self, **kw: Any):
        super().__init__(**kw)
        self.dialog_id = kw.get('dialog_id')
        self.dialog_title = kw.get('dialog_title')
        self.dialog_type = kw.get('dialog_type')


class DialogType(Base):
    __tablename__ = TableNames.dialog_types
    dialog_type_id: Mapped[int] = mapped_column(primary_key=True, unique=True)
    name: Mapped[str] = mapped_column(String, unique=True)
    # Relationships to 'Dialog' table
    dialogs: Mapped['Dialog'] = relationship(back_populates='dialog_type')

    def __init__(self, **kw: Any):
        super().__init__(**kw)


class File(Base):
    __tablename__ = TableNames.files
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    file_path: Mapped[str] = mapped_column(String, unique=True, index=True)
    size: Mapped[int] = mapped_column(Integer, nullable=True)
    # Relationships to 'Group' table
    grouped_id: Mapped[str] = mapped_column(String, ForeignKey(f'{TableNames.groups}.grouped_id'))
    group: Mapped['Group'] = relationship(back_populates='files')
    # Relationships to 'FileType' table
    file_type_id: Mapped[int] = mapped_column(Integer, ForeignKey(f'{TableNames.file_types}.file_type_id'))
    file_type: Mapped['FileType'] = relationship(back_populates='files')

    def __init__(self, **kw: Any):
        super().__init__(**kw)

    @property
    def web_path(self) -> str:
        """
        Returns the web path of the file.
        Возвращает веб-путь файла.
        """
        return self.file_path.replace('\\', '/')


class FileType(Base):
    __tablename__ = TableNames.file_types
    file_type_id: Mapped[int] = mapped_column(primary_key=True)
    type_name: Mapped[str] = mapped_column(String, unique=True)
    web_name: Mapped[str] = mapped_column(String)
    default_ext: Mapped[str] = mapped_column(String, nullable=True)
    sign: Mapped[str] = mapped_column(String, nullable=True)
    # Relationships to 'File' table
    files: Mapped['File'] = relationship(back_populates='file_type')

    def __init__(self, **kw: Any):
        super().__init__(**kw)


class DatabaseHandler:
    """
    A class for handling database operations.
    Класс для обработки операций с базой данных.
    """

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
        for member in configs.config.DialogTypes:
            member_existing = self.session.query(DialogType).filter_by(dialog_type_id=member.value).first()
            if member_existing:
                member_existing.name = member.name
            else:
                self.session.add(DialogType(dialog_type_id=member.value, name=member.name))
        # Проверяем наличие данных в статической таблице с типами файлов и добавляем их при необходимости
        for member in configs.config.MessageFileTypes:
            member_existing = self.session.query(FileType).filter_by(file_type_id=member.type_id).first()
            if member_existing:
                member_existing.type_name = member.name.title()
                member_existing.web_name = member.web_name
                member_existing.default_ext = member.default_ext
                member_existing.sign = member.sign
            else:
                self.session.add(FileType(file_type_id=member.type_id, type_name=member.name, web_name=member.web_name,
                                          default_ext=member.default_ext, sign=member.sign))
        self.session.commit()

    def save_message_group(self, message_group):
        """
        Saves a message group to the database.
        Сохраняет группу сообщений в базе данных.
        """
        pass


# engine = create_engine(f'sqlite:///{ProjectDirs.data_base_file}')
# session = Session(engine)

# init_database()

if __name__ == '__main__':
    pass
