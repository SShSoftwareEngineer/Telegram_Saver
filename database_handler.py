"""
The module contains model classes, functions, and constants for working with an SQLite database using SQLAlchemy.

class DatabaseHandler:a class to represent handle database operations.
class Base(DeclarativeBase): a declarative class for creating tables in the database
class DbDialog(Base): a class to represent a dialog (chat) in the database.
class DbDialogType(Base): a class to represent a type of dialog (chat) in the database.
class DbFile(Base): a class to represent a file associated with a message group in the database.
class DbFileType(Base): a class to represent a type of file associated with a message group in the database.
class DbMessageGroup(Base): a class to represent a message group in the database.
class DbTag(Base): a class to represent a tag associated with a message group in the database.
class DbCurrentState: a class representing the current state of the database client
class DbMessageSortFilter:a class to represent sorting and filtering of message groups in the database.
db_handler: an object of the DatabaseHandler class for working with the database
message_group_tag_links: a relationship table for many-to-many relationship between message groups and tags
ModelType: a TypeVar for model classes, bound to Base
"""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Any, Type, TypeVar  # , Dict, Optional
from sqlalchemy import create_engine, Integer, ForeignKey, Text, String, Table, Column, select, asc, desc, or_, \
    Boolean, update, delete, event, func, Select
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, Session
from configs.config import ProjectDirs, GlobalConst, TableNames, DialogTypes, MessageFileTypes, TagsSorting
from utils import parse_date_string, status_messages


class Base(DeclarativeBase):  # pylint: disable=too-few-public-methods
    """
    A declarative class for creating tables in the database
    Декларативный класс для создания таблиц в базе данных
    """


# TypeVar for model classes, bound to Base
ModelType = TypeVar('ModelType', bound=Base)  # pylint: disable=invalid-name

# Table implementing a many-to-many relationship between the MessageGroup and DbTag tables
# Таблица, реализующая отношение «многие-ко-многим» к таблицам «MessageGroup» и «DbTag»
message_group_tag_links = Table(
    TableNames.message_group_tag_links, Base.metadata,
    Column('message_group_id', String,
           ForeignKey(f'{TableNames.message_groups}.grouped_id'), primary_key=True),
    Column('tag_id', Integer,
           ForeignKey(f'{TableNames.tags}.id'), primary_key=True)
)


class DbMessageGroup(Base):  # pylint: disable=too-few-public-methods
    """
    A class to represent a message group in the database.
    Класс для представления группы сообщений в базе данных.
    """

    __tablename__ = TableNames.message_groups  # Table name in the database / Имя таблицы в базе данных
    grouped_id: Mapped[str] = mapped_column(String, primary_key=True, unique=True, index=True, nullable=False)
    date: Mapped[datetime]
    text: Mapped[str] = mapped_column(Text, nullable=True)
    truncated_text: Mapped[str] = mapped_column(Text, nullable=True)
    files_report: Mapped[str] = mapped_column(Text, nullable=True)
    from_id: Mapped[int] = mapped_column(Integer, nullable=True)
    selected: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Relationships to 'DbDialog' table
    dialog_id: Mapped[int] = mapped_column(Integer, ForeignKey(f'{TableNames.dialogs}.dialog_id'))
    dialog: Mapped['DbDialog'] = relationship(back_populates='message_groups')
    # Relationships to 'DbFile' table
    files: Mapped[List['DbFile']] = relationship(back_populates='message_group', cascade="all, delete-orphan")
    # Relationships to 'DbTag' table
    tags: Mapped[List['DbTag']] = relationship(secondary=message_group_tag_links, back_populates='message_groups')

    def get_export_data(self) -> dict:
        """
        Returns message group data as a dictionary for export to HTML or JSON
        Возвращает данные группы сообщений в виде словаря для экспорта в HTML или JSON
        """

        export_data = {'dialog_id': self.dialog_id,
                       'dialog_title': self.dialog.title if self.dialog else '',
                       'message_group_id': self.grouped_id,
                       'date': self.date.strftime(GlobalConst.message_datetime_format) if self.date else '',
                       'text': self.text if self.text else '',
                       'from_id': self.from_id,
                       'files': [{'file_path': db_file.file_path,
                                  'alt_text': db_file.file_type.alt_text,
                                  'type_name': db_file.file_type.name if db_file.file_type else ''}
                                 for db_file in self.files] if self.files else [],
                       'tags': [db_tag.name for db_tag in self.tags] if self.tags else []
                       }
        return export_data


class DbTag(Base):  # pylint: disable=too-few-public-methods
    """
    A class to represent a tag associated with a message group in the database.
    Класс для представления тега, связанного с группой сообщений в базе данных.
    """

    __tablename__ = TableNames.tags  # Table name in the database / Имя таблицы в базе данных
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, index=True)
    name: Mapped[str] = mapped_column(Text, default='', nullable=False)
    usage_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(default=datetime.now)
    # Relationships to 'DbMessageGroup' table
    message_groups: Mapped[List['DbMessageGroup']] = relationship(secondary=message_group_tag_links,
                                                                  back_populates='tags')


class DbDialog(Base):  # pylint: disable=too-few-public-methods
    """
    A class to represent a dialog (chat) in the database.
    Класс для представления диалога (чата) в базе данных.
    """

    __tablename__ = TableNames.dialogs  # Table name in the database / Имя таблицы в базе данных
    dialog_id: Mapped[int] = mapped_column(Integer, primary_key=True, unique=True, index=True, nullable=False)
    title: Mapped[str] = mapped_column(Text)
    # Relationships to 'DbMessageGroup' table
    message_groups: Mapped['DbMessageGroup'] = relationship(back_populates='dialog')
    # Relationships to 'DbDialogType' table
    dialog_type_id: Mapped[int] = mapped_column(Integer, ForeignKey(f'{TableNames.dialog_types}.dialog_type_id'))
    dialog_type: Mapped['DbDialogType'] = relationship(back_populates='dialogs')


class DbDialogType(Base):  # pylint: disable=too-few-public-methods
    """
    A class to represent a type of dialog (chat) in the database.
    Класс для представления типа диалога (чата) в базе данных.
    """

    __tablename__ = TableNames.dialog_types  # Table name in the database / Имя таблицы в базе данных
    dialog_type_id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String, unique=True)
    # Relationships to 'DbDialog' table
    dialogs: Mapped['DbDialog'] = relationship(back_populates='dialog_type')


class DbFile(Base):  # pylint: disable=too-few-public-methods
    """
    A class to represent a file associated with a message group in the database.
    Класс для представления файла, связанного с группой сообщений в базе данных.
    is_exists: Check for the existing file in the file system
    """

    __tablename__ = TableNames.files  # Table name in the database / Имя таблицы в базе данных
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, index=True)
    message_id: Mapped[int] = mapped_column(Integer)
    file_path: Mapped[str] = mapped_column(String, unique=True)
    size: Mapped[int] = mapped_column(Integer, nullable=True)
    # Relationships to 'DbMessageGroup' table
    grouped_id: Mapped[str] = mapped_column(String,
                                            ForeignKey(f'{TableNames.message_groups}.grouped_id', ondelete='CASCADE'))
    message_group: Mapped['DbMessageGroup'] = relationship(back_populates='files')
    # Relationships to 'DbFileType' table
    file_type_id: Mapped[int] = mapped_column(Integer, ForeignKey(f'{TableNames.file_types}.file_type_id'))
    file_type: Mapped['DbFileType'] = relationship(back_populates='files')

    def is_exists(self) -> bool:
        """
        Check for the existing file in the file system
        Проверка на существование файла в файловой системе
        """
        return (Path(ProjectDirs.media_dir) / self.file_path).exists() if self.file_path else False


class DbFileType(Base):  # pylint: disable=too-few-public-methods
    """
    A class to represent a type of file associated with a message group in the database.
    Класс для представления типа файла, связанного с группой сообщений в базе данных.
    """

    __tablename__ = TableNames.file_types  # Table name in the database / Имя таблицы в базе данных
    file_type_id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String, unique=True)
    alt_text: Mapped[str] = mapped_column(String)
    default_ext: Mapped[str] = mapped_column(String)
    sign: Mapped[str] = mapped_column(String)
    # Relationships to 'DbFile' table
    files: Mapped[List['DbFile']] = relationship(back_populates='file_type')


# noinspection PyUnresolvedReferences
@dataclass
class DbMessageSortFilter:  # pylint: disable=too-many-instance-attributes
    """
    A class to represent sorting and filtering of message groups in the database.
    Класс для представления параметров сортировки и фильтра для групп сообщений в базе данных.
    Attributes:
        selected_dialog_list (Optional[List[int]]): list of selected dialog IDs for filtering messages
        sorting_field (str): field to sort messages by (date or dialog)
        sort_order (bool): sort order: descending (True) or ascending (False)
        date_from (Optional[datetime]): date from which to get messages
        date_to (Optional[datetime]): date to which to get messages
        message_query (Optional[str]): filter by message text
        tag_query (Optional[List[str]]): filter by message tags
    """

    _selected_dialog_list: Optional[List[int]] = None
    _sorting_field = None
    _sort_order: bool = False
    _date_from: Optional[datetime] = None
    _date_to: Optional[datetime] = None
    _message_query: Optional[str] = None
    _tag_query: Optional[List[str]] = None
    sort_by_date: str = 'by date'
    sort_by_title: str = 'by title'

    @property
    def selected_dialog_list(self) -> Optional[List[int]]:
        """
        Returns a list of selected dialogs for filtering messages by dialogs
        Возвращает список выбранных диалогов для фильтрации сообщений по диалогам
        """
        return self._selected_dialog_list

    @selected_dialog_list.setter
    def selected_dialog_list(self, value: List[int]):
        """
        Sets the list of selected dialogs for filtering messages by dialogs
        Задает список выбранных диалогов для фильтрации сообщений по диалогам
        Attributes:
            value (List[int]): selected dialog IDs
        """
        if value:
            self._selected_dialog_list = value
        else:
            self._selected_dialog_list = None

    @property
    def sorting_field(self):
        """
        Returns the field by which messages are sorted
        Возвращает поле, по которому сортируются сообщения
        """
        return self._sorting_field

    @sorting_field.setter
    def sorting_field(self, value: str):
        """
        Sets the field by which messages are sorted
        Задает поле, по которому сортируются сообщения
        """
        self._sorting_field = self.sort_by_date if value == '0' else self.sort_by_title

    @property
    def sort_order(self) -> bool:
        """
        Returns the sort order of messages by a specified field
        Возвращает порядок сортировки сообщений по заданному полю
        Return:
            bool: sort order
        """
        return self._sort_order

    @sort_order.setter
    def sort_order(self, value: str):
        """
        Sets the order of sorting messages by a specified field
        Устанавливает порядок сортировки сообщений по заданному полю
        Attributes:
            value (str): form data
        """
        self._sort_order = value != '0'  # False if value == '0' else True

    @property
    def date_from(self) -> Optional[datetime]:
        """
        Returns the date from which to receive messages
        Возвращает дату, с которой получать сообщения
        Return:
            Optional[datetime]: date from which to receive messages
        """
        return self._date_from

    @date_from.setter
    def date_from(self, value: str):
        """
        Sets the date from which to receive messages
        Устанавливает дату, с которой получать сообщения
        Attributes:
            value (str): form data
        """
        self._date_from = parse_date_string(value)

    @property
    def date_to(self) -> Optional[datetime]:
        """
        Returns the date until which messages should be received
        Возвращает дату, до которой получать сообщения
        Return:
            Optional[datetime]: date until which messages should be received
        """
        return self._date_to

    @date_to.setter
    def date_to(self, value: str):
        """
        Sets the date until which to receive messages
        Устанавливает дату, до которой получать сообщения
        Attributes:
            value (str): form data
        """
        self._date_to = parse_date_string(value)

    @property
    def message_query(self) -> Optional[str]:
        """
        Returns a filter by message text
        Возвращает фильтр по тексту сообщений
        Return:
            Optional[str]: message text fragment
        """
        return self._message_query

    @message_query.setter
    def message_query(self, value: str):
        """
        Sets a filter by message text
        Устанавливает фильтр по тексту сообщений
        Attributes:
            value (str): form data
        """
        self._message_query = value if value else None

    @property
    def tag_query(self) -> Optional[List[str]]:
        """
        Returns a list of filters by message tags
        Возвращает список фильтров по тегам сообщений
        Return:
            Optional[List[str]]: message tag fragments
        """
        return self._tag_query

    @tag_query.setter
    def tag_query(self, value: str):
        """
        Sets a list of filters by message tags
        Устанавливает список фильтров по тегам сообщений
        Attributes:
            value (str): form data
        """
        self._tag_query = [tag.strip() for tag in value.split(GlobalConst.tag_filter_separator)] if value else None


@dataclass
class DbCurrentState:
    """
    A class representing the current state of the database client
    Класс, содержащий текущее состояние клиента базы данных.
    Attributes:
        dialog_list (list[DbDialog]): dialog list
        message_group_list (list[DbMessageGroup]): message group list
        selected_message_group_id (str): selected message group ID
        message_details (dict[str, Any]): selected message details
        all_tags_list_sorting (dict): sorting options for the list of all tags
    """

    dialog_list: list[DbDialog] = field(default_factory=list)
    message_group_list: list[DbMessageGroup] = field(default_factory=list)
    selected_message_group_id: str = ''
    message_details: dict[str, Any] = field(default_factory=dict)
    all_tags_list_sorting: dict = field(
        default_factory=lambda: TagsSorting.NAME_ASC.copy())  # pylint: disable=unnecessary-lambda


class DatabaseHandler:
    """
    A class to represent handle database operations.
    Класс для представления операций с базой данных.
    Attributes:
        all_dialogues_list (Optional[List[DbDialog]]): list of all database dialogs
        all_tags_list (Optional[List[DbTag]]): list of all database tags
        message_sort_filter (DbMessageSortFilter): current message filter
        current_state (DbCurrentState): current state of the database
    """

    all_dialogues_list: List[DbDialog] | None = None
    all_tags_list: List[DbTag] | None = None
    message_sort_filter: DbMessageSortFilter = DbMessageSortFilter()
    current_state: DbCurrentState = DbCurrentState()

    def upsert_record(self, model_class: Type[ModelType],
                      filter_fields: dict[str, Any],
                      update_fields: dict[str, Any]) -> ModelType:
        """
        Universal function for searching and updating/creating records in any database model
        Универсальная функция для поиска и обновления/создания записи в любой модели БД
        Attributes:
            model_class (Type[ModelType]): model class in which to search/create a record
            filter_fields (Dict[str, Any]): fields for searching the record
            update_fields (Dict[str, Any]): fields for updating/creating the record
        Returns:
            ModelType: the found or created/updated record
        """

        # Checking the record for existence / Проверяем запись на существование
        existing = self.session.query(model_class).filter_by(**filter_fields).first()
        if existing:
            # Updating an existing record / Обновляем существующую запись
            for key, value in update_fields.items():
                setattr(existing, key, value)
        else:
            # Create a new record / Создаем новую запись
            existing = model_class(**{**filter_fields, **update_fields})
            self.session.add(existing)
            self.session.flush()  # Flush to get the ID if it's an autoincrement field
        return existing

    def setup_database_connection(self):
        """
        Configuring SQLite database connection settings
        Настройка параметров подключения к базе данных SQLite
        """

        # Enforce foreign key constraints in SQLite
        @event.listens_for(self.engine, "connect")
        def set_sqlite_pragma(dbapi_conn, _):  # _ используется вместо необязательного параметра connection_record
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    def __init__(self):
        """
        Initializes the database handler by creating an engine, a session, and the necessary tables.
        Инициализирует обработчик базы данных, создавая движок, сессию и необходимые таблицы.
        """

        # Creating database engine and session
        self.engine = create_engine(f'sqlite:///{ProjectDirs.data_base_file}')
        self.setup_database_connection()
        self.session = Session(self.engine)
        # Creating tables in the database if they do not exist
        # Создаем таблицы в базе данных, если они отсутствуют
        Base.metadata.create_all(self.engine)
        # Checking the availability of data in the static table with dialogue types and adding them if necessary.
        # Проверяем наличие данных в статической таблице с типами диалогов и добавляем их при необходимости
        for dialog_type in DialogTypes:
            self.upsert_record(DbDialogType, {'dialog_type_id': dialog_type.value}, {'name': dialog_type.name})
        # Checking the availability of data in the static table with file types and adding them if necessary.
        # Проверяем наличие данных в статической таблице с типами файлов и добавляем их при необходимости
        for file_type in MessageFileTypes:
            self.upsert_record(DbFileType, {'file_type_id': file_type.type_id},
                               {'name': file_type.name, 'alt_text': file_type.alt_text,
                                'default_ext': file_type.default_ext, 'sign': file_type.sign})
        # Reset the “marked” flag for all message groups when the application starts.
        # Сбрасываем флаг "отмечена" у всех групп сообщений при старте приложения
        stmt = update(DbMessageGroup).values(selected=False)
        self.session.execute(stmt)
        # Save changes to the database / Сохраняем изменения в базе данных
        self.session.commit()
        # Get a list of saved dialogs from the database / Получаем список сохраненных диалогов из базы данных
        self.all_dialogues_list = self.get_dialog_list()
        # Get a list of all tags from the database / Получаем список всех тегов из базы данных
        self.current_state.all_tags_list_sorting = TagsSorting.NAME_ASC
        self.all_tags_list = self.get_all_tag_list()
        # Set the current state of the database client / Устанавливаем текущее состояние клиента базы данных
        self.current_state.dialog_list = list(self.all_dialogues_list)
        self.current_state.all_tags_list = list(self.all_tags_list)
        self.current_state.message_group_list = []

    def get_dialog_list(self) -> List[DbDialog]:
        """
        Getting a list of dialogs available in the database, taking into account filters and sorting
        Получение списка диалогов, имеющихся в БД с учетом фильтров и сортировки
        """

        # Getting the IDs of all dialogs / Получаем множество ID всех диалогов
        all_dialogs_id = set(self.session.execute(select(DbDialog.dialog_id)).scalars().all())
        # Getting a set of dialog IDs that are referenced in message groups
        # Получаем множество ID диалогов, на которые есть ссылки в группах сообщений
        referenced_dialogs_id = set(self.session.execute(select(DbMessageGroup.dialog_id).distinct()).scalars().all())
        # Find unused dialogs / Находим не используемые диалоги
        unused_dialogs_id = all_dialogs_id - referenced_dialogs_id
        # Deleting unused dialogs / Удаляем неиспользуемые диалоги
        if unused_dialogs_id:
            delete_stmt = delete(DbDialog).where(DbDialog.dialog_id.in_(unused_dialogs_id))
            self.session.execute(delete_stmt)
            self.session.commit()
        # Getting the remaining dialogs with filters and sorting applied
        # Получаем оставшиеся диалоги с учетом фильтров и сортировки
        select_stmt = select(DbDialog).order_by(asc(DbDialog.title))
        query_result = self.session.execute(select_stmt).scalars().all()
        # status_messages.mess_update('Loading chat lists',
        #                             f'{len(query_result)} chats loaded from the database')
        return list(query_result)

    def get_all_tag_list(self) -> List[DbTag]:
        """
        Get a list of all tags available in the database, taking into account the sorting specified in
                                                                                        current_state.sorting_tags
        Получение списка всех тегов, имеющихся в БД с учетом сортировки, установленной в current_state.sorting_tags
        """

        # Updating tag usage rates / Обновляем частоту использования тегов
        update_stmt = (update(DbTag).values(
            usage_count=select(func.count())  # pylint: disable=not-callable
            .select_from(message_group_tag_links)
            .where(message_group_tag_links.c.tag_id == DbTag.id)  # type: ignore
            .scalar_subquery())
                       .where(DbTag.id.isnot(None))
                       )
        self.session.execute(update_stmt)
        # Remove tags that are not used / Удаляем теги, которые не используются
        self.session.query(DbTag).filter(DbTag.usage_count == 0).delete()
        # Save changes to the database / Сохраняем изменения в базе данных
        self.session.commit()
        # Define the field for sorting / Определяем поле для сортировки
        sort_field = getattr(DbTag, self.current_state.all_tags_list_sorting['field'])
        # Define the sorting direction / Определяем направление сортировки
        if self.current_state.all_tags_list_sorting['order'] == 'asc':
            sort_expr = asc(sort_field)
        else:
            sort_expr = desc(sort_field)
        select_stmt = (
            select(DbTag)
            .group_by(DbTag.name)
            .order_by(sort_expr, DbTag.name)  # Secondary sorting by name / Вторичная сортировка по имени
        )
        query_result = self.session.execute(select_stmt).scalars().all()
        return list(query_result)

    def get_message_group_list(self) -> list[DbMessageGroup]:
        """
        Getting a list of message groups based on filters and sorting
        Получение списка групп сообщений с учетом фильтров и сортировки
        """

        # We uncheck the “marked” flag for all message groups / Сбрасываем флаг "отмечено" у всех групп сообщений
        update_stmt = update(DbMessageGroup).values(selected=False)
        self.session.execute(update_stmt)
        # Save changes to the database / Сохраняем изменения в базе данных
        self.session.commit()
        # Generating a query taking into account filters and sorting / Формируем запрос с учетом фильтров и сортировки
        select_stmt = select(DbMessageGroup)
        # Filter by selected dialogs / Фильтр по выбранным диалогам
        if self.message_sort_filter.selected_dialog_list:
            select_stmt = select_stmt.where(DbMessageGroup.dialog_id.in_(self.message_sort_filter.selected_dialog_list))
        # Filter by date from and to / Фильтр по дате от и до
        if self.message_sort_filter.date_from:
            select_stmt = select_stmt.where(DbMessageGroup.date >= self.message_sort_filter.date_from)
        if self.message_sort_filter.date_to:
            select_stmt = select_stmt.where(DbMessageGroup.date <= self.message_sort_filter.date_to)
        # Filter by message text / Фильтр по текстам сообщений
        if self.message_sort_filter.message_query:
            select_stmt = select_stmt.where(DbMessageGroup.text.ilike(f'%{self.message_sort_filter.message_query}%'))
        # Filter by message tags / Фильтр по тегам сообщений
        if self.message_sort_filter.tag_query:
            # Create a list of expressions with conditions for searching for key phrases in tags
            # Создаем список выражений с условиями для поиска ключевых фраз в тегах
            tag_conditions = [DbTag.name.ilike(f'%{keyword}%') for keyword in self.message_sort_filter.tag_query]
            select_stmt = select_stmt.where(DbMessageGroup.tags.any(or_(*tag_conditions)))
        # Sort by dialogues / Сортировка по диалогам
        if self.message_sort_filter.sorting_field == self.message_sort_filter.sort_by_title:
            select_stmt = select_stmt.join(DbDialog).order_by(
                DbDialog.title.desc() if self.message_sort_filter.sort_order else DbDialog.title.asc(),
                DbMessageGroup.date.desc())
        # Sort by date / Сортировка по дате
        if self.message_sort_filter.sorting_field == self.message_sort_filter.sort_by_date:
            select_stmt = select_stmt.order_by(
                DbMessageGroup.date.desc() if self.message_sort_filter.sort_order else DbMessageGroup.date.asc())
        query_result = self.session.execute(select_stmt).scalars().all()
        status_messages.mess_update('Loading chats from the database',
                                    f'{len(query_result)} chats loaded from the database', True)
        return list(query_result)

    @staticmethod
    def get_select_content_string(db_object_list: list, value: str, visible_text: str) -> str:
        """
        Formats a string for a tag in HTML format for the content of <select>
        Формирует строку для тега в HTML формате для содержимого <select>
        """

        if not db_object_list:
            return ''
        result = '\n'.join(
            [f'<option value="{getattr(db_object, value)}" >{getattr(db_object, visible_text)}</option>'
             for db_object in db_object_list])
        return result

    def get_message_detail(self, message_group_id: str) -> dict:
        """
        Getting message by dialog ID and message group ID
        Получение сообщения по id диалога и id группы сообщений
        Attributes:
            message_group_id (str): message group ID
        Returns:
            dict: message details
        """

        # Get the current group of messages by id / Получаем текущую группу сообщений по id
        current_message_group = self.session.query(DbMessageGroup).filter(
            DbMessageGroup.grouped_id == message_group_id).one()
        db_details = {'dialog_id': current_message_group.dialog_id,
                      'dialog_title': current_message_group.dialog.title,
                      'message_group_id': message_group_id,
                      'date': current_message_group.date,
                      'text': current_message_group.text if current_message_group.text else '',
                      'files': current_message_group.files,
                      'files_report': current_message_group.files_report if current_message_group.files_report else '',
                      'tags': current_message_group.tags if current_message_group.tags else None}
        db_details['existing_files'] = [db_file for db_file in (db_details.get('files') or []) if db_file.is_exists()]
        message_date = db_details.get('date')
        message_date_str = message_date.strftime(
            GlobalConst.message_datetime_format) if message_date is not None else ''
        status_messages.mess_update(
            f'Loading details of message "{message_date_str}" in chat "{db_details.get('dialog_title')}"',
            'Message details loaded', True)
        return db_details

    def message_group_exists(self, grouped_id: str) -> bool:
        """
        Checks whether a group of messages with the specified grouped_id exists
        Проверяет, существует ли группа сообщений с заданным grouped_id
        Attributes:
            grouped_id (str): message group ID
        Returns:
            bool: True if the message group exists, False otherwise
        """

        stmt = select(DbMessageGroup).filter(DbMessageGroup.grouped_id == grouped_id)
        query_result = bool(self.session.execute(stmt).scalars().first())
        return query_result

    def get_file_list_by_extension(self, file_ext: list) -> list[str]:
        """
        Gets a list of files with specified extensions from the database
        Получает из базы данных список файлов с заданными расширениями
        Attributes:
            file_ext (list): list of file extensions
        Returns:
            list[str]: list of file paths
        """

        stmt = select(DbFile.file_path).filter(or_(*[DbFile.file_path.endswith(ext) for ext in file_ext]))
        query_result = self.session.execute(stmt).scalars().all()
        return list(query_result)

    def get_file_by_local_path(self, local_path: str) -> dict[str, Any] | None:
        """
        Gets a file object from the database via a local path
        Получает из базы данных объект файл по локальному пути
        Attributes:
            local_path (str): local file path
        Returns:
            Optional[dict[str, Any]]: file information dictionary or None if not found
        """

        stmt = select(DbFile).filter(DbFile.file_path == local_path)
        query_result = self.session.execute(stmt).scalars().first()
        db_file_info = None
        if query_result:
            db_file_info = {'dialog_id': query_result.message_group.dialog_id,
                            'message_id': query_result.message_id,
                            'file_path': query_result.file_path,
                            'size': query_result.size,
                            'file_type_id': query_result.file_type_id, }
        return db_file_info

    def add_tag_to_message_group(self, tag_name: str, message_group_id: str) -> tuple[str, str]:
        """
        Adds a tag to a specified group of messages
        Добавляет тег к заданной группе сообщений
        Attributes:
            tag_name (str): tag name
            message_group_id (str): message group ID
        Returns:
            tuple[str, str]: updated current message tags select string, updated all tags select string
        """

        # Get the tag and group of messages by their ID / Получаем тег и группу сообщений по их ID
        tag = self.session.query(DbTag).filter(DbTag.name == tag_name).first()
        stmt = select(DbMessageGroup).filter(DbMessageGroup.grouped_id == message_group_id)
        message_group = self.session.execute(stmt).scalars().one()
        # Check for the tag in the database and add it if it is not there
        # Проверяем наличие тега в базе данных и добавляем, если нет
        if not tag:
            tag = DbTag(name=tag_name)
            self.session.add(tag)
            self.session.flush()
        # Check for the presence of messages in the database and the absence of the tag in it, and add the tag to it
        # Проверяем наличие группы сообщений в базе данных и отсутствие тега в ней и добавляем тег к ней
        if message_group and tag not in message_group.tags:
            message_group.tags.append(tag)
            tag.usage_count += 1
        self.session.commit()
        # Get updated tag lists for SELECT current message and all tags
        # Получаем обновленные списки тегов для SELECT текущего сообщения и всех тегов
        current_tags_select = self.get_select_content_string(message_group.tags, 'id', 'name')
        self.all_tags_list = self.get_all_tag_list()
        all_tags_select = self.get_select_content_string(self.all_tags_list, 'id', 'name')
        return current_tags_select, all_tags_select

    def remove_tag_from_message_group(self, tag_name: str, message_group_id: str) -> tuple[str, str]:
        """
        Removes a tag from a specified group of messages
        Удаляет тег из заданной группы сообщений
        Attributes:
            tag_name (str): tag name
            message_group_id (str): message group ID
        Returns:
            tuple[str, str]: updated current message tags select string, updated all tags select string
        """

        # Get a tag and a group of messages by their IDs / Получаем тег и группу сообщений по их ID
        stmt: Select = select(DbTag).filter(DbTag.name == tag_name)
        tag = self.session.execute(stmt).scalars().first()
        stmt = select(DbMessageGroup).filter(DbMessageGroup.grouped_id == message_group_id)
        message_group = self.session.execute(stmt).scalars().one()
        # Check for the presence of a tag in a group of messages in the database and remove the tag from it
        # Проверяем наличие тега в группе сообщений в базе данных и удаляем тег из неё
        if all([tag, message_group, tag in message_group.tags]):
            message_group.tags.remove(tag)
            tag.usage_count -= 1
            self.session.commit()
        # Get updated tag lists for SELECT current message and all tags
        # Получаем обновленные списки тегов для SELECT текущего сообщения и всех тегов
        current_tags_select = self.get_select_content_string(message_group.tags, 'id', 'name')
        self.all_tags_list = self.get_all_tag_list()
        all_tags_select = self.get_select_content_string(self.all_tags_list, 'id', 'name')
        return current_tags_select, all_tags_select

    def update_tag_from_message_group(self, old_tag_name: str, new_tag_name: str, message_group_id: str) -> tuple[
        str, str]:
        """
        Changes the specified tag from the current group message
        Изменяет заданный тег из текущего группового сообщения
        Attributes:
            old_tag_name (str): old tag name
            new_tag_name (str): new tag name
            message_group_id (str): message group ID
        Returns:
            tuple[str, str]: updated current message tags select string, updated all tags select string
        """

        # Get the old tag and a group of messages by their ID / Получаем старый тег и группу сообщений по их ID
        tag = self.session.query(DbTag).filter(DbTag.name == old_tag_name).first()
        stmt = select(DbMessageGroup).filter(DbMessageGroup.grouped_id == message_group_id)
        message_group = self.session.execute(stmt).scalars().one()
        # Check for the presence of a tag and a group of messages in the database
        # Проверяем наличие группы сообщений и тега в ней в базе данных
        if all([tag, message_group, tag in message_group.tags]):
            self.remove_tag_from_message_group(old_tag_name, message_group_id)
            self.add_tag_to_message_group(new_tag_name, message_group_id)
        # Get updated tag lists for SELECT current message and all tags
        # Получаем обновленные списки тегов для SELECT текущего сообщения и всех тегов
        current_tags_select = self.get_select_content_string(message_group.tags, 'id', 'name')
        self.all_tags_list = self.get_all_tag_list()
        all_tags_select = self.get_select_content_string(self.all_tags_list, 'id', 'name')
        return current_tags_select, all_tags_select

    def update_tag_everywhere(self, old_tag_name: str, new_tag_name: str,
                              message_group_id: str) -> tuple[str | None, str]:
        """
        Updates the tag in all message groups where it is used
        Обновляет тег во всех группах сообщений, где он используется
        Attributes:
            old_tag_name (str): old tag name
            new_tag_name (str): new tag name
            message_group_id (str): message group ID
        Returns:
            tuple[Optional[str], str]: updated current message tags select string, updated all tags select string
        """

        current_tags_select = None
        # Rename the tag in all message groups where it is used
        # Переименовываем тег во всех группах сообщений, где он используется
        stmt = select(DbMessageGroup).filter(DbMessageGroup.tags.any(name=old_tag_name))
        message_group_list = self.session.execute(stmt).scalars().all()
        for message_group in message_group_list:
            self.remove_tag_from_message_group(old_tag_name, message_group.grouped_id)
            self.add_tag_to_message_group(new_tag_name, message_group.grouped_id)
            if message_group.grouped_id == message_group_id:
                # Get the current list of tags for the current message
                # Получаем текущий список тегов для текущего сообщения
                current_tags_select = self.get_select_content_string(message_group.tags, 'id', 'name')
        # Get updated tag lists for SELECT current message and all tags
        # Получаем обновленные списки тегов для SELECT текущего сообщения и всех тегов
        self.all_tags_list = self.get_all_tag_list()
        all_tags_select = self.get_select_content_string(self.all_tags_list, 'id', 'name')
        return current_tags_select, all_tags_select


# Creating an instance of DatabaseHandler / Создаем экземпляр DatabaseHandler
db_handler = DatabaseHandler()

if __name__ == '__main__':
    pass
