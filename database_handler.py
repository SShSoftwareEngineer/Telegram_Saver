from dataclasses import dataclass
from datetime import datetime
from typing import List, Any, Type, Dict, TypeVar, Optional
from sqlalchemy import create_engine, Integer, ForeignKey, Text, String, Table, Column, select
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, Session

from configs.config import ProjectDirs, TableNames, DialogTypes, MessageFileTypes, date_decode


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
    """
    A class to represent a message group in the database.
    Класс для представления группы сообщений в базе данных.
    """
    __tablename__ = TableNames.message_groups
    # id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    grouped_id: Mapped[str] = mapped_column(String, primary_key=True, unique=True, index=True, nullable=False)
    date: Mapped[datetime]
    text: Mapped[str] = mapped_column(Text, nullable=True)
    truncated_text: Mapped[str] = mapped_column(Text, nullable=True)
    files_report: Mapped[str] = mapped_column(Text, nullable=True)
    from_id: Mapped[int] = mapped_column(Integer, nullable=True)
    reply_to: Mapped[int] = mapped_column(Integer, nullable=True)
    # Relationships to 'DbDialog' table
    dialog_id: Mapped[int] = mapped_column(Integer, ForeignKey(f'{TableNames.dialogs}.dialog_id'))
    dialog: Mapped['DbDialog'] = relationship(back_populates='message_groups')
    # Relationships to 'DbFile' table
    files: Mapped[List['DbFile']] = relationship(back_populates='message_group')
    # Relationships to 'DbTag' table
    tags: Mapped[List['DbTag']] = relationship(secondary=message_group_tag_links, back_populates='message_groups')


class DbTag(Base):
    """
    A class to represent a tag associated with a message group in the database.
    Класс для представления тега, связанного с группой сообщений в базе данных.
    """
    __tablename__ = TableNames.tags
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text)
    # Relationships to 'DbMessageGroup' table
    message_groups: Mapped[List['DbMessageGroup']] = relationship(secondary=message_group_tag_links,
                                                                  back_populates='tags')


class DbDialog(Base):
    """
    A class to represent a dialog (chat) in the database.
    Класс для представления диалога (чата) в базе данных.
    """
    __tablename__ = TableNames.dialogs
    # id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    dialog_id: Mapped[int] = mapped_column(Integer, primary_key=True, unique=True, index=True, nullable=False)
    title: Mapped[str] = mapped_column(Text)
    # Relationships to 'DbMessageGroup' table
    message_groups: Mapped['DbMessageGroup'] = relationship(back_populates='dialog')
    # Relationships to 'DbDialogType' table
    dialog_type_id: Mapped[int] = mapped_column(Integer, ForeignKey(f'{TableNames.dialog_types}.dialog_type_id'))
    dialog_type: Mapped['DbDialogType'] = relationship(back_populates='dialogs')


class DbDialogType(Base):
    """
    A class to represent a type of dialog (chat) in the database.
    Класс для представления типа диалога (чата) в базе данных.
    """
    __tablename__ = TableNames.dialog_types
    dialog_type_id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String, unique=True)
    # Relationships to 'DbDialog' table
    dialogs: Mapped['DbDialog'] = relationship(back_populates='dialog_type')


class DbFile(Base):
    """
    A class to represent a file associated with a message group in the database.
    Класс для представления файла, связанного с группой сообщений в базе данных.
    """
    __tablename__ = TableNames.files
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    message_id: Mapped[int] = mapped_column(Integer)
    file_path: Mapped[str] = mapped_column(String, unique=True)
    size: Mapped[int] = mapped_column(Integer, nullable=True)
    # Relationships to 'DbMessageGroup' table
    grouped_id: Mapped[str] = mapped_column(String, ForeignKey(f'{TableNames.message_groups}.grouped_id'))
    message_group: Mapped['DbMessageGroup'] = relationship(back_populates='files')
    # Relationships to 'DbFileType' table
    file_type_id: Mapped[int] = mapped_column(Integer, ForeignKey(f'{TableNames.file_types}.file_type_id'))
    file_type: Mapped['DbFileType'] = relationship(back_populates='files')


class DbFileType(Base):
    """
    A class to represent a type of file associated with a message group in the database.
    Класс для представления типа файла, связанного с группой сообщений в базе данных.
    """
    __tablename__ = TableNames.file_types
    file_type_id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String, unique=True)
    alt_text: Mapped[str] = mapped_column(String)
    default_ext: Mapped[str] = mapped_column(String)
    sign: Mapped[str] = mapped_column(String)
    # Relationships to 'DbFile' table
    files: Mapped[List['DbFile']] = relationship(back_populates='file_type')


@dataclass
class DbMessageSortFilter:
    """
    A class to represent sorting and filtering of message groups in the database.
    Класс для представления параметров сортировки и фильтра для групп сообщений в базе данных.
    """
    _selected_dialog_list: Optional[List[int]] = None
    _sorting_field = None  # по дате или по диалогу
    _sort_order: bool = False
    _date_from: Optional[datetime] = None
    _date_to: Optional[datetime] = None
    _message_query: Optional[str] = None

    @staticmethod
    def _sort_by_dialog_title(x):
        return x.dialog.title

    @staticmethod
    def _sort_by_date(x):
        return x.date

    @property
    def selected_dialog_list(self) -> Optional[List[int]]:
        """
        Возвращает список выбранных диалогов для фильтрации сообщений
        """
        return self._selected_dialog_list

    @selected_dialog_list.setter
    def selected_dialog_list(self, value: List[int]):
        """
        Возвращает список выбранных диалогов ID для фильтрации сообщений
        """
        if value:
            self._selected_dialog_list = value
        else:
            self._selected_dialog_list = None

    @property
    def sorting_field(self):
        """
        Возвращает поле, по которому сортируются сообщения
        """
        return self._sorting_field

    @sorting_field.setter
    def sorting_field(self, value: str):
        """
        Устанавливает поле сортировки
        """
        self._sorting_field = self._sort_by_dialog_title if value == '0' else self._sort_by_date

    @property
    def sort_order(self) -> bool:
        """
        Возвращает порядок сортировки сообщений по заданному полю
        """
        return self._sort_order

    @sort_order.setter
    def sort_order(self, value: str):
        """
        Устанавливает порядок сортировки сообщений по заданному полю
        """
        self._sort_order = False if value == '0' else True

    @property
    def date_from(self) -> Optional[datetime]:
        """
        Возвращает дату, с которой получать сообщения
        """
        return self._date_from

    @date_from.setter
    def date_from(self, value: str):
        """
        Устанавливает дату, с которой получать сообщения
        """
        self._date_from = date_decode(value)

    @property
    def date_to(self) -> Optional[datetime]:
        """
        Возвращает дату, до которой получать сообщения
        """
        return self._date_to

    @date_to.setter
    def date_to(self, value: str):
        """
        Устанавливает дату, до которой получать сообщения
        """
        self._date_to = date_decode(value)

    @property
    def message_query(self) -> Optional[str]:
        """
        Возвращает фильтр по тексту сообщений
        """
        return self._message_query

    @message_query.setter
    def message_query(self, value: str):
        """
        Устанавливает фильтр по тексту сообщений
        """
        self._message_query = value if value else None

    # def sort_message_group_list(self, message_group_list: List[TgMessageGroup]) -> List[TgMessageGroup]:
    #     """
    #     Сортировка списка групп сообщений по дате
    #     """
    #     result = sorted(message_group_list, key=lambda group: group.date, reverse=self.sort_order)
    #     return result


class DbCurrentState:
    """
    Текущее состояние клиента базы данных.
    """
    dialog_list: List[DbDialog] = None
    selected_dialog_id: int = None
    message_group_list: List[DbMessageGroup] = None
    selected_message_group: DbMessageGroup = None
    message_group_files: Dict[str, Dict[str, Any]] = None


class DatabaseHandler:
    """
    A class to represent handle database operations.
    Класс для представления операций с базой данных.
    """

    all_dialogues_list: List[DbDialog] = None
    message_sort_filter: DbMessageSortFilter = DbMessageSortFilter()
    current_state: DbCurrentState = DbCurrentState()

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
            self.session.flush()  # Flush to get the ID if it's an autoincrement field
        return existing

    def __init__(self):
        """
        Initializes the database handler by creating an engine, a session, and the necessary tables.
        Инициализирует обработчик базы данных, создавая движок, сессию и необходимые таблицы.
        """
        self.engine = create_engine(f'sqlite:///{ProjectDirs.data_base_file}')
        self.session = Session(self.engine)
        # Creating tables in the database if they do not exist
        # Создаем таблицы в базе данных, если они отсутствуют
        Base.metadata.create_all(self.engine)
        # Проверяем наличие данных в статической таблице с типами диалогов и добавляем их при необходимости
        for dialog_type in DialogTypes:
            self.upsert_record(DbDialogType, dict(dialog_type_id=dialog_type.value),
                               dict(name=dialog_type.name))
        # Проверяем наличие данных в статической таблице с типами файлов и добавляем их при необходимости
        for file_type in MessageFileTypes:
            self.upsert_record(DbFileType, dict(file_type_id=file_type.type_id),
                               dict(name=file_type.name, alt_text=file_type.alt_text,
                                    default_ext=file_type.default_ext, sign=file_type.sign))
        self.session.commit()
        # Получаем список диалогов из базы данных
        self.all_dialogues_list = self.get_db_dialog_list()
        # Устанавливаем текущее состояние клиента базы данных
        self.current_state.dialog_list = list(self.all_dialogues_list)
        self.current_state.message_group_list = []


    def get_db_dialog_list(self) -> List[DbDialog]:
        """
        Получение списка диалогов, имеющихся в БД с учетом фильтров и сортировки
        """
        dialogs = self.session.execute(select(DbDialog)).scalars().all()
        dialog_list = []
        for db_dialog in dialogs:
            dialog_list.append(db_dialog)
        print(f'{len(dialog_list)} chats loaded from the database')
        return sorted(dialog_list, key=lambda x: x.title)

    def get_message_group_list(self) -> list[DbMessageGroup]:
        """
        Получение списка групп сообщений с учетом фильтров и сортировки
        """
        stmt = select(DbMessageGroup)
        if self.message_sort_filter.selected_dialog_list:
            stmt = stmt.where(DbMessageGroup.dialog_id.in_(self.message_sort_filter.selected_dialog_list))
        if self.message_sort_filter.date_from:
            stmt = stmt.where(DbMessageGroup.date >= self.message_sort_filter.date_from)
        if self.message_sort_filter.date_to:
            stmt = stmt.where(DbMessageGroup.date <= self.message_sort_filter.date_to)
        if self.message_sort_filter.message_query:
            stmt = stmt.where(DbMessageGroup.text.ilike(f'%{self.message_sort_filter.message_query}%'))
        query_result = self.session.execute(stmt).scalars().all()
        print(f'{len(query_result)} messages loaded from the database')
        return sorted(query_result, key=self.message_sort_filter.sorting_field,
                      reverse=self.message_sort_filter.sort_order)

    # def get_message_detail(self, dialog_id: int, message_group_id: str) -> DbDetails:
    #     """
    #     Получение сообщения по id диалога и id группы сообщений
    #     """
    #     # Получаем текущую группу сообщений по id
    #     current_message_group = self.get_message_group_by_id(self.current_state.message_group_list, message_group_id)
    #     message_date_str = current_message_group.date.strftime(ProjectConst.message_datetime_format)
    #     print(f'Message {message_date_str} details loading...')
    #     tg_details = TgDetails(dialog_id=dialog_id,
    #                            dialog_title=self.get_dialog_by_id(dialog_id).title,
    #                            message_group_id=message_group_id,
    #                            date=current_message_group.date,
    #                            text=current_message_group.text if current_message_group.text else '',
    #                            files=current_message_group.files,
    #                            files_report=current_message_group.files_report if current_message_group.files_report else '',
    #                            saved_to_db=current_message_group.saved_to_db)
    #     # Преобразование текстовых гиперссылок вида [Text](URL) в HTML формат
    #     tg_details.text = convert_text_hyperlinks(tg_details.text)
    #     # Скачиваем файлы, содержащиеся в детальном сообщении, если их нет в файловой системе
    #     for tg_file in tg_details.files:
    #         if not tg_file.is_exists():
    #             if tg_file.file_type != MessageFileTypes.VIDEO:
    #                 print(f'Downloading file {tg_file.file_path}...')
    #                 self.download_message_file(tg_file)
    #     tg_details.existing_files = [tg_file for tg_file in tg_details.files if tg_file.is_exists()]
    #     print('Message details loaded')
    #     return tg_details


if __name__ == '__main__':
    pass
