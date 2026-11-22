"""
The module contains model classes and functions for working with an SQLite database using SQLAlchemy.
Модуль содержит классы моделей и функции для работы с базой данных SQLite через SQLAlchemy.

class DatabaseHandler: a class to represent handle database operations.
class Base(DeclarativeBase): a declarative class for creating tables in the database
class DbDialog(Base): a class to represent a dialog (chat) in the database.
class DbDialogType(Base): a class to represent a type of dialog (chat) in the database.
class DbFile(Base): a class to represent a file associated with a message group in the database.
class DbFileType(Base): a class to represent a type of file associated with a message group in the database.
class DbMessageGroup(Base): a class to represent a message group in the database.
class UtcDateTime(TypeDecorator): a column type for date and time stored in UTC
utc_now: a function returning the current moment as an aware datetime in UTC
class DbTag(Base): a class to represent a tag associated with a message group in the database.
class TagChange: the result of a tag operation for the page (the number of changed groups, the SELECT strings)
class DbCurrentState: a class representing the current state of the database client
class DbMessageSortFilter: a class to represent sorting and filtering of message groups in the database.
get_db_handler: a function returning the shared DatabaseHandler (created lazily on the first call)
message_group_tag_links: a relationship table for many-to-many relationship between message groups and tags
ModelType: a TypeVar for model classes, bound to Base
"""

from collections.abc import Iterable
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from threading import Lock
from typing import List, Any, Type, TypeVar, Iterator  # List - necessary for relationships
from sqlalchemy import create_engine, Integer, ForeignKey, Text, String, Table, Column, select, asc, desc, and_, or_, \
    Boolean, update, delete, event, func, Select, DateTime
from sqlalchemy.engine import Dialect
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, selectinload, Session
from sqlalchemy.types import TypeDecorator
from configs.config import ProjectDirs, GlobalConst, TableNames, DialogTypes, MessageFileTypes, TagsSorting
from utils import format_files_report, local_day_start, parse_date_string, status_messages, to_local, to_utc


class UtcDateTime(TypeDecorator):  # pylint: disable=too-many-ancestors,abstract-method
    """
    Date and time stored in UTC. SQLite keeps a date as a string without a time zone, so the value is converted to UTC
    on write (a naive datetime is local time, as in Python) and comes back as an aware datetime in UTC. It works for the
    values of the query filters too (they are bound through the same type).
    Дата и время, хранимые в UTC. SQLite хранит дату строкой без часового пояса, поэтому при записи значение переводится
    в UTC (наивная дата-время - локальное время, как в Python), а читается как aware дата-время в UTC. Работает и для
    значений фильтров запросов (они передаются через тот же тип).
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        """Converts a value to UTC before writing to the database / Переводит значение в UTC перед записью в БД"""
        return to_utc(value) if value is not None else None

    def process_result_value(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        """Marks a value read from the database as UTC / Помечает значение, прочитанное из БД, как UTC"""
        if value is None:
            return None
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def utc_now() -> datetime:
    """
    Current moment as an aware datetime in UTC (a column default)
    Текущий момент как aware дата-время в UTC (значение столбца по умолчанию)
    """

    return datetime.now(timezone.utc)


class Base(DeclarativeBase):  # pylint: disable=too-few-public-methods
    """
    A declarative class for creating tables in the database
    Декларативный класс для создания таблиц в базе данных
    """

    # Every `Mapped[datetime]` column is stored in UTC / Каждый столбец `Mapped[datetime]` хранится в UTC
    type_annotation_map = {datetime: UtcDateTime}


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


LIKE_ESCAPE_CHAR = '\\'  # Escape character of the LIKE patterns / Символ экранирования в шаблонах LIKE


def escape_like(value: str) -> str:
    """
    Escapes the characters that have a special meaning in a LIKE pattern (%, _ and the escape character itself), so a
    search query is matched literally
    Экранирует символы, имеющие особый смысл в шаблоне LIKE (%, _ и сам символ экранирования), чтобы поисковый запрос
    сравнивался буквально
    Attributes:
        value (str): search query
    Returns:
        str: the query for use in a LIKE pattern with `escape=LIKE_ESCAPE_CHAR`
    """

    return (value.replace(LIKE_ESCAPE_CHAR, LIKE_ESCAPE_CHAR * 2)
            .replace('%', f'{LIKE_ESCAPE_CHAR}%').replace('_', f'{LIKE_ESCAPE_CHAR}_'))


def _unicode_lower(value: Any) -> Any:
    """
    Lower-cases a string for any alphabet (the SQLite built-in `lower()` handles only ASCII); other values stay as is
    Приводит строку к нижнему регистру для любого алфавита (встроенная `lower()` в SQLite умеет только ASCII);
    остальные значения не меняются
    """

    return value.lower() if isinstance(value, str) else value


class DbMessageGroup(Base):  # pylint: disable=too-few-public-methods
    """
    A class to represent a message group in the database.
    Класс для представления группы сообщений в базе данных.
    """

    __tablename__ = TableNames.message_groups  # Table name in the database / Имя таблицы в базе данных
    grouped_id: Mapped[str] = mapped_column(String, primary_key=True, unique=True, index=True, nullable=False)
    date: Mapped[datetime]
    # Safe HTML of the message text (built by `render_message_html`) and the same text without formatting for search
    # Безопасный HTML текста сообщения (строит `render_message_html`) и тот же текст без форматирования для поиска
    html: Mapped[str] = mapped_column(Text, nullable=True)
    plain_text: Mapped[str] = mapped_column(Text, nullable=True)
    truncated_text: Mapped[str] = mapped_column(Text, nullable=True)
    files_report: Mapped[str] = mapped_column(Text, nullable=True)
    sender_id: Mapped[int] = mapped_column(Integer, nullable=True)
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
                       'date': to_local(self.date).strftime(GlobalConst.message_datetime_format) if self.date else '',
                       'html': self.html if self.html else '',
                       'sender_id': self.sender_id,
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
    created_at: Mapped[datetime] = mapped_column(default=utc_now)
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
        selected_dialog_list (list[int] | None): list of selected dialog IDs for filtering messages
        sorting_field (str): field to sort messages by (date or dialog)
        sort_order (bool): sort order: descending (True) or ascending (False)
        date_from (datetime | None): date from which to get messages
        date_to (datetime | None): date to which to get messages
        message_query (str | None): filter by message text
        tag_query (list[str] | None): filter by message tags
        tag_match_all (bool): the tag filter mode: every keyword must match (True, AND) or any (False, OR)
    """

    _selected_dialog_list: list[int] | None = None
    _sorting_field = None
    _sort_order: bool = False
    _date_from: datetime | None = None
    _date_to: datetime | None = None
    _message_query: str | None = None
    _tag_query: list[str] | None = None
    _tag_match_all: bool = False
    sort_by_date: str = 'by date'
    sort_by_title: str = 'by title'

    @property
    def selected_dialog_list(self) -> list[int] | None:
        """
        Returns a list of selected dialogs for filtering messages by dialogs
        Возвращает список выбранных диалогов для фильтрации сообщений по диалогам
        """
        return self._selected_dialog_list

    @selected_dialog_list.setter
    def selected_dialog_list(self, value: list[int]):
        """
        Sets the list of selected dialogs for filtering messages by dialogs
        Задает список выбранных диалогов для фильтрации сообщений по диалогам
        Attributes:
            value (list[int]): selected dialog IDs
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
    def date_from(self) -> datetime | None:
        """
        Returns the date from which to receive messages
        Возвращает дату, с которой получать сообщения
        Return:
            datetime | None: date from which to receive messages
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
    def date_to(self) -> datetime | None:
        """
        Returns the date until which messages should be received
        Возвращает дату, до которой получать сообщения
        Return:
            datetime | None: date until which messages should be received
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
        self._date_to = parse_date_string(value, end_of_day=True)  # the last day is included / последний день включен

    @property
    def message_query(self) -> str | None:
        """
        Returns a filter by message text
        Возвращает фильтр по тексту сообщений
        Return:
            str | None: message text fragment
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
    def tag_query(self) -> list[str] | None:
        """
        Returns a list of filters by message tags
        Возвращает список фильтров по тегам сообщений
        Return:
            list[str] | None: message tag fragments
        """
        return self._tag_query

    @tag_query.setter
    def tag_query(self, value: str):
        """
        Sets a list of filters by message tags. The keywords are the parts between the separators (the spaces inside a
        part stay: `art ad` is one keyword); the edges are trimmed, the empty parts are dropped (an empty keyword would
        match every tag). No keywords: the filter is off.
        Устанавливает список фильтров по тегам сообщений. Ключевые слова - части между разделителями (пробелы внутри
        части сохраняются: `art ad` - одно слово); края обрезаются, пустые части отбрасываются (пустое слово совпало бы
        с любым тегом). Нет слов: фильтр выключен.
        Attributes:
            value (str): form data
        """
        keywords = [tag.strip() for tag in value.split(GlobalConst.tag_filter_separator)] if value else []
        self._tag_query = [keyword for keyword in keywords if keyword] or None

    @property
    def tag_match_all(self) -> bool:
        """
        Returns the mode of the tag filter: True - every keyword must match (AND), False - any keyword (OR)
        Возвращает режим фильтра по тегам: True - должны совпасть все слова (И), False - любое слово (ИЛИ)
        Return:
            bool: the AND mode
        """
        return self._tag_match_all

    @tag_match_all.setter
    def tag_match_all(self, value: str):
        """
        Sets the mode of the tag filter from the radio buttons of the form: '1' - AND, anything else (also a missing
        value) - OR, the default
        Устанавливает режим фильтра по тегам по радиокнопкам формы: '1' - И, все остальное (в том числе отсутствие
        значения) - ИЛИ, режим по умолчанию
        Attributes:
            value (str): form data
        """
        self._tag_match_all = value == '1'

    def set_default_filters(self) -> None:
        """
        Sets the default filters of the tab: the last `db_last_days_by_default` days (from the start of the local day),
        sorted by date, newest first (as the radio buttons of the filter form are set), no other filters.
        Устанавливает фильтры вкладки по умолчанию: последние `db_last_days_by_default` дней (с начала локального дня),
        сортировка по дате, сначала новые (как выставлены радиокнопки формы фильтра), других фильтров нет.
        """

        self._selected_dialog_list = None
        self.sorting_field = '0'  # by date / по дате
        self.sort_order = '1'  # descending / по убыванию
        self._date_from = local_day_start(GlobalConst.db_last_days_by_default)
        self._date_to = None
        self._message_query = None
        self._tag_query = None
        self._tag_match_all = False


@dataclass
class TagChange:
    """
    The result of a tag operation for the page
    Результат операции с тегами для страницы
    Attributes:
        changed (int): the number of message groups the operation really changed
        current_tags_select (str | None): SELECT string with the tags of the open message, None if the open message was
            not processed (the field of the page stays as it is)
        all_tags_select (str): SELECT string with all tags
    """

    changed: int
    current_tags_select: str | None
    all_tags_select: str


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
        all_dialogues_list (list[DbDialog] | None): list of all database dialogs
        all_tags_list (list[DbTag] | None): list of all database tags
        message_sort_filter (DbMessageSortFilter): current message filter
        current_state (DbCurrentState): current state of the database
    """

    all_dialogues_list: list[DbDialog] | None = None
    all_tags_list: list[DbTag] | None = None
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
            filter_fields (dict[str, Any]): fields for searching the record
            update_fields (dict[str, Any]): fields for updating/creating the record
        Returns:
            ModelType: the found or created/updated record
        """

        # Checking the record for existence / Проверяем запись на существование
        existing = self.session.query(model_class).filter_by(**filter_fields).first()
        if filter_fields and existing:
            # Updating an existing record / Обновляем существующую запись
            for key, value in update_fields.items():
                if hasattr(existing, key):
                    setattr(existing, key, value)
        else:
            # Create a new record / Создаем новую запись
            existing = model_class(**{**filter_fields, **update_fields})
            self.session.add(existing)
            self.session.flush()  # Flush to get the ID if it's an autoincrement field
        return existing

    @contextmanager
    def transaction(self) -> Iterator[Session]:
        """
        Context manager for a transaction: commit on success, rollback and re-raise on any exception.
        Контекстный менеджер транзакции: commit при успехе, rollback и повторный выброс при любом исключении.
        Yields:
            Session: the shared database session
        """

        try:
            yield self.session
            self.session.commit()
        except Exception:
            # Without a rollback the shared session stays in a failed state for all later requests
            # Без отката общая сессия остается в неработоспособном состоянии для всех следующих запросов
            self.session.rollback()
            raise

    def setup_database_connection(self):
        """
        Configuring SQLite database connection settings
        Настройка параметров подключения к базе данных SQLite
        """

        # Enforce foreign key constraints in SQLite
        @event.listens_for(self.engine, "connect")
        def set_sqlite_pragma(dbapi_conn, _):  # _ используется вместо необязательного параметра connection_record
            # SQLite `lower()` changes only ASCII letters, and SQLAlchemy renders `ilike` as `lower(a) LIKE lower(b)`.
            # Replace it with a Unicode-aware function, so the search ignores the case of Cyrillic text too.
            # `lower()` в SQLite меняет только ASCII-буквы, а SQLAlchemy превращает `ilike` в `lower(a) LIKE lower(b)`.
            # Заменяем ее функцией с поддержкой Unicode, чтобы поиск не зависел от регистра и у кириллицы.
            dbapi_conn.create_function('lower', 1, _unicode_lower, deterministic=True)
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")  # Enabling foreign key constraints
            cursor.execute("PRAGMA journal_mode=WAL")  # Write-Ahead Logging
            cursor.execute("PRAGMA synchronous=NORMAL")  # Быстрее записи
            cursor.execute("PRAGMA cache_size=-64000")  # 64MB кеша
            cursor.execute("PRAGMA temp_store=MEMORY")  # Временные данные в RAM
            cursor.close()

    def __init__(self):
        """
        Initializes the database handler by creating an engine, a session, and the necessary tables.
        Инициализирует обработчик базы данных, создавая движок, сессию и необходимые таблицы.
        """

        # SQLite creates the database file but not its folder (a fresh clone has no `database/`)
        # SQLite создает файл базы данных, но не его папку (в свежем клоне нет `database/`)
        Path(ProjectDirs.data_base_dir).mkdir(parents=True, exist_ok=True)
        # Creating database engine and session
        # check_same_thread=False: the session is created in one thread but used from the web server's thread pool;
        # access is serialized by a shared lock outside this class.
        # check_same_thread=False: сессия создается в одном потоке, а используется из пула потоков веб-сервера;
        # доступ сериализуется общим замком вне этого класса.
        self.engine = create_engine(f'sqlite:///{ProjectDirs.data_base_file}',
                                    connect_args={'check_same_thread': False})
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
        # The handler's own message filter with the defaults (the last days, sorted by date), like the Telegram handler;
        # the form of the tab shows its dates, so the first "Apply" does not load the whole archive. The list of
        # messages stays empty until the filter is applied.
        # Собственный фильтр сообщений обработчика с умолчаниями (последние дни, сортировка по дате), как у обработчика
        # Telegram; форма вкладки показывает его даты, поэтому первое «Apply» не загрузит весь архив. Список сообщений
        # пуст, пока фильтр не применен.
        self.message_sort_filter = DbMessageSortFilter()
        self.message_sort_filter.set_default_filters()
        self.current_state.message_group_list = []

    def get_dialog_list(self) -> list[DbDialog]:
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

    def get_all_tag_list(self) -> list[DbTag]:
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
        # The files of the groups are loaded by one more query for the whole list: the list shows the files summary
        # line, which is formed from their type IDs (not stored)
        # Файлы групп подгружаются еще одним запросом на весь список: список показывает строку-резюме файлов,
        # которая формируется по ID их типов (не хранится)
        select_stmt = select(DbMessageGroup).options(selectinload(DbMessageGroup.files))
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
            select_stmt = select_stmt.where(DbMessageGroup.plain_text.ilike(
                f'%{escape_like(self.message_sort_filter.message_query)}%', escape=LIKE_ESCAPE_CHAR))
        # Filter by message tags / Фильтр по тегам сообщений
        if self.message_sort_filter.tag_query:
            # Create a list of expressions with conditions for searching for key phrases in tags (a part of a tag,
            # `%`, `_` and `\` are ordinary characters, like in the search by message text)
            # Создаем список выражений с условиями для поиска ключевых фраз в тегах (часть тега, `%`, `_` и `\` -
            # обычные символы, как в поиске по тексту сообщений)
            # One condition per keyword: the message has a tag that contains the keyword. OR: any keyword is enough;
            # AND: every keyword must match some tag of the message (not necessarily the same one)
            # Одно условие на слово: у сообщения есть тег, содержащий слово. ИЛИ: достаточно любого слова;
            # И: каждое слово должно совпасть с каким-либо тегом сообщения (не обязательно с одним и тем же)
            tag_conditions = [DbMessageGroup.tags.any(DbTag.name.ilike(f'%{escape_like(keyword)}%',
                                                                       escape=LIKE_ESCAPE_CHAR))
                              for keyword in self.message_sort_filter.tag_query]
            select_stmt = select_stmt.where(
                and_(*tag_conditions) if self.message_sort_filter.tag_match_all else or_(*tag_conditions))
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
        # The values (dialog titles, tag names) are escaped: the string goes to the page as HTML
        # Значения (названия диалогов, имена тегов) экранируются: строка попадает на страницу как HTML
        result = '\n'.join(
            [f'<option value="{escape(str(getattr(db_object, value)))}" >'
             f'{escape(str(getattr(db_object, visible_text)))}</option>'
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
                      'html': current_message_group.html if current_message_group.html else '',
                      'files': current_message_group.files,
                      'files_report': format_files_report(
                          db_file.file_type_id for db_file in current_message_group.files),
                      'tags': current_message_group.tags if current_message_group.tags else []}
        db_details['existing_files'] = [db_file for db_file in (db_details.get('files') or []) if db_file.is_exists()]
        message_date = db_details.get('date')
        message_date_str = to_local(message_date).strftime(
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
            dict[str, Any] | None: file information dictionary or None if not found
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

    def _get_message_groups(self, message_group_ids: Iterable[str]) -> list[DbMessageGroup]:
        """
        Gets the message groups by their IDs. A repeated ID counts once; an ID of a group that does not exist (for
        example, the page was not refreshed after the group was deleted) is skipped.
        Получает группы сообщений по их ID. Повторяющийся ID учитывается один раз; ID несуществующей группы (например,
        страница не обновилась после удаления группы) пропускается.
        Attributes:
            message_group_ids (Iterable[str]): message group IDs
        """

        unique_ids = list(dict.fromkeys(message_group_ids))
        if not unique_ids:
            return []
        stmt = select(DbMessageGroup).where(DbMessageGroup.grouped_id.in_(unique_ids))
        return list(self.session.execute(stmt).scalars().all())

    def _attach_tag(self, message_group: DbMessageGroup, tag_name: str) -> bool:
        """
        Adds a tag to a message group, creating the tag if it does not exist. It does not commit: the caller owns the
        transaction.
        Добавляет тег к группе сообщений, создавая тег, если его нет.
        Не делает commit: транзакцией управляет вызывающий.
        Attributes:
            message_group (DbMessageGroup): message group
            tag_name (str): tag name
        Returns:
            bool: True if the tag was added, False if the group already had it
        """

        tag = self.session.query(DbTag).filter(DbTag.name == tag_name).first()
        # Add the tag to the database if it is not there / Добавляем тег в базу данных, если его там нет
        if not tag:
            tag = DbTag(name=tag_name)
            self.session.add(tag)
            self.session.flush()
        # Link the tag with the group if it is not linked yet / Связываем тег с группой, если еще не связан
        if tag not in message_group.tags:
            message_group.tags.append(tag)
            tag.usage_count += 1
            return True
        return False

    def _detach_tag(self, message_group: DbMessageGroup, tag_name: str) -> bool:
        """
        Removes a tag from a message group if the group has it. It does not commit: the caller owns the transaction.
        Удаляет тег из группы сообщений, если он в ней есть. Не делает commit: транзакцией управляет вызывающий.
        Attributes:
            message_group (DbMessageGroup): message group
            tag_name (str): tag name
        Returns:
            bool: True if the tag was removed, False if the group did not have it
        """

        tag = self.session.query(DbTag).filter(DbTag.name == tag_name).first()
        if tag and tag in message_group.tags:
            message_group.tags.remove(tag)
            tag.usage_count -= 1
            return True
        return False

    def _tag_change(self, processed_groups: list[DbMessageGroup], changed: int, current_group_id: str) -> TagChange:
        """
        Builds the result of a tag operation. The tags of the open message are returned only if it was among the
        processed groups (otherwise the field of the page stays as it is). The list of all tags is refreshed: it
        recounts the usage and removes unused tags.
        Формирует результат операции с тегами. Теги открытого сообщения возвращаются, только если оно было среди
        обработанных групп (иначе поле страницы остается как есть). Список всех тегов обновляется: пересчитывается
        использование и удаляются неиспользуемые теги.
        Attributes:
            processed_groups (list[DbMessageGroup]): the groups the operation looked at (checked, or having the tag)
            changed (int): the number of groups the operation really changed
            current_group_id (str): ID of the message open in the details ('' if closed)
        """

        current_group = next((group for group in processed_groups if group.grouped_id == current_group_id), None)
        current_tags_select = (self.get_select_content_string(current_group.tags, 'id', 'name')
                               if current_group else None)
        self.all_tags_list = self.get_all_tag_list()
        return TagChange(changed, current_tags_select,
                         self.get_select_content_string(self.all_tags_list, 'id', 'name'))

    def add_tag_to_message_groups(self, tag_name: str, message_group_ids: Iterable[str],
                                  current_group_id: str = '') -> TagChange:
        """
        Adds a tag to the specified groups of messages (one transaction for all of them)
        Добавляет тег к заданным группам сообщений (одна транзакция на все группы)
        Attributes:
            tag_name (str): tag name
            message_group_ids (Iterable[str]): IDs of the groups (the checked messages)
            current_group_id (str): ID of the message open in the details ('' if closed)
        Returns:
            TagChange: the number of groups that got the tag, the select strings to update
        """

        changed = 0
        with self.transaction():
            groups = self._get_message_groups(message_group_ids)
            for message_group in groups:
                changed += self._attach_tag(message_group, tag_name)
        return self._tag_change(groups, changed, current_group_id)

    def remove_tag_from_message_groups(self, tag_name: str, message_group_ids: Iterable[str],
                                       current_group_id: str = '') -> TagChange:
        """
        Removes a tag from the specified groups of messages (one transaction for all of them)
        Удаляет тег из заданных групп сообщений (одна транзакция на все группы)
        Attributes:
            tag_name (str): tag name
            message_group_ids (Iterable[str]): IDs of the groups (the checked messages)
            current_group_id (str): ID of the message open in the details ('' if closed)
        Returns:
            TagChange: the number of groups that lost the tag, the select strings to update
        """

        changed = 0
        with self.transaction():
            groups = self._get_message_groups(message_group_ids)
            for message_group in groups:
                changed += self._detach_tag(message_group, tag_name)
        return self._tag_change(groups, changed, current_group_id)

    def update_tag_from_message_groups(self, old_tag_name: str, new_tag_name: str,
                                       message_group_ids: Iterable[str], current_group_id: str = '') -> TagChange:
        """
        Changes the specified tag in the specified groups of messages that have it (one transaction for all of them:
        either all the removals of the old tag and the additions of the new one happen, or none)
        Изменяет заданный тег в заданных группах сообщений, где он есть (одна транзакция на все группы: либо все
        удаления старого тега и добавления нового выполняются, либо ни одно)
        Attributes:
            old_tag_name (str): old tag name
            new_tag_name (str): new tag name
            message_group_ids (Iterable[str]): IDs of the groups (the checked messages)
            current_group_id (str): ID of the message open in the details ('' if closed)
        Returns:
            TagChange: the number of groups where the tag was changed, the select strings to update
        """

        changed = 0
        with self.transaction():
            groups = self._get_message_groups(message_group_ids)
            for message_group in groups:
                # Change the tag only if the group has it / Изменяем тег, только если он есть в группе
                if any(tag.name == old_tag_name for tag in message_group.tags):
                    self._detach_tag(message_group, old_tag_name)
                    self._attach_tag(message_group, new_tag_name)
                    changed += 1
        return self._tag_change(groups, changed, current_group_id)

    def update_tag_everywhere(self, old_tag_name: str, new_tag_name: str, current_group_id: str = '') -> TagChange:
        """
        Updates the tag in all message groups where it is used, whether the messages are checked or not (one
        transaction for all groups)
        Обновляет тег во всех группах сообщений, где он используется, отмечены сообщения или нет (одна транзакция на все
        группы)
        Attributes:
            old_tag_name (str): old tag name
            new_tag_name (str): new tag name
            current_group_id (str): ID of the message open in the details ('' if closed)
        Returns:
            TagChange: the number of groups where the tag was renamed, the select strings to update (the tags of the
                open message only if it had the tag)
        """

        # Rename the tag in all message groups where it is used
        # Переименовываем тег во всех группах сообщений, где он используется
        with self.transaction():
            stmt = select(DbMessageGroup).filter(DbMessageGroup.tags.any(name=old_tag_name))
            groups = list(self.session.execute(stmt).scalars().all())
            for message_group in groups:
                self._detach_tag(message_group, old_tag_name)
                self._attach_tag(message_group, new_tag_name)
        return self._tag_change(groups, len(groups), current_group_id)


# The DatabaseHandler instance is created lazily on the first get_db_handler() call, not on module import:
# the constructor opens the database, creates tables and writes reference data.
# Экземпляр DatabaseHandler создается лениво, при первом вызове get_db_handler(), а не при импорте модуля:
# конструктор открывает базу данных, создает таблицы и записывает справочные данные.
_db_handler: DatabaseHandler | None = None
_db_handler_lock = Lock()


def get_db_handler() -> DatabaseHandler:
    """
    Returns the shared DatabaseHandler, creating it on the first call.
    Возвращает общий DatabaseHandler, создавая его при первом вызове.
    Returns:
        DatabaseHandler: the single instance for working with the database
    """

    global _db_handler
    if _db_handler is None:
        # The lock prevents two threads from creating two handlers at the same time
        # Замок не дает двум потокам одновременно создать два обработчика
        with _db_handler_lock:
            if _db_handler is None:
                _db_handler = DatabaseHandler()
    return _db_handler


if __name__ == '__main__':
    pass
