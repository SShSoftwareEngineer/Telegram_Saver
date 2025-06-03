import asyncio
import mimetypes
import os
import re

from telethon.tl.types import MessageMediaPhoto, MessageMediaDocument

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Union, Optional, Dict, Any
from telethon import TelegramClient

from config.config import ProjectDirs, ProjectConst, FieldNames, MessageFileTypes

# Создаем и сохраняем цикл событий
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)




@dataclass
class TgDialogSortFilter:
    _sort_field: str = 'title'
    _sort_order: bool = False
    _dialog_type: Optional[str] = None
    _title_query: Optional[str] = None

    def sort_field(self, value: str):
        """
        Устанавливает поле сортировки
        """
        self._sort_field = FieldNames.DIALOG_INFO['title'] if value == '0' else (
            FieldNames.DIALOG_INFO)['last_message_date']

    def sort_order(self, value: str):
        """
        Устанавливает направление сортировки
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
                self._dialog_type = 'is_channel'
            case '2':
                self._dialog_type = 'is_group'
            case '3':
                self._dialog_type = 'is_user'

    def title_query(self, value: str):
        """
        Устанавливает фильтр по названию диалогов
        """
        self._title_query = value if value else None

    def get_filters(self) -> Dict[str, Union[str, bool]]:
        """
        Возвращает текущие фильтры
        """
        field = FieldNames.DIALOG_SETTINGS
        return {
            field['sort_field']: self._sort_field,
            field['sort_order']: self._sort_order,
            field['dialog_type']: self._dialog_type,
            field['title_query']: self._title_query
        }

    def check_filters(self, dialog_info: dict) -> bool:
        """
        Проверка фильтров по названию и по типу для конкретного диалога
        """
        field = FieldNames.DIALOG_SETTINGS
        title_query = True
        if self.get_filters().get(field['title_query']):
            title_query = (self.get_filters().get(field['title_query']).lower() in
                           str(dialog_info[FieldNames.DIALOG_INFO['title']]).lower())
        dialog_type = True
        if self.get_filters().get(field['dialog_type']):
            dialog_type = dialog_info[self.get_filters().get(field['dialog_type'])]
        return all([title_query, dialog_type])

    def sort_dialog_list(self, dialog_list: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        """
        Сортировка списка диалогов по заданному полю в заданном порядке
        """
        field = FieldNames.DIALOG_SETTINGS
        return dict(sorted(dialog_list.items(), key=lambda x: x[1].get(self.get_filters().get(field['sort_field'])),
                           reverse=self.get_filters().get(field['sort_order'])))


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


@dataclass
class TgCurrentState:
    dialog_list: Dict[str, Dict[str, Any]] = None
    selected_dialog_id: int = None
    message_group_list: Dict[str, Dict[str, Any]] = None
    selected_message_group_id: str = None
    message_details: Dict[str, Any] = None
    message_files: Dict[str, Dict[str, Any]] = None


class TelegramHandler:
    all_dialogues_list: Dict[str, Dict[str, Any]] = None
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

    def get_entity(self, entity_id: int) -> Any:
        """
        Получение сущности по id
        """
        entity = loop.run_until_complete(self.client.get_entity(entity_id))
        return entity

    def get_dialog_list(self) -> Dict[str, Dict[str, Any]]:
        """
        Получение списка всех диалогов Telegram с учетом фильтров и сортировки
        """
        print('Chats list loading...')
        dialogs = loop.run_until_complete(self.client.get_dialogs())
        dialog_list = dict()
        field = FieldNames.DIALOG_INFO
        for dialog in dialogs:
            current_dialog_id = dialog.id
            dialog_info = {
                field['title']: dialog.title if dialog.title else dialog.name if dialog.name else 'No title',
                field['user']: dialog.entity.username if dialog.entity.username else None,
                field['unread_count']: dialog.unread_count,
                field['last_message_date']: dialog.date.isoformat(' ', 'seconds') if dialog.date else None,
                field['is_user']: dialog.is_user,
                field['is_group']: dialog.is_group,
                field['is_channel']: dialog.is_channel,
            }
            if self.dialog_sort_filter.check_filters(dialog_info):
                dialog_list[current_dialog_id] = dialog_info
        print(f'{len(dialog_list)} chats loaded')
        return self.dialog_sort_filter.sort_dialog_list(dialog_list)

    def get_message_list(self, dialog_id: int) -> Dict[str, Dict[str, Any]]:
        """
        Получение списка сообщений из заданного чата с учетом фильтров, сортировки и группировки
        """
        # Получаем сущность диалога по id
        dialog = self.get_entity(dialog_id)
        print(f'Message list for "{dialog.title}" loading...')
        # Получаем текущие данные фильтра сообщений
        message_filters = self.message_sort_filter.get_filters()
        message_filters['entity'] = dialog
        # Устанавливаем параметры фильтрации по дате через id сообщений
        field = FieldNames.MESSAGE_SETTINGS
        if message_filters.get(field['date_from']):
            message_from = loop.run_until_complete(
                self.client.get_messages(entity=dialog, offset_date=message_filters.get(field['date_from']), limit=1))
            if message_from:
                message_filters['min_id'] = message_from[0].id
        message_filters.pop(field['date_from'])
        if message_filters.get(field['date_to']):
            message_to = loop.run_until_complete(
                self.client.get_messages(entity=dialog, offset_date=message_filters.get(field['date_to']), limit=1,
                                         reverse=True))
            if message_to:
                message_filters['max_id'] = message_to[0].id
        message_filters.pop(field['date_to'])
        # Установка параметра сортировки по дате
        message_filters['reverse'] = message_filters.get(field['sort_order'])
        # Удаление и восстановление фильтра поиска по тексту сообщения и порядка сортировки
        search_filter = message_filters.get(field['message_query'])
        message_filters.pop(field['sort_order'])
        message_filters.pop(field['message_query'])
        # Выборка сообщений по фильтрам
        messages = loop.run_until_complete(self.client.get_messages(**message_filters))
        # Восстановление удаленных фильтров
        message_filters[field['message_query']] = search_filter
        message_filters[field['sort_order']] = message_filters.get('reverse')
        # Создание списка сообщений с учетом группировки и фильтра по тексту
        message_group_list = dict()
        current_message_group = None
        current_group_id = None
        field = FieldNames.MESSAGE_GROUP_INFO
        for message in messages:
            # Применение фильтра по тексту сообщения
            if message_filters.get(FieldNames.MESSAGE_SETTINGS['message_query']):
                if not message_filters.get(
                        FieldNames.MESSAGE_SETTINGS['message_query']).lower() in message.text.lower():
                    continue
            # Составление списка сообщений с учетом группировки по message.grouped_id
            message_group_id = str(message.grouped_id) if message.grouped_id else f'None_{message.id}'
            if message_group_id != current_group_id:
                current_group_id = message_group_id
                current_message_group = dict()
            if current_group_id not in message_group_list:
                current_message_group = {field['dialog_id']: dialog_id,
                                         field['sender_id']: message.sender_id,
                                         field['date']: message.date.astimezone(),
                                         field['ids']: [message.id],
                                         field['text']: [convert_text_hyperlinks(message.text)] if message.text else [],
                                         field['files']: [self.get_message_file_info(message)] if message.file else [],
                                         field['image']: False,
                                         field['video']: False,
                                         field['document']: False,
                                         field['selected']: False, }
            else:
                current_date = current_message_group[field['date']]
                current_message_group[field['date']] = min(current_date, message.date.astimezone())
                current_message_group[field['ids']].append(message.id)
                if message.file:
                    current_message_group[field['files']].append(self.get_message_file_info(message))
                if message.text:
                    current_message_group[field['text']].append(convert_text_hyperlinks(message.text))
            current_message_group[field['image']] = current_message_group[field['image']] or message.photo is not None
            current_message_group[field['video']] = current_message_group[field['video']] or message.video is not None
            current_message_group[field['document']] = current_message_group[field['document']] or (
                    message.document is not None and message.video is None)
            message_group_list[current_group_id] = current_message_group
        print(f'{len(message_group_list)} messages loaded')
        self.current_state.message_group_list = message_group_list
        return message_group_list

    def get_message_detail(self, dialog_id: int, message_group_id: str) -> Dict[str, Any]:
        """
        Получение сообщения по id диалога и id группы сообщений
        """
        # Получаем текущую группу сообщений по id
        current_message_group = self.current_state.message_group_list.get(message_group_id)
        cmg_field = FieldNames.MESSAGE_GROUP_INFO
        det_field = FieldNames.DETAILS_INFO
        fil_field = FieldNames.MESSAGE_FILE_INFO
        message_date = current_message_group[cmg_field['date']].strftime(ProjectConst.message_datetime_format)
        print(f'Message {message_date} details loading...')
        details = {det_field['dialog_id']: current_message_group[cmg_field['dialog_id']],
                   det_field['mess_group_id']: message_group_id,
                   det_field['date']: current_message_group[cmg_field['date']],
                   det_field['text']: '\n\n'.join(current_message_group[cmg_field['text']]),
                   det_field['image']: [],
                   det_field['video']: [],
                   det_field['video_thumbnail']: [],
                   det_field['audio']: [],
                   det_field['document']: [], }
        # Преобразование текстовых гиперссылок вида [Text](URL) в HTML формат
        details[det_field['text']] = convert_text_hyperlinks(details[det_field['text']])

        # # Скачивание медиафайлов
        # messages_by_ids = loop.run_until_complete(
        #     self.client.get_messages(dialog_id, ids=current_message_group[cmg_field['ids']]))
        # for message in messages_by_ids:
        #     if message.media:
        #         # Определение типа файла, его расширения и размера
        #         message_file = {
        #             fil_field['dialog_id']: dialog_id,
        #             fil_field['message_id']: message.id,
        #             fil_field['path']: ProjectDirs.media_cache_dir,
        #             fil_field['name']: None,
        #             fil_field['ext']: None,
        #             fil_field['size']: None,
        #             fil_field['type']: None,
        #         }
        #         # file_size = float('inf')
        #         # file_type = det_field['document']
        #         # file_ext = ''
        #         if isinstance(message.media, MessageMediaPhoto):
        #             message_file[fil_field['type']] = det_field['image']
        #             message_file[fil_field['size']] = message.media.photo.sizes[
        #                 -1].size if message.media.photo.sizes else 0
        #             message_file[fil_field['ext']] = '.jpg'
        #             # file_type = det_field['image']
        #             # file_size = message.media.photo.sizes[-1].size if message.media.photo.sizes else 0
        #             # file_ext = '.jpg'
        #         elif isinstance(message.media, MessageMediaDocument):
        #             doc = message.media.document
        #             message_file[fil_field['size']] = doc.size
        #             file_ext = mimetypes.guess_extension(doc.mime_type)
        #             message_file[fil_field['ext']] = file_ext if file_ext else ''
        #             if doc.mime_type.startswith('image/'):
        #                 message_file[fil_field['type']] = det_field['image']
        #             elif doc.mime_type.startswith('video/'):
        #                 message_file[fil_field['type']] = det_field['video']
        #             elif doc.mime_type.startswith('audio/'):
        #                 message_file[fil_field['type']] = det_field['audio']
        #             else:
        #                 message_file[fil_field['type']] = det_field['document']
        #         # Загрузка файла в кэш, если его там нет
        #         downloading_result = None
        #         if message_file[fil_field['type']] != det_field['video']:
        #             # Получение файла, если это не видео
        #             file_name = cache_file_name(message.date, dialog_id, message_group_id, file_type, file_ext)
        #             if os.path.exists(file_name):
        #                 downloading_result = file_name
        #             else:
        #                 if file_size <= Constants.max_download_file_size:
        #                     downloading_result = loop.run_until_complete(
        #                         self.client.download_media(message, file=file_name))
        #         else:
        #             # Получение thumbnail видео
        #             file_name = cache_file_name(message.date, dialog_id, message_group_id, file_type, file_ext)
        #             if os.path.exists(file_name):
        #                 downloading_result = file_name
        #             else:
        #                 if message.video.thumbs:
        #                     downloading_result = loop.run_until_complete(
        #                         self.client.download_media(message, file=file_name, thumb=-1))

        # if message.file.size:
        #     file_size = message.file.size
        # # Получение расширения и имени файла
        # if message.photo or message.video:
        #     file_ext = '.jpg'
        # else:
        #     file_ext = getattr(message.file, 'ext', None)
        # downloading_result = None
        # if not message.video:
        #     # Получение файла, если это не видео
        #     file_name = clean_file_name(f'{message_date}_{dialog_id}_{message.id}{file_ext}')
        #     file = os.path.join(ProjectDirs.media_cache_dir, file_name)
        #     if os.path.exists(file):
        #         downloading_result = file
        #     else:
        #         if file_size <= Constants.max_download_file_size:
        #             downloading_result = loop.run_until_complete(self.client.download_media(message, file=file))
        # else:
        #     # Получение thumbnail видео
        #     file_name = clean_file_name(f'{message_date}_{dialog_id}_{message.id}_thumb.jpg')
        #     file = os.path.join(ProjectDirs.media_cache_dir, file_name)
        #     if os.path.exists(file):
        #         downloading_result = file
        #     else:
        #         if message.video.thumbs:
        #             downloading_result = loop.run_until_complete(
        #                 self.client.download_media(message, file=file, thumb=-1))

        # if downloading_result:
        #     downloading_result = os.path.basename(downloading_result)
        #     if message.photo:
        #         details[det_field['image']].append(downloading_result)
        #     if message.video:
        #         details[det_field['video_thumbnail']].append(downloading_result)
        #     if message.audio:
        #         details[det_field['audio']].append(downloading_result)
        #     if message.document and not message.video:
        #         details[det_field['document']].append(downloading_result)

        print('Message details loaded')
        return details

    def get_message_file_info(self, message, thumbnail: bool = True) -> Optional[Dict]:
        """
        Получение информации о файле сообщения
        """
        field = FieldNames.MESSAGE_FILE_INFO
        file_type = MessageFileTypes.UNKNOWN
        file_ext = None
        result=None
        if message.file:
            # Определение типа файла, его расширения и размера
            message_file_info = {
                field['dialog_id']: message.dialog.id,
                field['message_id']: message.id,
                field['full_path']: None,
                field['size']: None,
                field['type']: None,
            }
            if isinstance(message.media, MessageMediaPhoto):
                file_type = MessageFileTypes.PHOTO
                message_file_info[field['size']] = message.media.photo.sizes[
                    -1].size if message.media.photo.sizes else 0
            elif isinstance(message.media, MessageMediaDocument):
                mess_doc = message.media.document
                message_file_info[field['size']] = mess_doc.size
                file_ext = getattr(message.file, 'ext', None)
                file_ext = mimetypes.guess_extension(mess_doc.mime_type) if file_ext is None else None
                if mess_doc.mime_type.startswith('image/'):
                    file_type = MessageFileTypes.IMAGE
                elif mess_doc.mime_type.startswith('video/'):
                    if thumbnail:
                        file_type = MessageFileTypes.VIDEO_THUMBNAIL
                    else:
                        file_type = MessageFileTypes.VIDEO
                elif mess_doc.mime_type.startswith('audio/'):
                    file_type = MessageFileTypes.AUDIO
                else:
                    file_type = MessageFileTypes.DOCUMENT
            message_file_info[field['type']] = file_type.type
            if file_ext is None:
                message_file_info[field['ext']] = file_type.ext
            message_file_info[field['full_path']] = clean_file_path(
                str(os.path.join(ProjectDirs.media_dir,
                             f'{self.all_dialogues_list[message.dialog.id][FieldNames.DIALOG_INFO['title']]}_{message.dialog.id}',
                             message.date.strftime('%Y-%m-%d'),
                             message.date.strftime('%H_%M_%S'),
                             f'{message.id}_{file_type.sign}{file_ext}')))
            result= message_file_info
        return result


            # # Загрузка файла в базу данных или кэш, если его там нет
            # downloading_result = None
            # if save_to_database:
            #     file_name = ''
            # else:
            #     file_name = os.path.join(ProjectDirs.media_cache_dir,
            #                              cache_file_name(message.date, dialog_id, message.id,
            #                                              message_file[fil_field['type']],
            #                                              message_file[fil_field['ext']]))
            # if message_file[fil_field['type']] != det_field['video']:
            #     # Получение файла, если это не видео
            #     if os.path.exists(file_name):
            #         downloading_result = file_name
            #     else:
            #         if message_file[fil_field['size']] <= ProjectConst.max_download_file_size:
            #             downloading_result = loop.run_until_complete(
            #                 self.client.download_media(message, file=file_name))
            # else:
            #     # Получение thumbnail видео
            #     file_name = cache_file_name(message.date, dialog_id, message_group_id, file_type, file_ext)
            #     if os.path.exists(file_name):
            #         downloading_result = file_name
            #     else:
            #         if message.video.thumbs:
            #             downloading_result = loop.run_until_complete(
            #                 self.client.download_media(message, file=file_name, thumb=-1))
            #
            # if downloading_result:
            #     downloading_result = os.path.basename(downloading_result)
            #     if message.photo:
            #         details[det_field['image']].append(downloading_result)
            #     if message.video:
            #         details[det_field['video_thumbnail']].append(downloading_result)
            #     if message.audio:
            #         details[det_field['audio']].append(downloading_result)
            #     if message.document and not message.video:
            #         details[det_field['document']].append(downloading_result)


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
