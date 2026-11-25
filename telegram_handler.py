"""
The module contains classes and functions for working with Telegram (Telethon): dialogs, messages, files, filters.
Модуль содержит классы и функции для работы с Telegram (Telethon): диалоги, сообщения, файлы, фильтры.

class TelegramHandler: a class for handling Telegram operations.
class TgCurrentState: a class to represent the current state of the Telegram client
class TgDialog: a class to represent a Telegram dialog in this program
class TgDialogSortFilter: a class to represent sorting and filtering options of Telegram dialogs
class TgFile: a class to represent a Telegram message file
class TgMessageGroup: a class to represent a Telegram message group in this program
class TgMessageSortFilter: a class to represent sorting and filtering of Telegram message groups.
get_tg_handler: a function returning the shared TelegramHandler (created lazily on the first call)

The asyncio event loop of the Telegram client runs in a background daemon thread owned by TelegramHandler
(see TelegramHandler._run and TelegramHandler.close).
"""

import logging
import shutil
from asyncio import Semaphore, gather, new_event_loop, run_coroutine_threadsafe
from mimetypes import guess_extension
from sys import maxsize
from threading import Event, Lock, Thread, current_thread
from textwrap import shorten
from dataclasses import dataclass
from typing import Any, Callable, cast
from datetime import datetime, timezone
from pathlib import Path
from telethon.tl.custom import Dialog, Message
from telethon.tl.types import MessageMediaPhoto, MessageMediaDocument, PhotoSize, PhotoCachedSize, PhotoStrippedSize, \
    PhotoSizeProgressive, MessageMediaWebPage
from telethon import TelegramClient
from dotenv import dotenv_values
from config import ProjectDirs, GlobalConst, MessageFileTypes, DialogTypes, ensure_profile_selected
from profiles import read_profile_info, write_profile_info
from utils import (parse_date_string, clean_file_path, format_files_report, local_day_start, remove_empty_dirs,
                   status_messages, to_local)
from message_renderer import render_message_html, plain_text_to_html, render_link_html

logger = logging.getLogger(__name__)


class ProfileAccountError(RuntimeError):
    """
    The logged-in Telegram account is not the one the profile belongs to (the launcher reports it as a message)
    Вошедший аккаунт Telegram не тот, которому принадлежит профиль (запускатель сообщает об этом сообщением)
    """


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
        photo_id (int | None): ID of the current photo (avatar) of the chat, None if it has no photo
        entity (Any): Telethon entity of the chat (to download the avatar)
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
        # UTC as Telegram gives it / UTC, как отдает Telegram
        self.last_message_date = dialog.date if dialog.date else None  # type: ignore
        self.type = TgDialog.set_type(dialog.is_channel, dialog.is_group, dialog.is_user)
        self.dialog_dir = clean_file_path(f'{self.title}_{self.dialog_id}')
        # The photo ID comes with the dialog list, so it is known without a request to Telegram
        # ID фото приходит вместе со списком диалогов, поэтому известен без запроса к Telegram
        self.entity = getattr(dialog, 'entity', None)
        photo_id = getattr(getattr(self.entity, 'photo', None), 'photo_id', None)
        self.photo_id = photo_id if isinstance(photo_id, int) else None

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
        description (str): description of the reference message (plain text)
        file_name (str): file name
        file_path (str): full file path
        alt_text (str): alternate text for media file
        size (int): size of file
        file_type (MessageFileTypes): file type
        description_html (str): safe HTML of the description (escaped text, a link with a checked address)
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
    description_html: str = ''

    def is_exists(self) -> bool:
        """
        Checks whether a file exists in the file system
        Проверяет, существует ли файл в файловой системе
        """
        return (Path(ProjectDirs.media_dir) / self.file_path).exists() if self.file_path else False

    @property
    def preview_path(self) -> str:
        """
        The path of the preview of the file relative to the cache directory (`previews/<the path in the media
        directory>`): saving a message moves the file from the cache to the media directory under the same path
        Путь превью файла относительно директории кэша (`previews/<путь в директории медиа>`): при сохранении сообщения
        файл переносится из кэша в директорию медиа по тому же пути
        """
        return f'previews/{self.file_path}' if self.file_path else ''

    def is_cached(self) -> bool:
        """
        Checks whether the preview of the file exists in the cache
        Проверяет, существует ли превью файла в кэше
        """
        return (Path(ProjectDirs.cache_dir) / self.preview_path).exists() if self.file_path else False

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

        file_name = (f'{to_local(date).strftime('%H-%M-%S')}_'
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
        html (str): safe HTML of the message group text (built by `render_message_html`, output with `|safe`)
        plain_text (str): text of the message group without formatting (for search and truncation)
        truncated_text (str): truncated plain text of message group
        sender_id (int | None): message sender ID (the number `message.sender_id`, not the raw `Peer` object)
        files_report (str | None): summary of message group files
        saved_to_db (bool): database saving status
    """

    grouped_id: str
    dialog_id: int
    ids: list[int]
    files: list[TgFile]
    date: datetime | None = None
    html: str = ''
    plain_text: str = ''
    truncated_text: str = ''
    sender_id: int | None = None
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
        # `sender_id` is a number (the marked ID); `message.from_id` is a raw `Peer` object that the database and the
        # templates cannot use. It can be None, e.g. for own outgoing messages in a private chat.
        # `sender_id` - число (маркированный ID); `message.from_id` - сырой объект `Peer`, который не подходит для БД и
        # шаблонов. Может быть None, например у собственных исходящих сообщений в личном чате.
        self.sender_id = message.sender_id if self.sender_id is None else self.sender_id
        # The date stays in UTC as Telegram gives it; the local time is only for display and file names (`to_local`)
        # Дата остается в UTC, как ее отдает Telegram; локальное время - только для показа и имен файлов (`to_local`)
        self.date = message.date if self.date is None else min(self.date, message.date)
        self.ids.append(message.id)
        # `raw_text` has no formatting marks; the formatting is in `entities` and goes to `render_message_html`
        # `raw_text` без знаков форматирования; форматирование лежит в `entities` и обрабатывается `render_message_html`
        if message.raw_text:
            self._append_text(message.raw_text, render_message_html(message.raw_text, message.entities))

    def _append_text(self, plain_text: str, html: str) -> None:
        """
        Appends a text part to the message group: the plain text and its HTML, separated by an empty line
        Добавляет часть текста в группу сообщений: обычный текст и его HTML, через пустую строку
        Attributes:
            plain_text (str): plain text of the part
            html (str): safe HTML of the part
        """
        self.plain_text = '\n\n'.join([self.plain_text, plain_text]).strip() if self.plain_text else plain_text.strip()
        self.html = '<br><br>'.join([self.html, html]) if self.html else html

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
                self._append_text(message_file.description, message_file.description_html)

    def set_files_report(self) -> None:
        """
        Forming a summary string based on the files available in the group messages and their types
        Формирование строки резюме по имеющимся в группе сообщений файлам и их типам
        """

        self.files_report = format_files_report(file.file_type.type_id for file in self.files)

    def set_truncated_text(self) -> None:
        """
        Trimming the length of a message for display in the web interface of the message list
        The plain text is cut, not the HTML, so a tag can never be cut in half
        Обрезание длины текста сообщения для отображения в веб-интерфейсе списка сообщений
        Обрезается обычный текст, а не HTML, поэтому тег не может быть разрезан пополам
        """

        if self.plain_text:
            self.truncated_text = shorten(self.plain_text, width=GlobalConst.truncated_text_length, placeholder='...')

    def get_self_dir(self) -> str:
        """
        Returns the path to the message group directory
        Возвращает путь к директории группы сообщений
        """

        assert self.date is not None, 'The message group must contain the date'
        date_str = to_local(self.date).strftime('%Y-%m-%d')
        return clean_file_path(date_str) or date_str


@dataclass
class TgMessageSortFilter:
    """
    A class to represent sorting and filtering of Telegram message groups
    Класс представляющий параметры сортировки и фильтрации группы сообщений
    """

    # A new filter is neutral (no period); the handler sets the defaults with `set_default_filters()`, like the
    # database handler does. The filter dates are aware (local time of the system): Telethon takes a naive datetime
    # for UTC.
    # Новый фильтр нейтральный (без периода); умолчания задает обработчик через `set_default_filters()`, как и
    # обработчик БД. Даты фильтра aware (локальное время системы): наивную дату Telethon считает UTC.
    _sort_order: bool = True
    _date_from: datetime | None = None
    _date_to: datetime | None = None
    _message_query: str | None = None

    def set_default_filters(self) -> None:
        """
        Sets the default filters of the tab: the last `tg_last_days_by_default` days (from the start of the local day),
        newest first (as the radio buttons of the filter form are set), no text filter.
        Устанавливает фильтры вкладки по умолчанию: последние `tg_last_days_by_default` дней (с начала локального дня),
        сначала новые (как выставлены радиокнопки формы фильтра), фильтра по тексту нет.
        """

        self._sort_order = True
        self._date_from = local_day_start(GlobalConst.tg_last_days_by_default)
        self._date_to = None
        self._message_query = None

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
        self._date_to = parse_date_string(value, end_of_day=True)  # the last day is included / последний день включен

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
        # A group without a date goes first/last; the key must be aware like the dates (aware and naive do not compare)
        # Группа без даты идет первой/последней; ключ должен быть aware, как даты (aware и naive не сравниваются)
        return sorted(message_group_list, key=lambda group: group.date or datetime.min.replace(tzinfo=timezone.utc),
                      reverse=self.sort_order)


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

        ensure_profile_selected()
        # Load Telegram connection settings from file / Загружаем настройки подключения к Telegram из файла
        self._connection_settings = dotenv_values(ProjectDirs.telegram_settings_file)
        # The handler's own message filter with the defaults (the last days, newest first), like the database handler;
        # the form of the tab shows its dates. The list of messages stays empty until a chat is selected.
        # Собственный фильтр сообщений обработчика с умолчаниями (последние дни, сначала новые), как у обработчика БД;
        # форма вкладки показывает его даты. Список сообщений пуст, пока не выбран чат.
        self.message_sort_filter = TgMessageSortFilter()
        self.message_sort_filter.set_default_filters()
        # Start the event loop of the Telegram client in a background daemon thread
        # Запускаем цикл событий клиента Telegram в фоновом потоке (daemon)
        self._loop = new_event_loop()
        loop_started = Event()
        # The callback runs only when the loop is actually running: Telethon checks loop.is_running() in start()
        # Колбэк выполнится, только когда loop реально запущен: Telethon проверяет loop.is_running() в start()
        self._loop.call_soon_threadsafe(loop_started.set)
        self._loop_thread = Thread(target=self._loop.run_forever, name='telethon-loop', daemon=True)
        self._loop_thread.start()
        loop_started.wait()
        try:
            # Creating and launching a Telegram client / Создаем и запускаем клиент Telegram
            # Telethon ignores the loop argument: client.loop is the loop running in the calling thread,
            # so every call that touches client.loop must be made from inside our loop thread
            # Telethon игнорирует аргумент loop: client.loop - это loop, запущенный в вызывающем потоке,
            # поэтому все вызовы, которые обращаются к client.loop, делаем из потока нашего loop
            # The session file is in the directory of the profile (Telethon adds the `.session` extension)
            # Файл сессии лежит в каталоге профиля (расширение `.session` добавляет Telethon)
            ProjectDirs.session_file.parent.mkdir(parents=True, exist_ok=True)
            self.client = TelegramClient(str(ProjectDirs.session_file),
                                         int(self._connection_settings['API_ID']),
                                         self._connection_settings['API_HASH'])

            async def start_client():
                await self.client.start(self._connection_settings['PHONE'], self._connection_settings['PASSWORD'])

            self._run(start_client())
            # Get your Telegram username / Получаем имя пользователя Telegram
            self.me = self._run(self.client.get_me())
            # The account must be the one the profile belongs to / Аккаунт должен быть тем, которому принадлежит профиль
            self._check_profile_account()
            # Get a list of all Telegram account dialogues / Получаем список всех диалогов аккаунта Telegram
            self.all_dialogues_list = self.get_dialog_list()
            # Set the current status of the Telegram client / Устанавливаем текущее состояние клиента Telegram
            self.current_state.dialog_list = list(self.all_dialogues_list)
            if self.current_state.dialog_list:
                # Get the first dialog ID / Получаем ID первого диалога
                self.current_state.selected_dialog_id = self.current_state.dialog_list[0].dialog_id
            self.current_state.message_group_list = []
            self.current_state.message_details = None
        except BaseException:
            # Do not leave the loop thread running if the login failed or was interrupted
            # Не оставляем поток loop работать, если вход не удался или был прерван
            self.close()
            raise

    def _check_profile_account(self) -> None:
        """
        Compares the ID of the logged-in account with the one in `profile.json` of the profile; the first login
        writes the ID and the name there (the name is refreshed on every start). A different account is refused:
        its messages would get into the archive of another one.
        Сверяет ID вошедшего аккаунта с ID в `profile.json` профиля; при первом входе ID и имя записываются туда
        (имя обновляется при каждом запуске). Другой аккаунт не допускается: его сообщения попали бы в архив чужого.
        """

        saved_id = read_profile_info(ProjectDirs.profile_dir).get('user_id')
        if saved_id is not None and saved_id != self.me.id:
            raise ProfileAccountError(
                f'The profile belongs to the Telegram account {saved_id}, but the session is of {self.me.id}: '
                f'use another profile or remove {ProjectDirs.profile_info_file}\n'
                f'Профиль принадлежит аккаунту Telegram {saved_id}, а сессия - аккаунта {self.me.id}: '
                f'выберите другой профиль или удалите {ProjectDirs.profile_info_file}')
        name = ' '.join(filter(None, [self.me.first_name, self.me.last_name])) or self.me.username or str(self.me.id)
        write_profile_info(ProjectDirs.profile_dir, self.me.id, name)

    def _run(self, coro):
        """
        Runs a coroutine in the Telethon event loop thread and waits for its result (no timeout).
        Выполняет корутину в потоке цикла событий Telethon и ждет результат (без таймаута).
        Args:
            coro: the coroutine to run
        Returns:
            the result of the coroutine
        """

        if current_thread() is self._loop_thread:
            # Waiting for the loop from inside the loop would block it forever
            # Ожидание loop из самого loop заблокировало бы его навсегда
            coro.close()
            raise RuntimeError('TelegramHandler._run() must not be called from the Telethon loop thread')
        return run_coroutine_threadsafe(coro, self._loop).result()

    def close(self):
        """
        Disconnects the Telegram client and stops the event loop thread. Safe to call more than once.
        Отключает клиент Telegram и останавливает поток цикла событий. Можно вызывать повторно.
        """

        if self._loop.is_closed():
            return
        if self._loop_thread.is_alive():
            client = getattr(self, 'client', None)
            if client is not None:
                # disconnect() creates a task in the loop, so it must be called from inside the loop thread
                # disconnect() создает задачу в loop, поэтому его нужно вызывать из потока loop
                async def disconnect_client():
                    await client.disconnect()

                try:
                    self._run(disconnect_client())
                except Exception as error:
                    logger.warning('Telegram client disconnect error: %s', error)
            self._loop.call_soon_threadsafe(self._loop.stop)
            self._loop_thread.join(timeout=5)
        if not self._loop.is_running():
            self._loop.close()

    def get_entity(self, entity_id: int) -> Any:
        """
        Getting a Telegram entity by its ID
        Получение Telegram сущности по ее ID
        Attributes:
            entity_id (int): entity ID
        Returns:
            Any: Telegram entity
        """
        entity = self._run(self.client.get_entity(entity_id))
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
        dialogs = self._run(self.client.get_dialogs())
        dialog_list = []
        for dialog in dialogs:
            tg_dialog = TgDialog(dialog)
            if tg_dialog.dialog_id == self.me.id:
                tg_dialog.title = GlobalConst.me_dialog_title
            if self.dialog_sort_filter.check_filters(tg_dialog):
                dialog_list.append(tg_dialog)
        status_messages.mess_update('Loading chat lists', f'{len(dialog_list)} chats loaded from Telegram')
        self.sync_avatars(dialog_list)
        return self.dialog_sort_filter.sort_dialog_list(dialog_list)

    def sync_avatars(self, dialog_list: list[TgDialog]) -> None:
        """
        Brings the avatars of the chats in the cache (`cache/_avatars/<dialog_id>/<photo_id>.jpg`) up to date: a chat
        whose current photo is already there is skipped (without a request), otherwise the small photo is downloaded
        (several at once) and the older files of the chat are deleted. A chat without a photo loses its old avatars.
        A failure of one avatar does not stop the others: it is tried again on the next load of the list.
        Приводит аватарки чатов в кэше (`cache/_avatars/<dialog_id>/<photo_id>.jpg`) в актуальное состояние: чат, у
        которого текущее фото уже есть, пропускается (без запроса), иначе маленькое фото скачивается (по несколько
        одновременно), а прежние файлы чата удаляются. Чат без фото теряет старые аватарки. Сбой одной аватарки не
        останавливает остальные: она будет запрошена снова при следующей загрузке списка.
        Attributes:
            dialog_list (list[TgDialog]): the chats whose avatars are checked
        """

        avatars_dir = Path(ProjectDirs.cache_dir) / GlobalConst.cache_avatars_dir
        jobs: list[tuple[TgDialog, Path]] = []
        for tg_dialog in dialog_list:
            dialog_dir = avatars_dir / str(tg_dialog.dialog_id)
            if tg_dialog.photo_id is None:
                if dialog_dir.is_dir():
                    shutil.rmtree(dialog_dir, ignore_errors=True)
                continue
            avatar_path = dialog_dir / f'{tg_dialog.photo_id}.jpg'
            if not avatar_path.exists():
                jobs.append((tg_dialog, avatar_path))
        if not jobs:
            return
        status_messages.mess_update('', f'Downloading chat avatars: {len(jobs)}')

        async def download_all() -> int:
            limit = Semaphore(GlobalConst.avatar_parallel_downloads)

            async def download_one(tg_dialog: TgDialog, avatar_path: Path) -> bool:
                async with limit:
                    temp_path = avatar_path.with_name(f'{avatar_path.name}.part')
                    try:
                        avatar_path.parent.mkdir(parents=True, exist_ok=True)
                        # The file appears under its final name only when it is complete
                        # Файл появляется под окончательным именем, только когда он загружен полностью
                        if not await self.client.download_profile_photo(tg_dialog.entity, file=temp_path,
                                                                        download_big=False):
                            return False
                        temp_path.replace(avatar_path)
                        for old_path in avatar_path.parent.glob('*.jpg'):
                            if old_path != avatar_path:
                                old_path.unlink(missing_ok=True)
                        return True
                    except Exception as error:  # pylint: disable=broad-exception-caught
                        logger.warning('Avatar of the chat %s was not downloaded: %s', tg_dialog.dialog_id, error)
                        temp_path.unlink(missing_ok=True)
                        return False

            return sum(await gather(*(download_one(tg_dialog, path) for tg_dialog, path in jobs)))

        downloaded = self._run(download_all())
        status_messages.mess_update('', f'Chat avatars downloaded: {downloaded} of {len(jobs)}')

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
            message_from = self._run(
                self.client.get_messages(entity=dialog, offset_date=self.message_sort_filter.date_from, limit=1))
            message_filters['min_id'] = message_from[0].id if message_from else 0
        # Set filter parameters by maximum date via message ID
        # Устанавливаем параметры фильтрации по максимальной дате через id сообщений
        if self.message_sort_filter.date_to:
            message_to = self._run(
                self.client.get_messages(entity=dialog, offset_date=self.message_sort_filter.date_to, limit=1,
                                         reverse=True))
            message_filters['max_id'] = message_to[0].id if message_to else maxsize
        # Setting the sort order parameter by date / Установка параметра порядка сортировки по дате
        message_filters['reverse'] = self.message_sort_filter.sort_order
        # Getting a list of messages according to filters / Получение списка сообщений в соответствии с фильтрами
        message_list = self._run(self.client.get_messages(**message_filters))
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
                if not self.message_sort_filter.message_query.lower() in message_group.plain_text.lower():
                    message_group_list.remove(message_group)
        # Post-processing of the generated message group / Постобработка сформированной группы сообщений
        for tg_message_group in message_group_list:
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
        message_date_str = to_local(current_message_group.date).strftime(GlobalConst.message_datetime_format)
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
                      'html': current_message_group.html,
                      'files': current_message_group.files,
                      'files_report': current_message_group.files_report if current_message_group.files_report else '',
                      'saved_to_db': current_message_group.saved_to_db}
        # Download the previews of the files, except videos, contained in the detailed message, to the cache (a saved
        # message has its files in the media directory, they are not downloaded again)
        # Скачиваем превью файлов, кроме видео, содержащихся в детальном сообщении, в кэш (у сохраненного сообщения
        # файлы лежат в директории медиа, повторно они не скачиваются)
        tg_details_files = cast(list[TgFile], tg_details.get('files', []))
        for tg_file in tg_details_files:
            if not tg_file.is_exists() and not tg_file.is_cached():
                if tg_file.file_type != MessageFileTypes.VIDEO:
                    status_messages.mess_update('', f'Downloading file {tg_file.file_path}')
                    self.download_message_file(tg_file, to_cache=True)
        tg_details['existing_files'] = [tg_file for tg_file in tg_details_files
                                        if tg_file.is_exists() or tg_file.is_cached()]
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
        # The description is kept as plain text and as safe HTML (escaped text, a link with a checked address)
        # Описание хранится как обычный текст и как безопасный HTML (экранированный текст, ссылка с проверенным адресом)
        description = ''
        description_html = ''
        if file_type == MessageFileTypes.WEBPAGE:
            if hasattr(message.media.webpage, 'url') and message.media.webpage.url:
                description = message.media.webpage.url
                description_html = render_link_html(description, description)
            if hasattr(message.media.webpage, 'description') and message.media.webpage.description:
                page_description = shorten(message.media.webpage.description,
                                           width=GlobalConst.truncated_text_length, placeholder='...')
                description = '\n\n'.join(filter(None, [description, page_description]))
                description_html = '<br><br>'.join(filter(None, [description_html,
                                                                 plain_text_to_html(page_description)]))
        # Creating TgFile object / Создаем объект TgFile
        tg_file = TgFile(dialog_id=dialog_id, message_grouped_id=message_group.grouped_id,
                         message=message, message_id=message.id,
                         description=description, description_html=description_html,
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

    def download_message_file(self, tg_file: TgFile, to_cache: bool = False) -> str | None:
        """
        Downloading a message file to the media directory (saving a message), or to the cache of previews. Saving
        takes a file that is already in the cache from there (moves it), without downloading it again.
        Загрузка файла сообщения в директорию медиа (сохранение сообщения) или в кэш превью. При сохранении файл,
        который уже есть в кэше, берется оттуда (переносится), без повторной загрузки.
        Attributes:
            tg_file (TgFile): message file object
            to_cache (bool): True - download the preview to the cache (`cache/previews/...`), the file is not saved
        Returns:
            str | None: message file path if downloaded, else None
        """

        downloading_param = {}
        result = None
        media_path = Path(ProjectDirs.media_dir) / tg_file.file_path
        target_path = Path(ProjectDirs.cache_dir) / tg_file.preview_path if to_cache else media_path
        # Checking file existence / Проверка существования файла
        if media_path.exists() or (to_cache and target_path.exists()):
            # If the file already exists, return its path / Если файл уже существует, то возвращаем его путь
            result = tg_file.file_path
        elif not to_cache and tg_file.is_cached():
            # The preview of the file is in the cache: move it to the media directory under the same relative path
            # Превью файла есть в кэше: переносим его в директорию медиа по тому же относительному пути
            media_path.parent.mkdir(parents=True, exist_ok=True)
            cached_path = Path(ProjectDirs.cache_dir) / tg_file.preview_path
            shutil.move(cached_path, media_path)
            # The directories of the preview are left empty: nothing else would delete them
            # Каталоги превью остались пустыми: больше их никто не удалит
            remove_empty_dirs(cached_path.parent, Path(ProjectDirs.cache_dir) / 'previews')
            result = tg_file.file_path
        # Check file size is 0 < tg_file.size <= GlobalConst.max_download_file_size
        # Проверка размера файла на 0 < tg_file.size <= GlobalConst.max_download_file_size
        elif 0 < tg_file.size <= GlobalConst.max_download_file_size:
            # Create the appropriate directories, if necessary, and download the file
            # Создаем соответствующие директории, при необходимости, и загружаем файл
            target_path.parent.mkdir(parents=True, exist_ok=True)
            downloading_param['message'] = tg_file.message
            downloading_param['file'] = target_path
            if tg_file.file_type == MessageFileTypes.THUMBNAIL:
                downloading_param['thumb'] = -1
            result = self._run(self.client.download_media(**downloading_param))
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
            message = self._run(
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


# Экземпляр TelegramHandler создается лениво, при первом вызове get_tg_handler(), а не при импорте модуля:
# конструктор подключается к Telegram и может запросить код входа.
# The TelegramHandler instance is created lazily on the first get_tg_handler() call, not on module import:
# the constructor connects to Telegram and may ask for a login code.
_tg_handler: TelegramHandler | None = None
_tg_handler_lock = Lock()


def get_tg_handler() -> TelegramHandler:
    """
    Returns the shared TelegramHandler, creating it on the first call.
    Возвращает общий TelegramHandler, создавая его при первом вызове.
    Returns:
        TelegramHandler: the single instance for working with the Telegram client
    """

    global _tg_handler
    if _tg_handler is None:
        # The lock prevents two threads from creating two clients at the same time
        # Замок не дает двум потокам одновременно создать два клиента
        with _tg_handler_lock:
            if _tg_handler is None:
                _tg_handler = TelegramHandler()
    return _tg_handler


if __name__ == "__main__":
    pass
