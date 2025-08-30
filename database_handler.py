from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Any, Type, Dict, TypeVar, Optional

from sqlalchemy import create_engine, Integer, ForeignKey, Text, String, Table, Column, select, asc, desc, or_, update, \
    func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, Session

from configs.config import ProjectDirs, TableNames, DialogTypes, MessageFileTypes, parse_date_string, TagsSorting


class Base(DeclarativeBase):
    """ A declarative class for creating tables in the database """


# TypeVar for model classes, bound to Base
ModelType = TypeVar('ModelType', bound=Base)

# Relationships Many-to-Many to 'MessageGroup' and 'DbTag' tables
message_group_tag_links = Table(
    TableNames.message_group_tag_links, Base.metadata,
    Column('message_group_id', String, ForeignKey(f'{TableNames.message_groups}.grouped_id'), primary_key=True),
    Column('tag_id', Integer, ForeignKey(f'{TableNames.tags}.id'), primary_key=True)
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
    name: Mapped[str] = mapped_column(Text, default='', nullable=False)
    usage_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(default=datetime.now, onupdate=datetime.now)
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

    def is_exists(self) -> bool:
        """
        Проверяет, был ли файл загружен в файловую систему
        """
        return (Path(ProjectDirs.media_dir) / self.file_path).exists() if self.file_path else False


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
    sort_by_date: str = 'by date'
    sort_by_title: str = 'by title'

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
        self._sorting_field = self.sort_by_date if value == '0' else self.sort_by_title

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
        self._date_from = parse_date_string(value)

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
        self._date_to = parse_date_string(value)

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
    message_group_list: List[DbMessageGroup] = None
    message_details: Dict[str, Any] = None
    details_tags_string: str = None
    selected_message_group_id: str = None


class DatabaseHandler:
    """
    A class to represent handle database operations.
    Класс для представления операций с базой данных.
    """

    all_dialogues_list: List[DbDialog] = None
    all_tags_list: List[DbTag] = None
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
        self.all_dialogues_list = self.get_dialog_list()
        # Обновляем частоту использования тегов
        stmt = (update(DbTag).values(
            usage_count=select(func.count())
            .select_from(message_group_tag_links)
            .where(message_group_tag_links.c.tag_id.in_(select(DbTag.id)))
            .scalar_subquery())
        )
        self.session.execute(stmt)
        # Удаляем теги, которые не используются
        self.session.query(DbTag).filter(DbTag.usage_count == 0).delete()
        # Сохраняем изменения в базе данных
        self.session.commit()
        # Получаем список всех тегов из базы данных
        self.all_tags_list = self.get_all_tag_list(sorting=TagsSorting.name_asc)
        # Устанавливаем текущее состояние клиента базы данных
        self.current_state.dialog_list = list(self.all_dialogues_list)
        self.current_state.all_tags_list = list(self.all_tags_list)
        self.current_state.message_group_list = []

    def get_dialog_list(self) -> List[DbDialog]:
        """
        Получение списка диалогов, имеющихся в БД с учетом фильтров и сортировки
        """
        dialogs = self.session.execute(select(DbDialog)).scalars().all()
        dialog_list = []
        for db_dialog in dialogs:
            dialog_list.append(db_dialog)
        print(f'{len(dialog_list)} chats loaded from the database')
        return sorted(dialog_list, key=lambda x: x.title)

    def get_all_tag_list(self, sorting: dict) -> List[DbTag]:
        """
        Получение списка всех тегов, имеющихся в БД с учетом сортировки
        """
        # Определяем поле для сортировки
        sort_field = getattr(DbTag, sorting['field'])
        # Определяем направление сортировки
        if sorting['order'] == 'asc':
            sort_expr = asc(sort_field)
        else:
            sort_expr = desc(sort_field)
        stmt = (
            select(DbTag)
            .group_by(DbTag.name)
            .order_by(sort_expr, DbTag.name)  # Вторичная сортировка по имени
        )
        query_result = self.session.execute(stmt).scalars().all()
        return list(query_result)

    @staticmethod
    def get_tags_select_string(tags: List[DbTag]) -> str:
        """
        Получение содержимого <SELECT> для выбора тегов
        """
        return '/n'.join([f'<option value = "{tag.id}" > {tag.name}</option>' for tag in tags])

    def get_message_group_list(self) -> list[DbMessageGroup]:
        """
        Получение списка групп сообщений с учетом фильтров и сортировки
        """
        stmt = select(DbMessageGroup)
        # Фильтр по выбранным диалогам
        if self.message_sort_filter.selected_dialog_list:
            stmt = stmt.where(DbMessageGroup.dialog_id.in_(self.message_sort_filter.selected_dialog_list))
        # Фильтр по дате от и до
        if self.message_sort_filter.date_from:
            stmt = stmt.where(DbMessageGroup.date >= self.message_sort_filter.date_from)
        if self.message_sort_filter.date_to:
            stmt = stmt.where(DbMessageGroup.date <= self.message_sort_filter.date_to)
        # Фильтр по тексту сообщения
        if self.message_sort_filter.message_query:
            stmt = stmt.where(DbMessageGroup.text.ilike(f'%{self.message_sort_filter.message_query}%'))
        # Сортировка по диалогам
        if self.message_sort_filter.sorting_field == self.message_sort_filter.sort_by_title:
            stmt = stmt.join(DbDialog).order_by(
                DbDialog.title.desc() if self.message_sort_filter.sort_order else DbDialog.title.asc(),
                DbMessageGroup.date.desc())
        # Сортировка по дате
        if self.message_sort_filter.sorting_field == self.message_sort_filter.sort_by_date:
            stmt = stmt.order_by(
                DbMessageGroup.date.desc() if self.message_sort_filter.sort_order else DbMessageGroup.date.asc())
        query_result = self.session.execute(stmt).scalars().all()
        print(f'{len(query_result)} messages loaded from the database')
        return list(query_result)

    @staticmethod
    def get_select_tags_string(tags: Optional[List[DbTag]]) -> str:
        """
        Формирует строку для тега в HTML формате для использования в <select>
        """
        if not tags:
            return ''
        result = '\n'.join([f'<option value="{tag.id}" > {tag.name}</option>' for tag in tags])
        return result

    def get_message_detail(self, message_group_id: str) -> dict:
        """
        Получение сообщения по id диалога и id группы сообщений
        """
        # Получаем текущую группу сообщений по id
        current_message_group = self.session.query(DbMessageGroup).filter(
            DbMessageGroup.grouped_id == message_group_id).one()
        db_details = dict(dialog_id=current_message_group.dialog_id,
                          dialog_title=current_message_group.dialog.title,
                          message_group_id=message_group_id,
                          date=current_message_group.date,
                          text=current_message_group.text if current_message_group.text else '',
                          files=current_message_group.files,
                          files_report=current_message_group.files_report if current_message_group.files_report else '',
                          tags=current_message_group.tags if current_message_group.tags else None)
        db_details['existing_files'] = [db_file for db_file in db_details.get('files') if db_file.is_exists()]
        return db_details

    def message_group_exists(self, grouped_id: str) -> bool:
        """
        Проверяет, существует ли группа сообщений с заданным grouped_id
        """
        stmt = select(DbMessageGroup).filter(DbMessageGroup.grouped_id == grouped_id)
        query_result = bool(self.session.execute(stmt).scalars().first())
        return query_result

    def get_file_list_by_extension(self, file_ext: list) -> list[str]:
        """
        Получает из базы данных список файлов с заданными расширениями
        """
        stmt = select(DbFile.file_path).filter(or_(*[DbFile.file_path.endswith(ext) for ext in file_ext]))
        query_result = self.session.execute(stmt).scalars().all()
        return list(query_result)

    def get_file_by_local_path(self, local_path: str) -> Optional[DbFile]:
        """
        Получает из базы данных файл по локальному пути
        """
        stmt = select(DbFile).filter(DbFile.file_path == local_path)
        query_result = self.session.execute(stmt).scalars().first()
        db_file = None
        if query_result:
            db_file = dict(dialog_id=query_result.message_group.dialog_id,
                           message_id=query_result.message_id,
                           file_path=query_result.file_path,
                           size=query_result.size,
                           file_type_id=query_result.file_type_id, )

        return db_file

    def add_tag_to_message_group(self, tag_name: str, message_group_id: str) -> None:
        """
        Добавляет тег к заданной группе сообщений
        """
        # Получаем тег и группу сообщений по их идентификаторам
        stmt = select(DbTag).filter(DbTag.name == tag_name)
        tag = self.session.execute(stmt).scalars().first()
        stmt = select(DbMessageGroup).filter(DbMessageGroup.grouped_id == message_group_id)
        message_group = self.session.execute(stmt).scalars().one()
        # Проверяем наличие тега в базе данных и добавляем, если нет
        if not tag:
            tag = DbTag(name=tag_name)
            self.session.add(tag)
            self.session.flush()
        # Проверяем наличие группы сообщений в базе данных и добавляем тег к ней
        if message_group:
            message_group.tags.append(tag)
            tag.usage_count += 1
        self.session.commit()

    def remove_tag_from_message_group(self, tag_name: str, message_group_id: str):
        """
        Удаляет тег из заданной группы сообщений
        """
        # Получаем тег и группу сообщений по их идентификаторам
        stmt = select(DbTag).filter(DbTag.name == tag_name)
        tag = self.session.execute(stmt).scalars().first()
        stmt = select(DbMessageGroup).filter(DbMessageGroup.grouped_id == message_group_id)
        message_group = self.session.execute(stmt).scalars().one()
        # Проверяем наличие тега и группы сообщений в базе данных и удаляем тег из неё
        if tag and message_group:
            message_group.tags.remove(tag)
            tag.usage_count -= 1
        self.session.commit()

    def update_tag_from_message_group(self, old_tag_name: str, new_tag_name: str, message_group_id: str):
        """
        Изменяет заданный тег из заданной группы сообщений
        """
        self.remove_tag_from_message_group(old_tag_name, message_group_id)
        self.add_tag_to_message_group(new_tag_name, message_group_id)
        self.session.commit()

    def update_tag_everywhere(self, old_tag_name: str, new_tag_name: str):
        """
        Обновляет тег во всех группах сообщений, где он используется
        """
        stmt = update(DbTag).where(DbTag.name == old_tag_name).values(name=new_tag_name)
        self.session.execute(stmt)
        self.session.commit()


if __name__ == '__main__':
    pass
