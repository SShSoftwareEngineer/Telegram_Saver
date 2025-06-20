import asyncio
import re
import mimetypes
import sys

from telethon.tl.custom import Dialog, Message
from telethon.tl.types import MessageMediaPhoto, MessageMediaDocument, PhotoSize, PhotoCachedSize, PhotoStrippedSize, \
    PhotoSizeProgressive  # , Message

from pathlib import Path
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Union, Optional, Dict, Any, List
from telethon import TelegramClient

from configs.config import ProjectDirs, ProjectConst, FieldNames, MessageFileTypes, DialogTypes

# Создаем и сохраняем цикл событий
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)


@dataclass
class TgDialog:
    """
    A class to represent a Telegram dialog in this program.
    """
    dialog_id: int
    title: str
    name: str
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
        if dialog.name:
            self.name = dialog.name
        elif dialog.entity.username:
            self.name = dialog.entity.username
        else:
            self.name = 'No name'
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
        return sorted(dialog_list, key=self._sorting_field, reverse=self._sort_order)


@dataclass
class TgMessageGroup:
    """
    A class to represent a Telegram message group in this program.
    """
    grouped_id: str
    dialog_id: int
    ids: List[int]
    date: datetime = None
    from_id: Optional[int] = None
    reply_to: Optional[int] = None
    text: Optional[str] = None
    files: Optional[Dict[str, Any]] = None
    files_report: Optional[str] = None
    selected: bool = False

    def __init__(self, grouped_id: str = None, dialog_id: int = None):
        self.grouped_id = grouped_id
        self.dialog_id = dialog_id
        self.ids = []

    def add_message(self, message: Message):
        """
        Добавляет сообщение в группу сообщений
        """
        self.from_id = message.from_id if self.from_id is None else self.from_id
        self.reply_to = message.reply_to if self.reply_to is None else self.reply_to
        self.date = message.date.astimezone() if self.date is None else min(self.date, message.date.astimezone())
        self.ids.append(message.id)
        if message.text:
            self.text = message.text if self.text is None else '\n\n'.join([self.text, message.text])
        self.text = convert_text_hyperlinks(self.text) if self.text is not None else None
        # self.files = files if files else {}
        # self.files_report = files_report
        #                      field['files']: [
        #                          self.get_message_file_info(dialog_id, message)] if message.file else [],
        #                      field['files_report']: None,


# if message.file:
#     current_message_group[field['files']].append(self.get_message_file_info(dialog_id, message))

# # Формирование строки отчета по имеющимся файлам и их типам в группе сообщений
# files_report = set(
#     [file.get(FieldNames.MESSAGE_FILE_INFO['type']) for file in current_message_group[field['files']]])
# current_message_group[field['files_report']] = ' '.join(sorted(files_report))
# # Если есть видео, то заменяем в отчете тип файла thumbnail на video
# current_message_group[field['files_report']].replace(MessageFileTypes.THUMBNAIL.web_name,
#                                                      MessageFileTypes.VIDEO.web_name)


@dataclass
class TgMessageSortFilter:
    _sort_order: bool = False
    _date_from: Optional[datetime] = datetime.now() - timedelta(days=ProjectConst.last_days_by_default)
    _date_to: Optional[datetime] = None
    _message_query: Optional[str] = None

    def set_default_filters(self):
        """
        Устанавливает фильтры по умолчанию
        """
        self._sort_order = False
        self._date_from = datetime.now() - timedelta(days=ProjectConst.last_days_by_default)
        self._date_to = None
        self._message_query = None

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

    def sort_order(self, value: str):
        """
        Устанавливает порядок сортировки сообщений по дате
        """
        self._sort_order = True if value == '0' else False

    def date_from(self, value: str):
        """
        Устанавливает дату, с которой получать сообщения
        """
        self._date_from = self.set_date(value)

    def date_to(self, value: str):
        """
        Устанавливает дату, до которой получать сообщения
        """
        self._date_to = self.set_date(value)

    def message_query(self, value: str):
        """
        Устанавливает фильтр по названию диалогов
        """
        self._message_query = value if value else None

    def get_filters(self) -> Dict[str, Union[str, int]]:
        """
        Возвращает текущие фильтры
        """
        field = FieldNames.MESSAGE_SETTINGS
        return {
            field['sort_order']: self._sort_order,
            field['date_from']: self._date_from,
            field['date_to']: self._date_to,
            field['message_query']: self._message_query,
        }

    def sort_message_group_list(self, message_group_list: List[TgMessageGroup]) -> List[TgMessageGroup]:
        """
        Сортировка списка групп сообщений по дате
        """
        return sorted(message_group_list, key=lambda x: x.date, reverse=self._sort_order)


@dataclass
class TgCurrentState:
    dialog_list: List[TgDialog] = None
    selected_dialog_id: int = None
    message_group_list: Dict[str, Dict[str, Any]] = None
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
        Получение сущности по id
        """
        entity = loop.run_until_complete(self.client.get_entity(entity_id))
        return entity

    def get_tg_dialog_by_id(self, dialog_id: int) -> Optional[TgDialog]:
        """
        Получение диалога по id
        """
        found_tg_dialog = next((x for x in self.all_dialogues_list if x.dialog_id == dialog_id), None)
        return found_tg_dialog

    @staticmethod
    def get_tg_message_group_by_id(message_group_list: list, grouped_id: str) -> Optional[TgMessageGroup]:
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

    def get_message_group_list(self, dialog_id: int) -> List[TgMessageGroup]:
        """
        Получение списка групп сообщений из заданного чата с учетом фильтров, сортировки и группировки
        """
        current_tg_dialog = self.get_tg_dialog_by_id(dialog_id)
        if current_tg_dialog:
            print(f'Loading messages for "{current_tg_dialog.title}" dialog...')
        # Получаем сущность диалога по id
        dialog = self.get_entity(dialog_id)
        # Получаем текущие данные фильтра сообщений
        message_filters = self.message_sort_filter.get_filters()
        message_filters['entity'] = dialog
        # Устанавливаем параметры фильтрации по дате через id сообщений
        field = FieldNames.MESSAGE_SETTINGS
        if message_filters.get(field['date_from']):
            message_from = loop.run_until_complete(
                self.client.get_messages(entity=dialog, offset_date=message_filters.get(field['date_from']), limit=1))
            message_filters['min_id'] = message_from[0].id if message_from else 0
        message_filters.pop(field['date_from'])
        if message_filters.get(field['date_to']):
            message_to = loop.run_until_complete(
                self.client.get_messages(entity=dialog, offset_date=message_filters.get(field['date_to']), limit=1,
                                         reverse=True))
            message_filters['max_id'] = message_to[0].id if message_to else sys.maxsize
        message_filters.pop(field['date_to'])
        # Установка параметра порядка сортировки по дате
        message_filters['reverse'] = message_filters.get(field['sort_order'])
        # Удаление и восстановление фильтра поиска по тексту сообщения и порядка сортировки
        search_filter = message_filters.pop(field['message_query'])
        message_filters.pop(field['sort_order'])
        # Получение сообщений в соответствии с фильтрами
        messages = loop.run_until_complete(self.client.get_messages(**message_filters))
        # Восстановление удаленных фильтров
        message_filters[field['message_query']] = search_filter
        message_filters[field['sort_order']] = message_filters.get('reverse')
        # Создание списка групп сообщений с учетом параметра группировки и фильтра по тексту
        message_group_list = []
        # Составление списка сообщений с учетом группировки по message.grouped_id
        for message in messages:
            # Если message.grouped_id сообщения не установлен, то используем строку "Message_{message.id}"
            message_grouped_id = str(message.grouped_id) if message.grouped_id else f'Message_{message.id}'
            # Проверяем существование группы сообщений с текущим grouped_id
            tg_message_group = self.get_tg_message_group_by_id(message_group_list, message_grouped_id)
            # Если группа сообщений с текущим grouped_id не существует, создаем ее и добавляем в список групп сообщений
            if tg_message_group is None:
                tg_message_group = TgMessageGroup(message_grouped_id, dialog_id)
                message_group_list.append(tg_message_group)
            # Добавляем текущее сообщение в группу сообщений
            tg_message_group.add_message(message)
        # Применение фильтра по тексту группы сообщений, если он задан
        if message_filters.get(FieldNames.MESSAGE_SETTINGS['message_query']):
            for message_group in message_group_list.copy():
                if not message_filters.get(FieldNames.MESSAGE_SETTINGS['message_query']).lower() in \
                       message_group.text.lower():
                    message_group_list.remove(message_group)
        print(f'{len(message_group_list)} messages loaded')
        return self.message_sort_filter.sort_message_group_list(message_group_list)

    def get_message_detail(self, message_group_id: str) -> Dict[str, Any]:
        """
        Получение сообщения по id диалога и id группы сообщений
        """
        # Получаем текущую группу сообщений по id
        current_message_group = self.current_state.message_group_list.get(message_group_id)
        cmg_field = FieldNames.MESSAGE_GROUP_INFO
        det_field = FieldNames.DETAILS_INFO
        fil_field = FieldNames.MESSAGE_FILE_INFO
        message_date_str = current_message_group[cmg_field['date']].strftime(ProjectConst.message_datetime_format)
        print(f'Message {message_date_str} details loading...')
        details = {det_field['dialog_id']: current_message_group[cmg_field['dialog_id']],
                   det_field['mess_group_id']: message_group_id,
                   det_field['date']: message_date_str,
                   det_field['text']: '\n\n'.join(current_message_group[cmg_field['text']]),
                   det_field['files']: sorted(current_message_group[cmg_field['files']],
                                              key=lambda x: x[fil_field['type']]),
                   det_field['files_report']: current_message_group[cmg_field['files_report']],
                   }
        # Преобразование текстовых гиперссылок вида [Text](URL) в HTML формат
        details[det_field['text']] = convert_text_hyperlinks(details[det_field['text']])
        # Скачиваем файлы, содержащиеся в детальном сообщении, если их нет
        for message_file_info in details[det_field['files']]:
            self.download_message_file(message_file_info)
        print('Message details loaded')
        return details

    def get_message_file_info(self, dialog_id: int, message, thumbnail: bool = True) -> Optional[Dict]:
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
        field = FieldNames.MESSAGE_FILE_INFO
        message_file_info = {
            field['dialog_id']: dialog_id,
            field['message']: message,
            field['full_path']: None,
            field['size']: None,
            field['type']: None,
        }
        mess_doc = None
        # Определение типа файла
        file_type = MessageFileTypes.UNKNOWN
        if isinstance(message.media, MessageMediaPhoto):
            file_type = MessageFileTypes.PHOTO
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
        message_file_info[field['type']] = file_type.web_name
        # Определение размера файла
        if isinstance(message.media, MessageMediaPhoto):
            message_file_info[field['size']] = get_image_size(message.media.photo.sizes)
        elif isinstance(message.media, MessageMediaDocument):
            mess_doc = message.media.document
            if all([thumbnail, hasattr(mess_doc, 'thumbs'), mess_doc.thumbs]):
                message_file_info[field['size']] = get_image_size(mess_doc.thumbs)
            else:
                message_file_info[field['size']] = mess_doc.size
        # Определение расширения файла
        if file_type == MessageFileTypes.UNKNOWN:
            file_ext = getattr(message.file, 'ext', None)
            if file_ext is None:
                file_ext = mimetypes.guess_extension(mess_doc.mime_type)
            if file_ext is None:
                file_ext = ''
        else:
            file_ext = file_type.default_ext
        # Формирование пути к файлу
        dialog_dir = f'{self.get_tg_dialog_by_id(dialog_id).title}_{dialog_id}'
        file_name = f'{message.date.astimezone().strftime('%H-%M-%S')}_{message.id}_{file_type.sign}{file_ext}'
        message_file_info[field['full_path']] = Path(ProjectDirs.media_dir) / clean_file_path(
            dialog_dir) / message.date.astimezone().strftime('%Y-%m-%d') / file_name
        message_file_info[field['web_path']] = message_file_info[field['full_path']].as_posix()
        return message_file_info


def download_message_file(self, message_file_info: dict) -> Optional[str]:
    """
    Загрузка файла сообщения
    """
    downloading_param = dict()
    field = FieldNames.MESSAGE_FILE_INFO
    # Проверка существования файла и его размера
    if all([not Path(message_file_info[field['full_path']]).exists,
            # if all([not os.path.exists(message_file_info[field['full_path']]),
            0 < message_file_info[field['size']] <= ProjectConst.max_download_file_size]):
        # Если файл не существует, то создаем соответствующие директории и загружаем файл
        Path(message_file_info[field['full_path']]).parent.mkdir(parents=True, exist_ok=True)
        # os.makedirs(os.path.dirname(message_file_info[field['full_path']]),
        #             exist_ok=True)
        downloading_param['message'] = message_file_info[field['message']]
        downloading_param['file'] = message_file_info[field['full_path']]
        if message_file_info[field['type']] == MessageFileTypes.THUMBNAIL.web_name:
            downloading_param['thumb'] = -1
        result = loop.run_until_complete(self.client.download_media(**downloading_param))
    else:
        # Если файл уже существует, то возвращаем его имя
        result = message_file_info[field['full_path']]
    return result


def clean_file_path(file_path: str | None) -> str | None:
    """
    Очищает имя файла/директории от недопустимых символов
    """
    clean_filepath = None
    if file_path:
        # Удаляем или заменяем недопустимые символы
        clean_filepath = re.sub(r'[<>:"/\\|?*]', '_', file_path)
        # Заменяем множественные пробелы
        clean_filepath = re.sub(r'\s+', '_', clean_filepath)
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
