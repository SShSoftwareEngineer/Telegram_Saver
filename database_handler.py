from datetime import datetime
from sqlalchemy import create_engine, Integer, ForeignKey, Text, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, Session

from config.config import ProjectDirs, ProjectConst, TableNames, DialogTypes


class Base(DeclarativeBase):
    """ A declarative class for creating tables in the database """


class Group(Base):
    __tablename__ = TableNames.groups
    id: Mapped[int] = mapped_column(primary_key=True)
    grouped_id: Mapped[str] = mapped_column(String, unique=True, index=True)
    date_time: Mapped[datetime]
    text: Mapped[str] = mapped_column(Text, nullable=True)
    # Relationships to 'Messages' table
    messages: Mapped['Message'] = relationship(back_populates='group')
    # Relationships to 'Dialogs' table
    dialog_id: Mapped[int] = mapped_column(Integer, ForeignKey(f'{TableNames.dialogs}.dialog_id'))
    dialog: Mapped['Dialog'] = relationship(back_populates='groups')
    # Relationships to 'Files' table
    files: Mapped['File'] = relationship(back_populates='group')

    # tag_messages: Mapped[List['TagMessage']] = relationship('TagMessage', back_populates='message')
    #
    # @property
    # def tags(self):
    #     return [tm.tag for tm in self.tag_messages]


class Message(Base):
    __tablename__ = TableNames.messages
    id: Mapped[int] = mapped_column(primary_key=True)
    message_id: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    from_user: Mapped[str] = mapped_column(Text, nullable=True)
    # Relationships to 'Groups' table
    grouped_id: Mapped[int] = mapped_column(Integer, ForeignKey(f'{TableNames.groups}.grouped_id'))
    group: Mapped['Group'] = relationship(back_populates='messages')


class Dialog(Base):
    __tablename__ = TableNames.dialogs
    id: Mapped[int] = mapped_column(primary_key=True)
    dialog_id: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    dialog_title: Mapped[str] = mapped_column(Text)
    # Relationships to 'Groups' table
    groups: Mapped['Group'] = relationship(back_populates='dialog')
    # Relationships to 'DialogTypes' table
    dialog_type_id: Mapped[int] = mapped_column(Integer, ForeignKey(f'{TableNames.dialog_types}.dialog_type_id'))
    dialog_type: Mapped['DialogType'] = relationship(back_populates='dialogs')


class DialogType(Base):
    __tablename__ = TableNames.dialog_types
    id: Mapped[int] = mapped_column(primary_key=True)
    dialog_type_id: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    name: Mapped[str] = mapped_column(String, unique=True)
    # Relationships to 'Dialogs' table
    dialogs: Mapped['Dialog'] = relationship(back_populates='dialog_type')


class File(Base):
    __tablename__ = TableNames.files
    id: Mapped[int] = mapped_column(primary_key=True)
    file_path: Mapped[str] = mapped_column(String, unique=True, index=True)
    web_path: Mapped[str] = mapped_column(String, unique=True, index=True)
    size: Mapped[int] = mapped_column(Integer, nullable=True)
    # Relationships to 'Groups' table
    grouped_id: Mapped[int] = mapped_column(Integer, ForeignKey(f'{TableNames.groups}.grouped_id'))
    group: Mapped['Group'] = relationship(back_populates='files')
    # Relationships to 'FileTypes' table
    file_type_id: Mapped[int] = mapped_column(Integer, ForeignKey(f'{TableNames.file_types}.file_type_id'))
    file_type: Mapped['FileType'] = relationship(back_populates='files')


class FileType(Base):
    __tablename__ = TableNames.file_types
    id: Mapped[int] = mapped_column(primary_key=True)
    file_type_id: Mapped[int] = mapped_column(Integer)
    type_name: Mapped[str] = mapped_column(String, unique=True)
    default_extension: Mapped[str] = mapped_column(String, nullable=True)
    signature: Mapped[str] = mapped_column(String, nullable=True)
    # Relationships to 'Files' table
    files: Mapped['File'] = relationship(back_populates='file_type')


#
# class Tag(Base):
#     __tablename__ = TableNames.tags
#     id: Mapped[int] = mapped_column(primary_key=True)
#     tag_name: Mapped[str] = mapped_column(Text)
#     tag_messages: Mapped[List['TagMessage']] = relationship('TagMessage', back_populates='tag')
#
#     @property
#     def messages(self):
#         return [tm.message for tm in self.tag_messages]
#
#
# class TagMessage(Base):
#     __tablename__ = TableNames.tags_messages
#     tag_id: Mapped[int] = mapped_column(Integer, ForeignKey(f'{TableNames.tags}.id'), primary_key=True)
#     message_id: Mapped[int] = mapped_column(Integer, ForeignKey(f'{TableNames.messages}.id'), primary_key=True)
#     tag: Mapped['Tag'] = relationship('Tag', back_populates=TableNames.tags_messages)
#     message: Mapped['Message'] = relationship('Message', back_populates=TableNames.tags_messages)
#


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
    if not session.query(DialogType).first():
        for member in DialogTypes:
            session.merge(DialogType(dialog_type_id=member.value, name=member.name))
        session.commit()


engine = create_engine(f'sqlite:///{ProjectDirs.data_base_name}.db')
session = Session(engine)

init_database()

if __name__ == '__main__':
    pass
