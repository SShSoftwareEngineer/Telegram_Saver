import re
from asyncio import new_event_loop, set_event_loop
from mimetypes import guess_extension
from sys import maxsize
from telethon.tl.custom import Dialog, Message
from telethon.tl.types import MessageMediaPhoto, MessageMediaDocument, PhotoSize, PhotoCachedSize, PhotoStrippedSize, \
    PhotoSizeProgressive, MessageMediaWebPage
from pathlib import Path
from textwrap import shorten
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from telethon import TelegramClient
from configs.config import ProjectDirs, ProjectConst, MessageFileTypes, DialogTypes

# Создаем и сохраняем цикл событий
loop = new_event_loop()
set_event_loop(loop)


@dataclass
class TgDialog:
    """
    A class to represent a Telegram dialog in this program.
    """
    dialog_id: int
    title: str
    unread_count: int = 0
    last_message_date: Optional[datetime] = None
    type: DialogTypes = DialogTypes.Unknown

    def __init__(self, dialog: Dialog):
        self.dialog_id = dialog.id
        if dialog.title:
            self.title = dialog.title
        elif dialog.name:
            self.title = dialog.name
        else:
            self.title = 'No title'
        self.unread_count = dialog.unread_count if dialog.unread_count else 0
        self.last_message_date = dialog.date.astimezone() if dialog.date else None  # type: ignore
        self.type = TgDialog.set_type(dialog.is_channel, dialog.is_group, dialog.is_user)

    @staticmethod
    def set_type(is_channel: bool, is_group: bool, is_user: bool) -> DialogTypes:
        """
        Returns the type name for a given dialog type.
        """
        if is_channel:
            return DialogTypes.Channel
        elif is_group:
            return DialogTypes.Group
        elif is_user:
            return DialogTypes.User
        else:
            return DialogTypes.Unknown


@dataclass
class TgDialogSortFilter:
    """
    A class to represent sorting and filtering of Telegram dialogs.
    """
    _sorting_field = None
    _sort_order: bool = False
    _dialog_type: Optional[DialogTypes] = None
    _title_query: Optional[str] = None

    @staticmethod
    def _sort_by_title(x):
        return x.title

    @staticmethod
    def _sort_by_last_message_date(x):
        return x.last_message_date

    def sort_field(self, value: str):
        """
        Устанавливает поле сортировки
        """
        self._sorting_field = self._sort_by_title if value == '0' else self._sort_by_last_message_date

    def sort_order(self, value: str):
        """
        Устанавливает порядок сортировки
        """
        self._sort_order = False if value == '0' else True

    def dialog_type(self, value: str):
        """
        Устанавливает фильтр по типу диалогов
        """
        match value:
            case '0':
                self._dialog_type = None
            case '1':
                self._dialog_type = DialogTypes.Channel
            case '2':
                self._dialog_type = DialogTypes.Group
            case '3':
                self._dialog_type = DialogTypes.User
            case _:
                self._dialog_type = DialogTypes.Unknown

    def title_query(self, value: str):
        """
        Устанавливает фильтр по названию диалогов
        """
        self._title_query = value if value else None

    def check_filters(self, tg_dialog: TgDialog) -> bool:
        """
        Проверка фильтров по подстроке в названии и по типу для конкретного диалога
        """
        title_query = True
        if self._title_query:
            title_query = self._title_query.lower() in str(tg_dialog.title).lower()
        dialog_type = True
        if self._dialog_type:
            dialog_type = tg_dialog.type == self._dialog_type
        return all([title_query, dialog_type])

    def sort_dialog_list(self, dialog_list: List[TgDialog]) -> List[TgDialog]:
        """
        Сортировка списка диалогов по заданному полю в заданном порядке
        """
        if self._sorting_field is None:
            self._sorting_field = self._sort_by_title
        result = sorted(dialog_list, key=self._sorting_field, reverse=self._sort_order)
        return result


@dataclass
class TgFile:
    """
    A class to represent a Telegram message file.
    """
    dialog_id: int
    message_grouped_id: str
    message: Message
    message_id: int
    full_path: str
    web_path: str
    description: str
    alt_text: str
    size: int
    file_type: MessageFileTypes = MessageFileTypes.UNKNOWN

    def __init__(self, dialog_id: int, message_grouped_id: str, message: Message, full_path: str, web_path: str,
                 description: str, alt_text: str, size: int, file_type: MessageFileTypes):
        self.dialog_id = dialog_id
        self.message_grouped_id = message_grouped_id
        self.message = message
        self.message_id = message.id
        self.full_path = full_path
        self.web_path = web_path
        self.size = size
        self.description = description
        self.alt_text = alt_text
        self.file_type = file_type


@dataclass
class TgMessageGroup:
    """
    A class to represent a Telegram message group in this program.
    """
    grouped_id: str
    dialog_id: int
    ids: List[int]
    files: List[TgFile]
    date: Optional[datetime] = None
    from_id: Optional[int] = None
    reply_to: Optional[int] = None
    text: str = ''
    truncated_text: str = ''
    files_report: Optional[str] = ''
    selected: bool = False

    def __init__(self, grouped_id: str, dialog_id: int):
        self.grouped_id = grouped_id
        self.dialog_id = dialog_id
        self.ids = []
        self.files = []

    def add_message(self, message: Message, message_file: Optional[TgFile] = None) -> None:
        """
        Добавляет сообщение в группу сообщений
        """
        self.from_id = message.from_id if self.from_id is None else self.from_id
        self.reply_to = message.reply_to if self.reply_to is None else self.reply_to
        self.date = message.date.astimezone() if self.date is None else min(self.date, message.date.astimezone())
        self.ids.append(message.id)
        if message.text:
            self.text = message.text if self.text is None else '\n\n'.join([self.text, message.text]).strip()
        if message_file:
            self.files.append(message_file)
            if message_file.description:
                self.text = message_file.description if self.text is None else '\n\n'.join(
                    [self.text, message_file.description]).strip()

    def set_files_report(self) -> None:
        """
        Формирование строки отчета по имеющимся в группе сообщений файлам и их типам
        """
        alt_texts = set()
        for file in self.files:
            if file.file_type == MessageFileTypes.THUMBNAIL:
                # Если есть файл с видео, то заменяем в отчете тип файла thumbnail на video
                alt_texts.add(MessageFileTypes.VIDEO.alt_text)
            else:
                alt_texts.add(file.alt_text)
        self.files_report = ' '.join(sorted(alt_texts))

    def text_hyperlink_conversion(self) -> None:
        """
        Преобразование текстовых гиперссылок вида [Text](URL) в HTML формат
        """
        if self.text:
            self.text = convert_text_hyperlinks(self.text)

    def set_truncated_text(self) -> None:
        """
        Ограничение длины текста сообщения для отображения в веб-интерфейсе списка сообщений
        """
        if self.text:
            # Если текст сообщения не содержит гиперссылок обрезаем до заданной длины
            if any([self.text.find('<a href') == -1,
                    self.text.find('<a href') > ProjectConst.truncated_text_length]):
                self.truncated_text = shorten(self.text, width=ProjectConst.truncated_text_length, placeholder='...')
            else:
                self.truncated_text = shorten(self.text, width=ProjectConst.truncated_text_length + 50,
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

        # <a href = "https://cutt.ly/DrnDxWzA" target = "_blank" >«Перезавантаження: розширення можливостей для працевлаштування» </a>
        # shorten             из             модуля             textwrap


# TODO: продумать, возможно сохранять текст сообщения в HTML файл с локальными ссылками на файлы
# TODO: проверить на загрузку сообщения с разными типами приложений, почему возвращает ошибку при Unknown, проверить загрузку видео и аудио
# TODO: проверить превращение статусной строки в ссылку в Message_Group


@dataclass
class TgMessageSortFilter:
    _sort_order: bool = True
    _date_from: Optional[datetime] = datetime.now() - timedelta(days=ProjectConst.last_days_by_default)
    _date_to: Optional[datetime] = None
    _message_query: Optional[str] = None
    date_from_default: Optional[str] = (datetime.now() - timedelta(
        days=ProjectConst.last_days_by_default)).strftime('%d/%m/%Y')

    def set_default_filters(self):
        """
        Устанавливает фильтры по умолчанию
        """
        self._sort_order = True
        self._date_from = datetime.now() - timedelta(days=ProjectConst.last_days_by_default)
        self._date_to = None
        self._message_query = None
        self.date_from_default = self.date_from.strftime('%d/%m/%Y')

    @staticmethod
    def set_date(date_str: str) -> Optional[datetime]:
        """
        Декодирование даты из строки
        """
        if date_str:
            date_split = re.split(r'[/.-]', date_str)
            if len(date_split) == 3:
                dd, mm, yyyy = date_split
                try:
                    return datetime(int(yyyy), int(mm), int(dd))
                except ValueError:
                    return None
        return None

    @property
    def sort_order(self) -> bool:
        """
        Возвращает порядок сортировки сообщений по дате
        """
        return self._sort_order

    @sort_order.setter
    def sort_order(self, value: str):
        """
        Устанавливает порядок сортировки сообщений по дате
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
        self._date_from = self.set_date(value)

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
        self._date_to = self.set_date(value)

    @property
    def message_query(self) -> Optional[str]:
        """
        Возвращает фильтр по названию диалогов
        """
        return self._message_query

    @message_query.setter
    def message_query(self, value: str):
        """
        Устанавливает фильтр по названию диалогов
        """
        self._message_query = value if value else None

    def sort_message_group_list(self, message_group_list: List[TgMessageGroup]) -> List[TgMessageGroup]:
        """
        Сортировка списка групп сообщений по дате
        """
        result = sorted(message_group_list, key=lambda group: group.date, reverse=self.sort_order)
        return result


@dataclass
class TgDetails:
    """
    A class to represent details of a Telegram message.
    """
    dialog_id: int
    message_group_id: str
    date: datetime
    text: str
    files: List[TgFile]
    files_report: Optional[str] = ''

    def __init__(self, dialog_id: int, message_group_id: str, date: datetime, text: str,
                 files: List[TgFile], files_report: Optional[str] = None):
        self.dialog_id = dialog_id
        self.message_group_id = message_group_id
        self.date = date
        self.text = text
        self.files = files
        self.files_report = files_report if files_report else ''


@dataclass
class TgCurrentState:
    dialog_list: List[TgDialog] = None
    selected_dialog_id: int = None
    message_group_list: List[TgMessageGroup] = None
    selected_message_group_id: str = None
    message_details: Dict[str, Any] = None
    message_files: Dict[str, Dict[str, Any]] = None


class TelegramHandler:
    all_dialogues_list: List[TgDialog] = None
    dialog_sort_filter: TgDialogSortFilter = TgDialogSortFilter()
    message_sort_filter: TgMessageSortFilter = TgMessageSortFilter()
    current_state: TgCurrentState = TgCurrentState()

    def __init__(self):
        # Загружаем настройки подключения к Telegram из файла
        self._connection_settings = dict()
        with open(ProjectDirs.telegram_settings_file, 'r', encoding='utf-8') as file_env:
            for line in file_env:
                if not line.strip().startswith('#') and '=' in line:
                    key, value = line.strip().split('=')
                    self._connection_settings[key] = value
        # Создаем и запускаем клиент Telegram
        self.client = TelegramClient(self._connection_settings['SESSION_NAME'],
                                     int(self._connection_settings['API_ID']),
                                     self._connection_settings['API_HASH'], loop=loop)
        self.client.start(self._connection_settings['PHONE'], self._connection_settings['PASSWORD'])
        # Получаем список всех диалогов аккаунта Telegram
        self.all_dialogues_list = self.get_dialog_list()
        self.current_state.dialog_list = self.all_dialogues_list

    def get_entity(self, entity_id: int) -> Any:
        """
        Получение Telegram сущности по id
        """
        entity = loop.run_until_complete(self.client.get_entity(entity_id))
        return entity

    def get_dialog_by_id(self, dialog_id: int) -> Optional[TgDialog]:
        """
        Получение диалога по id
        """
        found_tg_dialog = next((x for x in self.all_dialogues_list if x.dialog_id == dialog_id), None)
        return found_tg_dialog

    @staticmethod
    def get_message_group_by_id(message_group_list: list, grouped_id: str) -> Optional[TgMessageGroup]:
        """
        Получение группы сообщений по grouped_id
        """
        found_tg_message_group = next((x for x in message_group_list if x.grouped_id == grouped_id), None)
        return found_tg_message_group

    def get_dialog_list(self) -> List[TgDialog]:
        """
        Получение списка всех диалогов Telegram с учетом фильтров и сортировки
        """
        print('Chats list loading...')
        dialogs = loop.run_until_complete(self.client.get_dialogs())
        dialog_list = []
        for dialog in dialogs:
            tg_dialog = TgDialog(dialog)
            if self.dialog_sort_filter.check_filters(tg_dialog):
                dialog_list.append(tg_dialog)
        print(f'{len(dialog_list)} chats loaded')
        return self.dialog_sort_filter.sort_dialog_list(dialog_list)

    def get_message_list(self, dialog_id: int) -> List[Message]:
        """
        Получение списка сообщений из заданного чата с учетом фильтров и сортировки
        """
        current_tg_dialog = self.get_dialog_by_id(dialog_id)
        if current_tg_dialog:
            print(f'Loading messages for "{current_tg_dialog.title}" dialog...')
        # Получаем сущность диалога по id
        dialog = self.get_entity(dialog_id)
        # Формируем текущие данные фильтра сообщений
        message_filters = {'entity': dialog}
        # Устанавливаем параметры фильтрации по минимальной дате через id сообщений
        if self.message_sort_filter.date_from:
            message_from = loop.run_until_complete(
                self.client.get_messages(entity=dialog, offset_date=self.message_sort_filter.date_from, limit=1))
            message_filters['min_id'] = message_from[0].id if message_from else 0
        # Устанавливаем параметры фильтрации по максимальной дате через id сообщений
        if self.message_sort_filter.date_to:
            message_to = loop.run_until_complete(
                self.client.get_messages(entity=dialog, offset_date=self.message_sort_filter.date_to, limit=1,
                                         reverse=True))
            message_filters['max_id'] = message_to[0].id if message_to else maxsize
        # Установка параметра порядка сортировки по дате
        message_filters['reverse'] = self.message_sort_filter.sort_order
        # Получение сообщений в соответствии с фильтрами
        message_list = loop.run_until_complete(self.client.get_messages(**message_filters))
        print(f'{len(message_list)} messages loaded')
        return message_list

    def get_message_group_list(self, dialog_id: int) -> List[TgMessageGroup]:
        """
        Формирование списка групп сообщений из сообщений заданного чата с учетом фильтров, сортировки и группировки
        """
        # Создание списка групп сообщений с учетом параметра группировки и фильтра по тексту
        message_group_list = []
        # Составление списка сообщений с учетом группировки по message.grouped_id
        for message in self.get_message_list(dialog_id):
            # Если message.grouped_id сообщения не установлен, то используем строку "Message_{message.id}"
            message_grouped_id = str(message.grouped_id) if message.grouped_id else f'Message_{message.id}'
            # Проверяем существование группы сообщений с текущим grouped_id
            tg_message_group = self.get_message_group_by_id(message_group_list, message_grouped_id)
            # Если группа сообщений с текущим grouped_id не существует, создаем ее и добавляем в список групп сообщений
            if tg_message_group is None:
                tg_message_group = TgMessageGroup(message_grouped_id, dialog_id)
                message_group_list.append(tg_message_group)
            # Получаем информацию о файле сообщения, если он есть
            message_file = self.get_message_file_info(dialog_id, message_grouped_id, message)
            # Добавляем текущее сообщение и его файл, если он есть, в соответствующую группу сообщений
            tg_message_group.add_message(message, message_file)
        # Применение фильтра по тексту группы сообщений, если он задан
        if self.message_sort_filter.message_query:
            for message_group in message_group_list.copy():
                if not self.message_sort_filter.message_query.lower() in message_group.text.lower():
                    message_group_list.remove(message_group)
        # Постобработка сформированной группы сообщений
        for tg_message_group in message_group_list:
            # Преобразование текстовых гиперссылок вида [Text](URL) в HTML формат
            tg_message_group.text_hyperlink_conversion()
            # Формирование строки отчета по имеющимся в группе сообщений файлам и их типам
            tg_message_group.set_files_report()
            # Ограничение длины текста сообщения для отображения в веб-интерфейсе списка сообщений
            tg_message_group.set_truncated_text()
        print(f'{len(message_group_list)} message groups were formed')
        return self.message_sort_filter.sort_message_group_list(message_group_list)

    def get_message_detail(self, message_group_id: str) -> TgDetails:
        """
        Получение сообщения по id диалога и id группы сообщений
        """
        # Получаем текущую группу сообщений по id
        current_message_group = self.get_message_group_by_id(self.current_state.message_group_list, message_group_id)
        message_date_str = current_message_group.date.strftime(ProjectConst.message_datetime_format)
        print(f'Message {message_date_str} details loading...')
        tg_details = TgDetails(dialog_id=current_message_group.dialog_id,
                               message_group_id=message_group_id,
                               date=current_message_group.date,
                               text=current_message_group.text if current_message_group.text else '',
                               files=current_message_group.files,
                               # sorted(current_message_group.files, key=lambda x: x[fil_field['type']]),
                               files_report=current_message_group.files_report if current_message_group.files_report else '')
        # Преобразование текстовых гиперссылок вида [Text](URL) в HTML формат
        tg_details.text = convert_text_hyperlinks(tg_details.text)
        # Скачиваем файлы, содержащиеся в детальном сообщении, если их нет в файловой системе
        for tg_file in tg_details.files:
            if not Path(tg_file.full_path).exists():
                print(f'Downloading file {tg_file.full_path}...')
                self.download_message_file(tg_file)
        print('Message details loaded')
        return tg_details

    def get_message_file_info(self, dialog_id: int, message_grouped_id: str, message,
                              thumbnail: bool = True) -> Optional[TgFile]:
        """
        Получение информации о файле сообщения
        Определение типа файла, его расширения и размера, формирование пути к файлу
        """

        def get_image_size(images: list) -> int:
            """
            Определяет максимальный из возможных размер изображения в сообщении
            """
            max_image_size = 0
            for image in images:
                if isinstance(image, PhotoSize):
                    max_image_size = max(image.size, max_image_size)
                elif isinstance(image, PhotoCachedSize) or isinstance(image, PhotoStrippedSize):
                    max_image_size = max(len(image.bytes), max_image_size)
                elif isinstance(image, PhotoSizeProgressive):
                    max_image_size = max(max(image.sizes), max_image_size)
            return max_image_size

        if not message.file:
            return None
        # Определяем тип файла
        mess_doc = None
        file_type = MessageFileTypes.UNKNOWN
        if isinstance(message.media, MessageMediaPhoto):
            file_type = MessageFileTypes.PHOTO
        elif isinstance(message.media, MessageMediaWebPage):
            file_type = MessageFileTypes.WEBPAGE
        elif isinstance(message.media, MessageMediaDocument):
            mess_doc = message.media.document
            if mess_doc.mime_type.startswith('image/'):
                file_type = MessageFileTypes.IMAGE
            elif mess_doc.mime_type.startswith('audio/'):
                file_type = MessageFileTypes.AUDIO
            elif not thumbnail and mess_doc.mime_type.startswith('video/'):
                file_type = MessageFileTypes.VIDEO
            elif all([thumbnail, hasattr(mess_doc, 'thumbs'), mess_doc.thumbs]):
                file_type = MessageFileTypes.THUMBNAIL
        # Определяем расширение файла
        if file_type == MessageFileTypes.UNKNOWN:
            file_ext = getattr(message.file, 'ext', None)
            if file_ext is None:
                file_ext = guess_extension(mess_doc.mime_type)
            if file_ext is None:
                file_ext = MessageFileTypes.UNKNOWN.default_ext
        else:
            file_ext = file_type.default_ext
        # Получаем размер файла
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
        # Получаем описание файла
        description = ''
        if file_type == MessageFileTypes.WEBPAGE:
            if hasattr(message.media.webpage, 'url') and message.media.webpage.url:
                description = f'<a href = "{message.media.webpage.url}" target="_blank" >{message.media.webpage.url}</a>'
            if hasattr(message.media.webpage, 'description') and message.media.webpage.description:
                description = '\n\n'.join([description,
                                           shorten(message.media.webpage.description,
                                                   width=ProjectConst.truncated_text_length, placeholder='...')])
        # Формирование локального пути к файлу
        dialog_dir = f'{self.get_dialog_by_id(dialog_id).title}_{dialog_id}'
        message_time = message.date.astimezone().strftime('%H-%M-%S')
        file_name = f'{message_time}_{file_type.sign}_{message_grouped_id}_{message.id}{file_ext}'
        full_path = Path(ProjectDirs.media_dir) / clean_file_path(dialog_dir) / message.date.astimezone().strftime(
            '%Y-%m-%d') / file_name
        # Создаем объект TgFile с информацией о файле сообщения
        tg_file = TgFile(dialog_id=dialog_id,
                         message_grouped_id=message_grouped_id,
                         message=message,
                         full_path=full_path,
                         web_path=full_path.as_posix(),
                         description=description,
                         alt_text=file_type.alt_text,
                         size=file_size,
                         file_type=file_type)
        return tg_file

    def download_message_file(self, tg_file: TgFile) -> Optional[str]:
        """
        Загрузка файла сообщения
        """
        downloading_param = dict()
        result = None
        # Проверка существования файла
        if not Path(tg_file.full_path).exists():
            # Проверка размера файла
            if 0 < tg_file.size <= ProjectConst.max_download_file_size:
                # Если нужно, создаем соответствующие директории и загружаем файл
                Path(tg_file.full_path).parent.mkdir(parents=True, exist_ok=True)
                downloading_param['message'] = tg_file.message
                downloading_param['file'] = tg_file.full_path
                if tg_file.file_type == MessageFileTypes.THUMBNAIL:
                    downloading_param['thumb'] = -1
                result = loop.run_until_complete(self.client.download_media(**downloading_param))
        else:
            # Если файл уже существует, то возвращаем его имя
            result = tg_file.full_path
        return result


def clean_file_path(file_path: str | None) -> str | None:
    """
    Очищает имя файла/директории от недопустимых символов
    """
    clean_filepath = None
    if file_path:
        # Удаляем или заменяем недопустимые символы
        clean_filepath = re.sub(r'[<>:"/\\|?*]', '_', file_path)
        # Заменяем множественные пробелы на одинарные
        clean_filepath = re.sub(r'\s+', ' ', clean_filepath)
        # Убираем лишние точки и пробелы в начале и конце
        clean_filepath = clean_filepath.strip('. ')
    return clean_filepath


def convert_text_hyperlinks(message_text: str) -> Optional[str]:
    # Преобразование текстовых гиперссылок вида [Text](URL) в HTML формат
    if message_text:
        matches = ProjectConst.text_with_url_pattern.findall(message_text)
        if matches:
            for match in matches:
                message_text = message_text.replace(f'[{match[0]}]({match[1]})',
                                                    f'<a href = "{match[1]}" target="_blank" >{match[0]}</a>')
    return message_text


if __name__ == "__main__":
    pass

# def progress_callback(current, total):
#     print(f'{current / total:.2%}')
