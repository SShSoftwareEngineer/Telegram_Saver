import asyncio
import os
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List, Union, Optional, Dict, Any
from telethon import TelegramClient

from config.config import ProjectDirs, Constants, FieldNames

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

    def sort_dialog_list(self, dialog_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Сортировка списка диалогов по заданному полю в заданном порядке
        """
        field = FieldNames.DIALOG_SETTINGS
        return sorted(dialog_list, key=lambda x: x[self.get_filters().get(field['sort_field'])],
                      reverse=self.get_filters().get(field['sort_order']))


@dataclass
class TgMessageSortFilter:
    _sort_order: bool = False
    _date_from: Optional[datetime] = datetime.now() - timedelta(days=Constants.last_days_by_default)
    _date_to: Optional[datetime] = None
    _message_query: Optional[str] = None

    def set_default_filters(self):
        """
        Устанавливает фильтры по умолчанию
        """
        self._sort_order = False
        self._date_from = datetime.now() - timedelta(days=Constants.last_days_by_default)
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
    dialog_list: List[Dict[str, Any]] = None
    selected_dialog_id: int = None
    message_group_list: Dict[str, Dict[str, Any]] = None
    selected_message_group_id: str = None
    message_details: Dict[str, Any] = None


class TelegramHandler:
    dialog_sort_filter: TgDialogSortFilter = TgDialogSortFilter()
    message_sort_filter: TgMessageSortFilter = TgMessageSortFilter()
    current_state: TgCurrentState = TgCurrentState()

    def __init__(self):
        self._connection_settings = dict()
        with open(ProjectDirs.telegram_settings_file, 'r', encoding='utf-8') as file_env:
            for line in file_env:
                if not line.strip().startswith('#') and '=' in line:
                    key, value = line.strip().split('=')
                    self._connection_settings[key] = value
        self.client = TelegramClient(self._connection_settings['SESSION_NAME'],
                                     int(self._connection_settings['API_ID']),
                                     self._connection_settings['API_HASH'], loop=loop)
        self.client.start(self._connection_settings['PHONE'], self._connection_settings['PASSWORD'])

    def get_entity(self, entity_id: int) -> Any:
        """
        Получение сущности по id
        """
        entity = loop.run_until_complete(self.client.get_entity(entity_id))
        return entity

    def get_dialog_list(self) -> List[Dict[str, Any]]:
        """
        Получение списка всех диалогов Telegram с учетом фильтров и сортировки
        """
        print('Chats list loading...')
        dialogs = loop.run_until_complete(self.client.get_dialogs())
        dialog_list = []
        for dialog in dialogs:
            field = FieldNames.DIALOG_INFO
            dialog_info = {
                field['id']: dialog.id,
                field['title']: dialog.title if dialog.title else dialog.name if dialog.name else 'No title',
                field['user']: dialog.entity.username if dialog.entity.username else None,
                field['unread_count']: dialog.unread_count,
                field['last_message_date']: dialog.date.isoformat(' ', 'seconds') if dialog.date else None,
                field['is_user']: dialog.is_user,
                field['is_group']: dialog.is_group,
                field['is_channel']: dialog.is_channel,
            }
            if self.dialog_sort_filter.check_filters(dialog_info):
                dialog_list.append(dialog_info)
        print(f'{len(dialog_list)} chats loaded')
        return self.dialog_sort_filter.sort_dialog_list(dialog_list)

    def get_message_list(self, dialog_id: int) -> Dict[str, Dict[str, Any]]:
        """
        Получение списка сообщений из заданного чата с учетом фильтров, сортировки и группировки
        """
        print(f'Message list for chat id={dialog_id} loading...')
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
                                         field['photo']: False,
                                         field['video']: False,
                                         field['document']: False,
                                         field['selected']: False,}
            else:
                current_date = current_message_group[field['date']]
                current_message_group[field['date']] = min(current_date, message.date.astimezone())
                current_message_group[field['ids']].append(message.id)
                if message.text:
                    current_message_group[field['text']].append(convert_text_hyperlinks(message.text))
            current_message_group[field['photo']] = current_message_group[field['photo']] or message.photo is not None
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
        message_date = current_message_group[cmg_field['date']].strftime(Constants.datetime_format)
        print(f'Message {message_date} details loading...')
        details = {det_field['dialog_id']: current_message_group[cmg_field['dialog_id']],
                   det_field['mess_group_id']: message_group_id,
                   det_field['date']: current_message_group[cmg_field['date']],
                   det_field['text']: '\n\n'.join(current_message_group[cmg_field['text']]),
                   det_field['photo']: [],
                   det_field['video']: [],
                   det_field['video_thumbnail']: [],
                   det_field['audio']: [],
                   det_field['document']: [], }
        # Преобразование текстовых гиперссылок вида [Text](URL) в HTML формат
        details[det_field['text']] = convert_text_hyperlinks(details[det_field['text']])
        # Скачивание медиафайлов
        messages_by_ids = loop.run_until_complete(
            self.client.get_messages(dialog_id, ids=current_message_group[cmg_field['ids']]))
        for message in messages_by_ids:
            if message.file:
                # Получение информации о размере файла
                file_size = float('inf')
                if message.file.size:
                    file_size = message.file.size
                # Получение расширения и имени файла
                if message.photo or message.video:
                    file_ext = '.jpg'
                else:
                    file_ext = getattr(message.file, 'ext', None)
                downloading_result = None
                if not message.video:
                    # Получение файла, если это не видео
                    file_name = clean_file_name(f'{message_date}_{dialog_id}_{message.id}{file_ext}')
                    file = os.path.join(ProjectDirs.cache_media_dir, file_name)
                    if os.path.exists(file):
                        downloading_result = file
                    else:
                        if file_size <= Constants.max_download_file_size:
                            downloading_result = loop.run_until_complete(self.client.download_media(message, file=file))
                else:
                    # Получение thumbnail видео
                    file_name = clean_file_name(f'{message_date}_{dialog_id}_{message.id}_thumb.jpg')
                    file = os.path.join(ProjectDirs.cache_media_dir, file_name)
                    if os.path.exists(file):
                        downloading_result = file
                    else:
                        if message.video.thumbs:
                            downloading_result = loop.run_until_complete(
                                self.client.download_media(message, file=file, thumb=-1))
                if downloading_result:
                    downloading_result = os.path.basename(downloading_result)
                    if message.photo:
                        details[det_field['photo']].append(downloading_result)
                    if message.video:
                        details[det_field['video_thumbnail']].append(downloading_result)
                    if message.audio:
                        details[det_field['audio']].append(downloading_result)
                    if message.document and not message.video:
                        details[det_field['document']].append(downloading_result)
        print('Message details loaded')
        return details


def convert_text_hyperlinks(message_text: str) -> Optional[str]:
    # Преобразование текстовых гиперссылок вида [Text](URL) в HTML формат
    if message_text:
        matches = Constants.text_with_url_pattern.findall(message_text)
        if matches:
            for match in matches:
                message_text = message_text.replace(f'[{match[0]}]({match[1]})',
                                                    f'<a href = "{match[1]}" target="_blank" >{match[0]}</a>')
    return message_text


def clean_file_name(file_name: str | None) -> str | None:
    """
    Очищает имя файла/директории от недопустимых символов
    """
    clean_filename = None
    if file_name:
        # Удаляем или заменяем недопустимые символы
        clean_filename = re.sub(r'[<>:"/\\|?*]', '_', file_name)
        # Заменяем множественные пробелы
        clean_filename = re.sub(r'\s+', '_', clean_filename)
        # Убираем лишние точки и пробелы в начале и конце
        clean_filename = clean_filename.strip('. ')
    return clean_filename


if __name__ == "__main__":
    pass

# def progress_callback(current, total):
#     print(f'{current / total:.2%}')
