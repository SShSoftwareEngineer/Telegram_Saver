"""
The module contains model classes, functions, and constants for working with an SQLite database using SQLAlchemy.

class TelegramHandler: a class for handling Telegram operations.
class TgCurrentState: a class to represent the current state of the Telegram client
class TgDialog: a class to represent a Telegram dialog in this program
class TgDialogSortFilter: a class to represent sorting and filtering options of Telegram dialogs
class TgFile: a class to represent a Telegram message file
class TgMessageGroup: a class to represent a Telegram message group in this program
class TgMessageSortFilter: a class to represent sorting and filtering of Telegram message groups.
tg_handler: an object of the TelegramHandler class for working with the Telegram
loop: the asyncio event loop for working with the Telegram client
convert_text_hyperlinks: a function for converting text hyperlinks in Markdown format [Text](URL) to HTML format
cleanup_loop: a function called at application exit to close the event loop if it is open
"""

import atexit
from asyncio import new_event_loop, set_event_loop
from collections import Counter
from mimetypes import guess_extension
from sys import maxsize
from textwrap import shorten
from dataclasses import dataclass
from typing import Any, Callable, cast
from datetime import datetime, timedelta
from pathlib import Path
from telethon.tl.custom import Dialog, Message
from telethon.tl.types import MessageMediaPhoto, MessageMediaDocument, PhotoSize, PhotoCachedSize, PhotoStrippedSize, \
    PhotoSizeProgressive, MessageMediaWebPage
from telethon import TelegramClient
from dotenv import dotenv_values
from configs.config import ProjectDirs, GlobalConst, MessageFileTypes, DialogTypes
from utils import parse_date_string, clean_file_path, status_messages


@dataclass
class TgDialog:
    """
    A class to represent a Telegram dialog
    Класс диалога (чата) Telegram
    Attributes:
        dialog_id (int): dialog ID
        title (str): title (name) of dialog
        unread_count (int): number of unread messages
        last_message_date (datetime | None): date and time of last message
        type (DialogTypes): dialog type
    """

    dialog_id: int
    title: str
    unread_count: int = 0
    last_message_date: datetime | None = None
    type: DialogTypes = DialogTypes.UNKNOWN

    def __init__(self, dialog: Dialog):
        """
        Initializes the dialog object with the specified parameters.
        Инициализирует объект диалога с заданными параметрами.
        """

        self.dialog_id = dialog.id
        if dialog.title:
            self.title = dialog.title
        elif dialog.name:
            self.title = dialog.name
        else:
            self.title = GlobalConst.dialog_no_title
        self.unread_count = dialog.unread_count if dialog.unread_count else 0
        self.last_message_date = dialog.date.astimezone() if dialog.date else None  # type: ignore
        self.type = TgDialog.set_type(dialog.is_channel, dialog.is_group, dialog.is_user)
        self.dialog_dir = clean_file_path(f'{self.title}_{self.dialog_id}')

    @staticmethod
    def set_type(is_channel: bool, is_group: bool, is_user: bool) -> DialogTypes:
        """
        Returns the name of the dialog type depending on the Telegram dialog type.
        Возвращает имя типа диалога в зависимости от типа диалога Telegram
        """

        if is_channel:
            return DialogTypes.CHANNEL
        if is_group:
            return DialogTypes.GROUP
        if is_user:
            return DialogTypes.USER
        return DialogTypes.UNKNOWN

    def get_self_dir(self) -> str:
        """
        Returns the name of the dialog directory
        Возвращает имя директории диалога
        """
        return clean_file_path(f'{self.title}_{self.dialog_id}') or f'{self.title}_{self.dialog_id}'


@dataclass
class TgDialogSortFilter:
    """
    A class to represent sorting and filtering options of Telegram dialogs.
    Класс, представляющий текущие параметры фильтра и сортировки диалогов Telegram
    """

    _sorting_field: Callable[[Any], Any] | None = None
    _sort_order: bool = False
    _dialog_type: DialogTypes | None = None
    _title_query: str | None = None

    @staticmethod
    def _sort_by_title(x):
        """
        Sort by dialog name function
        Функция сортировки по названию диалога
        """
        return x.title

    @staticmethod
    def _sort_by_last_message_date(x):
        """
        Sort by date of last update
        Функция сортировки по дате последнего обновления
        """
        return x.last_message_date

    def sort_field(self, value: str):
        """
        Sets the sorting field
        Устанавливает поле для сортировки
        Attributes:
            value (str): form data
        """
        self._sorting_field = self._sort_by_title if value == '0' else self._sort_by_last_message_date

    def sort_order(self, value: str):
        """
        Sets the sorting order
        Устанавливает порядок сортировки
        Attributes:
            value (str): form data
        """
        self._sort_order = value != '0'  # False if value == '0' else True

    def dialog_type(self, value: str):
        """
        Sets a filter by dialog type
        Устанавливает фильтр по типу диалогов
        Attributes:
            value (str): form data
        """

        match value:
            case '0':
                self._dialog_type = None
            case '1':
                self._dialog_type = DialogTypes.CHANNEL
            case '2':
                self._dialog_type = DialogTypes.GROUP
            case '3':
                self._dialog_type = DialogTypes.USER
            case _:
                self._dialog_type = DialogTypes.UNKNOWN

    def title_query(self, value: str):
        """
        Sets a filter by dialog name
        Устанавливает фильтр по названию диалогов
        Attributes:
            value (str): form data
        """
        self._title_query = value if value else None

    def check_filters(self, tg_dialog: TgDialog) -> bool:
        """
        Checking filters by substring in the name and by type for a specific dialog
        Проверка фильтров по подстроке в названии и по типу для конкретного диалога
        Attributes:
            tg_dialog (TgDialog): verification dialog
        Returns:
            bool: filter condition match
        """

        title_query = True
        if self._title_query:
            title_query = self._title_query.lower() in str(tg_dialog.title).lower()
        dialog_type = True
        if self._dialog_type:
            dialog_type = tg_dialog.type == self._dialog_type
        return all([title_query, dialog_type])

    def sort_dialog_list(self, dialog_list: list[TgDialog]) -> list[TgDialog]:
        """
        Sorting a list of dialogs by a specified field in a specified order
        Сортировка списка диалогов по заданному полю в заданном порядке
        Attributes:
            dialog_list (list[TgDialog]): list of dialogs for sorting
        Returns:
            list[TgDialog]: sorted dialogue list
        """

        if self._sorting_field is None:
            self._sorting_field = self._sort_by_title
        result = sorted(dialog_list, key=self._sorting_field, reverse=self._sort_order)
        return result


@dataclass
class TgFile:  # pylint: disable=too-many-instance-attributes
    """
    A class to represent a Telegram message file.
    Класс, представляющий файл сообщения Telegram.
    Attributes:
        dialog_id (int): dialog ID
        message_grouped_id (str): message group ID
        message (Message): Telegram message object
        message_id (int): message ID
        description (str): description of the reference message
        file_name (str): file name
        file_path (str): full file path
        alt_text (str): alternate text for media file
        size (int): size of file
        file_type (MessageFileTypes): file type
    """

    dialog_id: int
    message_grouped_id: str
    message: Message
    message_id: int
    description: str
    file_name: str
    file_path: str
    alt_text: str
    size: int
    file_type: MessageFileTypes = MessageFileTypes.UNKNOWN

    def is_exists(self) -> bool:
        """
        Checks whether a file exists in the file system
        Проверяет, существует ли файл в файловой системе
        """
        return (Path(ProjectDirs.media_dir) / self.file_path).exists() if self.file_path else False

    @staticmethod
    def get_self_file_name(date: datetime, file_type: MessageFileTypes, message_grouped_id: str,
                           message_id: int, file_ext: str) -> str:
        """
        Return template of file name
        Возвращает шаблонное имя файла
        Attributes:
            date (datetime): date and time of file message
            file_type (MessageFileTypes): file type
            message_grouped_id (str): file message group ID
            message_id (int): file message ID
            file_ext (str): file extension
        Returns:
            str: file name
        """

        file_name = (f'{date.astimezone().strftime('%H-%M-%S')}_'
                     f'{file_type.sign}_{message_grouped_id}_{message_id}{file_ext}')
        return clean_file_path(file_name) or file_name


@dataclass
class TgMessageGroup:  # pylint: disable=too-many-instance-attributes
    """
    A class representing a group of Telegram messages with a single grouped_id
    Класс представляющий группу сообщений Telegram с одним grouped_id
    Attributes:
        grouped_id (str): common grouped ID for a group of messages
        dialog_id (int): group message dialogue ID
        ids (list[int]): ID of messages contained in the message group
        files (list[TgFile]): message files contained in a message group
        date (datetime | None): date of message group
        text (str): text of message group
        truncated_text (str): truncated text of message group for HTML templates
        from_id (int | None): message sender ID
        files_report (str | None): summary of message group files
        saved_to_db (bool): database saving status
    """

    grouped_id: str
    dialog_id: int
    ids: list[int]
    files: list[TgFile]
    date: datetime | None = None
    text: str = ''
    truncated_text: str = ''
    from_id: int | None = None
    files_report: str | None = ''
    saved_to_db: bool = False

    def __init__(self, grouped_id: str, dialog_id: int):
        """
        Initializes a message group
        Инициализирует групу сообщений
        Attributes:
            grouped_id (str): common grouped ID for a group of messages
            dialog_id (int): group message dialogue ID
        """

        self.grouped_id = grouped_id
        self.dialog_id = dialog_id
        self.ids = []
        self.files = []

    def add_message(self, message: Message) -> None:
        """
        Adds a message to a message group
        Добавляет сообщение в группу сообщений
        Attributes:
            message (Message): added message
        """
        self.from_id = message.from_id if self.from_id is None else self.from_id
        self.date = message.date.astimezone() if self.date is None else min(self.date, message.date.astimezone())
        self.ids.append(message.id)
        if message.text:
            self.text = message.text if self.text is None else '\n\n'.join([self.text, message.text]).strip()

    def add_message_file(self, message_file: TgFile | None = None) -> None:
        """
        Adds the message file to the message group, if it exists
        Добавляет файл сообщения в группу сообщений, если он есть
        Attributes:
            message_file (TgFile | None): added file
        """
        if message_file:
            self.files.append(message_file)
            if message_file.description:
                self.text = message_file.description if self.text is None else '\n\n'.join(
                    [self.text, message_file.description]).strip()

    def set_files_report(self) -> None:
        """
        Forming a summary string based on the files available in the group messages and their types
        Формирование строки резюме по имеющимся в группе сообщений файлам и их типам
        """

        alt_texts_list = []
        for file in self.files:
            alt_texts_list.append(file.alt_text)
        alt_texts_dict = dict(sorted(Counter(alt_texts_list).items()))
        alt_texts_list.clear()
        for alt_text, count in alt_texts_dict.items():
            current_report = f'{alt_text} ({count})' if count > 1 else alt_text
            alt_texts_list.append(current_report)
        self.files_report = ' '.join(sorted(alt_texts_list))

    def text_hyperlink_conversion(self) -> None:
        """
        Converting text hyperlinks of the form [Text](URL) to HTML format
        Преобразование текстовых гиперссылок вида [Text](URL) в HTML формат
        """
        if self.text:
            self.text = convert_text_hyperlinks(self.text) or ''

    def set_truncated_text(self) -> None:
        """
        Trimming the length of a message for display in the web interface of the message list
        Обрезание длины текста сообщения для отображения в веб-интерфейсе списка сообщений
        """

        if self.text:
            # If the text of the message does not contain hyperlinks, we trim it to the specified length.
            # Если текст сообщения не содержит гиперссылок обрезаем до заданной длины
            if any([self.text.find('<a href') == -1,
                    self.text.find('<a href') > GlobalConst.truncated_text_length]):
                self.truncated_text = shorten(self.text, width=GlobalConst.truncated_text_length, placeholder='...')
            else:
                self.truncated_text = shorten(self.text, width=GlobalConst.truncated_text_length + 50,
                                              placeholder='...')

            #     hyperlinks = re.findall(r'.*?(<a href.*?>)(.*?)(<\/a>).*?', self.text)
            #     if hyperlinks:
            #         for hyperlink in hyperlinks:
            #             hyperlink_text = ''.join(hyperlink)
            #             truncated_text_length = self.text.find(hyperlink_text)
            #             if truncated_text_length  >= ProjectConst.truncated_text_length:
            #                 pass
            #             if truncated_text_length+len(hyperlink[1]) >= ProjectConst.truncated_text_length:
            #                 self.truncated_text = shorten(self.text, placeholder='...',
            #                                               width=truncated_text_length + len(hyperlink_text))
            #                 break
            # if not self.truncated_text:
            #     self.truncated_text = self.text

        # <a href = "https://cutt.ly/DrnDxWzA" target = "_blank" >
        # «Перезавантаження: розширення для працевлаштування» </a>
        # shorten             из             модуля             textwrap

    def get_self_dir(self) -> str:
        """
        Returns the path to the message group directory
        Возвращает путь к директории группы сообщений
        """

        assert self.date is not None, 'The message group must contain the date'
        date_str = self.date.astimezone().strftime('%Y-%m-%d')
        return clean_file_path(date_str) or date_str


@dataclass
class TgMessageSortFilter:
    """
    A class to represent sorting and filtering of Telegram message groups
    Класс представляющий параметры сортировки и фильтрации группы сообщений
    """

    _sort_order: bool = True
    _date_from: datetime | None = datetime.now() - timedelta(days=GlobalConst.last_days_by_default)
    _date_to: datetime | None = None
    _message_query: str | None = None
    date_from_default: str | None = (datetime.now() - timedelta(
        days=GlobalConst.last_days_by_default)).strftime("%Y-%m-%d")

    def set_default_filters(self):
        """
        Sets default filters
        Устанавливает фильтры по умолчанию
        """

        self._sort_order = True
        self._date_from = datetime.now() - timedelta(days=GlobalConst.last_days_by_default)
        self._date_to = None
        self._message_query = None
        self.date_from_default = self.date_from.strftime("%Y-%m-%d")

    @property
    def sort_order(self) -> bool:
        """
        Returns the sort order of messages by date
        Возвращает порядок сортировки сообщений по дате
        """
        return self._sort_order

    @sort_order.setter
    def sort_order(self, value: str):
        """
        Returns the sorting order of messages by date
        Устанавливает порядок сортировки сообщений по дате
        Attributes:
            value (str): form data
        """
        self._sort_order = value == '0'  # True if value == '0' else False

    @property
    def date_from(self) -> datetime | None:
        """
        Returns the date from which to receive messages
        Возвращает дату, с которой получать сообщения
        """
        return self._date_from

    @date_from.setter
    def date_from(self, value: str):
        """
        Sets the order for sorting messages by date
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
        """
        return self._date_to

    @date_to.setter
    def date_to(self, value: str):
        """
        Sets the date until which messages should be received
        Устанавливает дату, до которой получать сообщения
        Attributes:
            value (str): form data
        """
        self._date_to = parse_date_string(value)

    @property
    def message_query(self) -> str | None:
        """
        Returns a filter by dialog title
        Возвращает фильтр по названию диалогов
        """
        return self._message_query

    @message_query.setter
    def message_query(self, value: str):
        """
        Sets a filter by dialog title
        Устанавливает фильтр по названию диалогов
        Attributes:
            value (str): form data
        """
        self._message_query = value if value else None

    def sort_message_group_list(self, message_group_list: list[TgMessageGroup]) -> list[TgMessageGroup]:
        """
        Sorting the list of message groups by date
        Сортировка списка групп сообщений по дате
        Attributes:
            message_group_list (list[TgMessageGroup]):
        Returns:
            list[TgMessageGroup]: sorted list of message groups
        """
        return sorted(message_group_list, key=lambda group: group.date or datetime.min, reverse=self.sort_order)


@dataclass
class TgCurrentState:
    """
    Current state of the Telegram client
    Текущее состояние клиента Telegram
    Attributes:
        dialog_list (list[TgDialog] | None): current dialog list
        selected_dialog_id (int | None): selected dialog ID
        message_group_list (list[TgMessageGroup] | None): current message group list
        message_details (dict[str, Any] | None): selected message details
    """

    dialog_list: list[TgDialog] | None = None
    selected_dialog_id: int | None = None
    message_group_list: list[TgMessageGroup] | None = None
    message_details: dict[str, Any] | None = None


class TelegramHandler:
    """
    Класс для представления операций с клиентом Telegram
    A class for handling Telegram client operations
    Attributes:
        all_dialogues_list (list[TgDialog] | None): list of all dialogs
        dialog_sort_filter (TgDialogSortFilter): current dialog filter
        message_sort_filter (TgMessageSortFilter): current message filter
        current_state (TgCurrentState): current state of the Telegram client
    """

    all_dialogues_list: list[TgDialog] | None = None
    dialog_sort_filter: TgDialogSortFilter = TgDialogSortFilter()
    message_sort_filter: TgMessageSortFilter = TgMessageSortFilter()
    current_state: TgCurrentState = TgCurrentState()

    def __init__(self):
        """
        Initializes the Telegram handler.
        Инициализирует обработчик сообщений Telegram.
        """

        # Load Telegram connection settings from file / Загружаем настройки подключения к Telegram из файла
        self._connection_settings = dotenv_values(ProjectDirs.telegram_settings_file)
        # Creating and launching a Telegram client / Создаем и запускаем клиент Telegram
        self.client = TelegramClient(self._connection_settings['SESSION_NAME'],
                                     int(self._connection_settings['API_ID']),
                                     self._connection_settings['API_HASH'], loop=loop)
        self.client.start(self._connection_settings['PHONE'], self._connection_settings['PASSWORD'])
        # Get your Telegram username / Получаем имя пользователя Telegram
        self.me = loop.run_until_complete(self.client.get_me())
        # Get a list of all Telegram account dialogues / Получаем список всех диалогов аккаунта Telegram
        self.all_dialogues_list = self.get_dialog_list()
        # Set the current status of the Telegram client / Устанавливаем текущее состояние клиента Telegram
        self.current_state.dialog_list = list(self.all_dialogues_list)
        if self.current_state.dialog_list:
            # Get the first dialog ID / Получаем ID первого диалога
            self.current_state.selected_dialog_id = self.current_state.dialog_list[0].dialog_id
        self.current_state.message_group_list = []
        self.current_state.message_details = None

    def get_entity(self, entity_id: int) -> Any:
        """
        Getting a Telegram entity by its ID
        Получение Telegram сущности по ее ID
        Attributes:
            entity_id (int): entity ID
        Returns:
            Any: Telegram entity
        """
        entity = loop.run_until_complete(self.client.get_entity(entity_id))
        return entity

    def get_dialog_by_id(self, dialog_id: int) -> TgDialog | None:
        """
        Getting a dialog by its ID
        Получение диалога по его ID
        Attributes:
            dialog_id (int): dialog ID
        Returns:
            TgDialog | None: Telegram dialog object
        """
        found_tg_dialog = next((x for x in (self.all_dialogues_list or []) if x.dialog_id == dialog_id), None)
        return found_tg_dialog

    @staticmethod
    def get_message_group_by_id(message_group_list: list, grouped_id: str) -> TgMessageGroup | None:
        """
        Retrieving a group of messages from the message list with the same grouped_id
        Получение группы сообщений из списка сообщений с одинаковым grouped_id
        Attributes:
            message_group_list (list): list of message groups
            grouped_id (str): grouped ID of the message group
        Returns:
            TgMessageGroup | None: message group object
        """
        found_tg_message_group = next((x for x in message_group_list if x.grouped_id == grouped_id), None)
        return found_tg_message_group

    def get_dialog_list(self) -> list[TgDialog]:
        """
        Getting a list of all Telegram dialogs with filters and sorting
        Получение списка всех диалогов Telegram с учетом фильтров и сортировки
        """

        status_messages.mess_update('Loading chat list from Telegram', '', True)
        dialogs = loop.run_until_complete(self.client.get_dialogs())
        dialog_list = []
        for dialog in dialogs:
            tg_dialog = TgDialog(dialog)
            if tg_dialog.dialog_id == self.me.id:
                tg_dialog.title = GlobalConst.me_dialog_title
            if self.dialog_sort_filter.check_filters(tg_dialog):
                dialog_list.append(tg_dialog)
        status_messages.mess_update('Loading chat lists', f'{len(dialog_list)} chats loaded from Telegram')
        return self.dialog_sort_filter.sort_dialog_list(dialog_list)

    def get_message_list(self, dialog_id: int) -> list[Message]:
        """
        Getting a list of messages from a specified chat, taking into account filters and sorting
        Получение списка сообщений из заданного чата с учетом фильтров и сортировки
        Attributes:
            dialog_id (int): dialog ID
        Returns:
            list[Message]: list of Telegram messages
        """

        current_tg_dialog = self.get_dialog_by_id(dialog_id)
        if current_tg_dialog:
            status_messages.mess_update(f'Loading messages for "{current_tg_dialog.title}" dialog', '', True)
        # Get the entity of the dialogue by ID / Получаем сущность диалога по ID
        dialog = self.get_entity(dialog_id)
        # Forming the current message filter parameters / Формируем текущие параметры фильтра сообщений
        message_filters = {'entity': dialog}
        # Set filter parameters by minimum date via message ID
        # Устанавливаем параметры фильтрации по минимальной дате через ID сообщений
        if self.message_sort_filter.date_from:
            message_from = loop.run_until_complete(
                self.client.get_messages(entity=dialog, offset_date=self.message_sort_filter.date_from, limit=1))
            message_filters['min_id'] = message_from[0].id if message_from else 0
        # Set filter parameters by maximum date via message ID
        # Устанавливаем параметры фильтрации по максимальной дате через id сообщений
        if self.message_sort_filter.date_to:
            message_to = loop.run_until_complete(
                self.client.get_messages(entity=dialog, offset_date=self.message_sort_filter.date_to, limit=1,
                                         reverse=True))
            message_filters['max_id'] = message_to[0].id if message_to else maxsize
        # Setting the sort order parameter by date / Установка параметра порядка сортировки по дате
        message_filters['reverse'] = self.message_sort_filter.sort_order
        # Getting a list of messages according to filters / Получение списка сообщений в соответствии с фильтрами
        message_list = loop.run_until_complete(self.client.get_messages(**message_filters))
        status_messages.mess_update('', f'{len(message_list)} messages loaded')
        return message_list

    def get_message_group_list(self, dialog_id: int) -> list[TgMessageGroup]:
        """
        Create list of message groups from messages in specified chat, taking in accordance filters, sorting, grouping.
        Формирование списка групп сообщений из сообщений заданного чата с учетом фильтров, сортировки и группировки
        Attributes:
            dialog_id (int): dialog ID
        Returns:
            list[TgMessageGroup]: list of message groups
        """

        # Creating a list of message groups based on grouping parameters and text filters
        # Создание списка групп сообщений с учетом параметра группировки и фильтра по тексту
        message_group_list: list[TgMessageGroup] = []
        # Creating a list of messages based on grouping by message.grouped_id
        # Составление списка сообщений с учетом группировки по message.grouped_id
        for message in self.get_message_list(dialog_id):
            # If message.grouped_id is None, then use message.id
            # Если message.grouped_id сообщения is None, то используем message.id
            message_grouped_id = f'{dialog_id}_{message.grouped_id if message.grouped_id else message.id}'
            # Check if a message group with the current grouped_id exists
            # Проверяем существование группы сообщений с текущим grouped_id
            tg_message_group = self.get_message_group_by_id(message_group_list, message_grouped_id)
            # If a message group with current grouped_id does not exist, create it and add to the list of message groups
            # Если группа сообщений с текущим grouped_id не существует, создаем ее и добавляем в список групп сообщений
            if tg_message_group is None:
                tg_message_group = TgMessageGroup(message_grouped_id, dialog_id)
                message_group_list.append(tg_message_group)
            # Add the current message to the appropriate message group
            # Добавляем текущее сообщение в соответствующую группу сообщений
            tg_message_group.add_message(message)
            # Get information about the message file, if it exists / Получаем информацию о файле сообщения, если он есть
            message_file = self.get_message_file_info(dialog_id, tg_message_group, message, False)
            # Add the file, if it exists, to the appropriate message group
            # Добавляем файл, если он есть, в соответствующую группу сообщений
            if message_file:
                tg_message_group.add_message_file(message_file)
                # If it is a video, we check for its presence and obtain information about the file with a thumbnail
                # Если это файл с видео, то проверяем на наличие и получаем информацию о файле с thumbnail
                if message_file.file_type == MessageFileTypes.VIDEO:
                    message_file = self.get_message_file_info(dialog_id, tg_message_group, message, True)
                    tg_message_group.add_message_file(message_file)
        # Apply filter based on message group text, if specified
        # Применение фильтра по тексту группы сообщений, если он задан
        if self.message_sort_filter.message_query:
            for message_group in message_group_list.copy():
                if not self.message_sort_filter.message_query.lower() in message_group.text.lower():
                    message_group_list.remove(message_group)
        # Post-processing of the generated message group / Постобработка сформированной группы сообщений
        for tg_message_group in message_group_list:
            # Converting text hyperlinks of the form [Text](URL) to HTML format
            # Преобразование текстовых гиперссылок вида [Text](URL) в HTML формат
            tg_message_group.text_hyperlink_conversion()
            # Create a summary string based on the files available in the group messages and their types
            # Формирование строки резюме по имеющимся в группе сообщений файлам и их типам
            tg_message_group.set_files_report()
            # Create a truncated message text for display in the web interface of the message list
            # Формирование обрезанного текста сообщения для отображения в веб-интерфейсе списка сообщений
            tg_message_group.set_truncated_text()
        status_messages.mess_update('', f'{len(message_group_list)} message groups have been formed')
        return self.message_sort_filter.sort_message_group_list(message_group_list)

    def get_message_detail(self, dialog_id: int, message_group_id: str) -> dict:
        """
        Getting message details by dialog ID and message group ID
        Получение деталей сообщения по ID диалога и ID группы сообщений
        Attributes:
            dialog_id (int): dialog ID
            message_group_id (str): message group ID
        Returns:
            dict: details of message group
        """

        # Get the current group of messages by id / Получаем текущую группу сообщений по id
        current_message_group = self.get_message_group_by_id(self.current_state.message_group_list or [],
                                                             message_group_id)
        assert current_message_group is not None and current_message_group.date is not None, \
            'The message group must exist and contain the date'
        message_date_str = current_message_group.date.strftime(GlobalConst.message_datetime_format)
        current_dialog = self.get_dialog_by_id(dialog_id)
        # 1. Take the dialog, or None / Берем диалог, или None
        # 2. Take the title from the dialog, or None (if the dialog was None) / У диалога берем title, или None
        # 3. If the result==None, take GlobalConst.dialog_no_title / Если None, берем GlobalConst.dialog_no_title
        detail_dialog_title = (current_dialog.title if current_dialog else None) or GlobalConst.dialog_no_title
        status_messages.mess_update(
            f'Loading details of message {message_date_str} in chat {detail_dialog_title}', '', True)
        tg_details = {'dialog_id': dialog_id,
                      'dialog_title': detail_dialog_title,
                      'message_group_id': message_group_id,
                      'date': current_message_group.date,
                      # Converting text hyperlinks of the form [Text](URL) to HTML format
                      # Преобразование текстовых гиперссылок вида [Text](URL) в HTML формат
                      'text': convert_text_hyperlinks(
                          current_message_group.text) if current_message_group.text else '',
                      'files': current_message_group.files,
                      'files_report': current_message_group.files_report if current_message_group.files_report else '',
                      'saved_to_db': current_message_group.saved_to_db}
        # Download files, except videos, contained in the detailed message, if they are not in the file system
        # Скачиваем файлы, кроме видео, содержащиеся в детальном сообщении, если их нет в файловой системе
        tg_details_files = cast(list[TgFile], tg_details.get('files', []))
        for tg_file in tg_details_files:
            if not tg_file.is_exists():
                if tg_file.file_type != MessageFileTypes.VIDEO:
                    status_messages.mess_update('', f'Downloading file {tg_file.file_path}')
                    self.download_message_file(tg_file)
        tg_details['existing_files'] = [tg_file for tg_file in tg_details_files if tg_file.is_exists()]
        status_messages.mess_update('', 'Message details loaded')
        return tg_details

    def get_message_file_info(self, dialog_id: int, message_group: TgMessageGroup,
                              # pylint: disable=too-many-statements, too-many-branches
                              message, thumbnail: bool) -> TgFile | None:
        """
        Defining the message file type, its extension and size, creating a path to the file
        Определение типа файла сообщения, его расширения и размера, формирование пути к файлу
        Attributes:
            dialog_id (int): dialog ID
            message_group (TgMessageGroup): message group object
            message (Message): Telegram message object
            thumbnail (bool): flag for getting thumbnail information
        Returns:
            TgFile | None: message file object
        """

        def get_image_size(images: list) -> int:
            """
            Defines the maximum possible image size in a message
            Определяет максимальный из возможных размер изображения в сообщении
            Attributes:
                images (list): specified image list
            Returns:
                int: maximum image size
            """

            max_image_size = 0
            for image in images:
                if isinstance(image, PhotoSize):
                    max_image_size = max(image.size, max_image_size)
                elif isinstance(image, (PhotoCachedSize, PhotoStrippedSize)):
                    max_image_size = max(len(image.bytes), max_image_size)
                elif isinstance(image, PhotoSizeProgressive):
                    max_image_size = max(*image.sizes, max_image_size)
            return max_image_size

        if not message.file:
            return None
        mess_doc = message.media.document if isinstance(message.media, MessageMediaDocument) else None
        # Define the file type from MessageFileTypes / Определяем тип файла из MessageFileTypes
        file_type = MessageFileTypes.UNKNOWN
        if isinstance(message.media, MessageMediaPhoto):
            file_type = MessageFileTypes.PHOTO
        elif isinstance(message.media, MessageMediaWebPage):
            file_type = MessageFileTypes.WEBPAGE
        elif isinstance(message.media, MessageMediaDocument) and mess_doc:
            if mess_doc.mime_type.startswith('image/'):
                file_type = MessageFileTypes.IMAGE
            elif mess_doc.mime_type.startswith('audio/'):
                file_type = MessageFileTypes.AUDIO
            elif mess_doc.mime_type.startswith('video/') and not thumbnail:
                file_type = MessageFileTypes.VIDEO
            elif all([thumbnail, hasattr(mess_doc, 'thumbs'), mess_doc.thumbs]):
                file_type = MessageFileTypes.THUMBNAIL
        # Define file extension / Определяем расширение файла
        if file_type == MessageFileTypes.UNKNOWN:
            file_ext = getattr(message.file, 'ext', None)
            if file_ext is None and mess_doc:
                file_ext = guess_extension(mess_doc.mime_type)
            if file_ext is None:
                file_ext = MessageFileTypes.UNKNOWN.default_ext
        else:
            file_ext = file_type.default_ext
        # Getting file size / Получаем размер файла
        file_size = 0
        if isinstance(message.media, MessageMediaPhoto):
            file_size = get_image_size(message.media.photo.sizes)
        elif isinstance(message.media, MessageMediaWebPage):
            if hasattr(message.media.webpage, 'photo') and message.media.webpage.photo:
                file_size = get_image_size(message.media.webpage.photo.sizes)
        elif isinstance(message.media, MessageMediaDocument):
            mess_doc = message.media.document
            if all([thumbnail, hasattr(mess_doc, 'thumbs'), mess_doc.thumbs]):
                file_size = get_image_size(mess_doc.thumbs)
            else:
                file_size = mess_doc.size
        # Get the file description / Получаем описание файла
        description = ''
        if file_type == MessageFileTypes.WEBPAGE:
            if hasattr(message.media.webpage, 'url') and message.media.webpage.url:
                description = (f'<a href = "{message.media.webpage.url}"'
                               f' target="_blank" >{message.media.webpage.url}</a>')
            if hasattr(message.media.webpage, 'description') and message.media.webpage.description:
                description = '\n\n'.join([description,
                                           shorten(message.media.webpage.description,
                                                   width=GlobalConst.truncated_text_length, placeholder='...')])
        # Creating TgFile object / Создаем объект TgFile
        tg_file = TgFile(dialog_id=dialog_id, message_grouped_id=message_group.grouped_id,
                         message=message, message_id=message.id,
                         description=description,
                         file_name='', file_path='',
                         alt_text=file_type.alt_text,
                         size=file_size,
                         file_type=file_type)
        # Generating a path to a file in the file system / Формирование пути к файлу в файловой системе
        tg_file.file_name = TgFile.get_self_file_name(tg_file.message.date, tg_file.file_type,
                                                      message_group.grouped_id, message.id, file_ext)
        current_dialog = self.get_dialog_by_id(dialog_id)
        assert current_dialog is not None, 'The dialog must exist'
        file_path = Path(current_dialog.get_self_dir()) / message_group.get_self_dir() / tg_file.file_name
        tg_file.file_path = file_path.as_posix()
        return tg_file

    def download_message_file(self, tg_file: TgFile) -> str | None:
        """
        Downloading a message file
        Загрузка файла сообщения
        Attributes:
            tg_file (TgFile): message file object
        Returns:
            str | None: message file path if downloaded, else None
        """

        downloading_param = {}
        result = None
        # Checking file existence / Проверка существования файла
        if not tg_file.is_exists():
            # Check file size is 0 < tg_file.size <= GlobalConst.max_download_file_size
            # Проверка размера файла на 0 < tg_file.size <= GlobalConst.max_download_file_size
            if 0 < tg_file.size <= GlobalConst.max_download_file_size:
                # Create the appropriate directories, if necessary, and download the file
                # Создаем соответствующие директории, при необходимости, и загружаем файл
                (Path(ProjectDirs.media_dir) / tg_file.file_path).parent.mkdir(parents=True, exist_ok=True)
                downloading_param['message'] = tg_file.message
                downloading_param['file'] = Path(ProjectDirs.media_dir) / tg_file.file_path
                if tg_file.file_type == MessageFileTypes.THUMBNAIL:
                    downloading_param['thumb'] = -1
                result = loop.run_until_complete(self.client.download_media(**downloading_param))
        else:
            # If the file already exists, return its full path / Если файл уже существует, то возвращаем его полный путь
            result = tg_file.file_path
        return result

    def download_message_file_from_list(self, downloaded_file_list: list) -> str:
        """
        Downloading files from a list with download file parameters
        Загрузка файлов по списку с параметрами файлов для скачивания
        Attributes:
            downloaded_file_list (list): downloaded file list with parameters
        Returns:
            str: resulting report
        """

        # # Setting counters / Установка счетчиков
        successfully_download = 0
        failed_to_download = 0
        no_messages_found = 0
        # Скачивание файлов по списку / Downloading files from a list
        for counter, downloaded_file in enumerate(downloaded_file_list, 1):
            progress = f'{counter} / {len(downloaded_file_list)}'
            dialog = self.get_entity(downloaded_file['dialog_id'])
            message = loop.run_until_complete(
                self.client.get_messages(entity=dialog, ids=downloaded_file['message_id']))
            if message:
                # If the message is found, create a TgFile object and load the file
                # Если сообщение найдено, то создаем объект TgFile и загружаем файл
                tg_file = TgFile(dialog_id=downloaded_file['dialog_id'], message_grouped_id='message_grouped_id',
                                 message=message, message_id=message.id,
                                 description='description',
                                 file_name='', file_path=downloaded_file['file_path'],
                                 alt_text='alt_text',
                                 size=downloaded_file['size'],
                                 file_type=MessageFileTypes.get_file_type_by_type_id(downloaded_file['file_type_id']))
                # Загружаем файл сообщения / Downloading the message file
                status_messages.mess_update('Synchronizing the list of local files with the database',
                                            f'{progress}  Download: {tg_file.file_path}')
                downloading_result = self.download_message_file(tg_file)
                # Depending on the result of the file download, we change the counters
                # В зависимости от результата загрузки файла изменяем счетчики
                if downloading_result:
                    status_messages.mess_update('', f'{progress}  Successfully!')
                    successfully_download += 1
                else:
                    status_messages.mess_update('', f'{progress}  Download failed')
                    failed_to_download += 1
            else:
                status_messages.mess_update('', f'{counter} / {len(downloaded_file_list)} No messages found for '
                                                f'dialog {dialog.title} and message id {downloaded_file["message_id"]}')
                no_messages_found += 1
        # Формирование отчета по результатам загрузки файлов / Generating a report based on file downloading results
        resulting_report = (f'Files to download: {len(downloaded_file_list)};\n '
                            f'Downloaded files: {successfully_download};\n '
                            f'Failed to download files: {failed_to_download};\n '
                            f'No messages found: {no_messages_found}')
        status_messages.mess_update('', resulting_report)
        return resulting_report


def convert_text_hyperlinks(message_text: str | None) -> str | None:
    """
    Converting text hyperlinks of the form [Text](URL) to HTML format
    Преобразование текстовых гиперссылок вида [Text](URL) в HTML формат
    Attributes:
        message_text (str | None): message text
    Returns:
        str | None: converted message text
    """

    if message_text:
        matches = GlobalConst.text_with_url_pattern.findall(message_text)
        if matches:
            for match in matches:
                message_text = message_text.replace(f'[{match[0]}]({match[1]})',
                                                    f'<a href = "{match[1]}" target="_blank" >{match[0]}</a>')
    return message_text


def cleanup_loop():
    """
    Called when the application terminates and closes the event loop if it is open.
    Вызывается при завершении приложения и закрывает цикл событий, если он открыт
    """

    if loop.is_running():
        loop.stop()
    if not loop.is_closed():
        loop.close()
    set_event_loop(None)


# Создаем и сохраняем цикл событий для работы с клиентом Telegram
# Create and save the asyncio event loop for working with the Telegram client
loop = new_event_loop()
set_event_loop(loop)
atexit.register(cleanup_loop)
# Создаем экземпляр TelegramHandler для работы с клиентом Telegram
# Create an object of the TelegramHandler class for working with the Telegram client
tg_handler = TelegramHandler()

if __name__ == "__main__":
    pass
