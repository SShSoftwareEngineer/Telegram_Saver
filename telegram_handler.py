import asyncio
import os
from dataclasses import dataclass
from datetime import datetime

from telethon import TelegramClient
import re
from typing import List, Union, Optional, Dict, Any

CHATS_MEDIA = r'chats_media'
DB_MEDIA_DIR = fr'{CHATS_MEDIA}\database'
CACHE_MEDIA_DIR = fr'{CHATS_MEDIA}\cache'
TELEGRAM_SETTINGS_FILE = '.env'
MAX_FILE_SIZE = 10 * 1024 * 1024
MESSAGE_LIMIT = 20

# Создаем и сохраняем цикл событий
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)


@dataclass
class TgDialogSortFilter:
    _sort_field: str = 'title'
    _reverse: bool = False
    _type_filter: Optional[str] = None
    _title_filter: Optional[str] = None

    def sort_field(self, value: str):
        """
        Устанавливает поле сортировки
        """
        self._sort_field = 'title' if value == '0' else 'last_message_date'

    def reverse(self, value: str):
        """
        Устанавливает направление сортировки
        """
        self._reverse = False if value == '0' else True

    def type_filter(self, value: str):
        """
        Устанавливает фильтр по типу диалогов
        """
        match value:
            case '0':
                self._type_filter = None
            case '1':
                self._type_filter = 'is_channel'
            case '2':
                self._type_filter = 'is_group'
            case '3':
                self._type_filter = 'is_user'

    def title_filter(self, value: str):
        """
        Устанавливает фильтр по названию диалогов
        """
        self._title_filter = value if value else None

    def get_filters(self) -> Dict[str, Union[str, bool]]:
        """
        Возвращает текущие фильтры
        """
        return {
            'sort_field': self._sort_field,
            'reverse': self._reverse,
            'type_filter': self._type_filter,
            'title_filter': self._title_filter
        }

    def check_filters(self, dialog_info: dict) -> bool:
        """
        Проверка фильтров по названию и по типу для конкретного диалога
        """
        title_filter = True
        if self.get_filters().get('title_filter'):
            title_filter = self.get_filters().get('title_filter').lower() in str(dialog_info['title']).lower()
        type_filter = True
        if self.get_filters().get('type_filter'):
            type_filter = dialog_info[self.get_filters().get('type_filter')]
        return all([title_filter, type_filter])

    def sort_dialog_list(self, dialog_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Сортировка списка диалогов по заданному полю в заданном порядке
        """
        return sorted(dialog_list, key=lambda x: x[self.get_filters().get('sort_field')],
                      reverse=self.get_filters().get('reverse'))


@dataclass
class TgMessageSortFilter:
    _reverse: bool = False
    _date_from: Optional[datetime] = None
    _date_to: Optional[datetime] = None
    _search: Optional[str] = None
    _limit: int = MESSAGE_LIMIT

    def set_default_filters(self):
        """
        Устанавливает фильтры по умолчанию
        """
        self._reverse = False
        self._date_from = None
        self._date_to = None
        self._search = None
        self._limit = MESSAGE_LIMIT

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

    def reverse(self, value: str):
        """
        Устанавливает порядок сортировки сообщений по дате
        """
        self._reverse = False if value == '0' else True

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

    def search(self, value: str):
        """
        Устанавливает фильтр по названию диалогов
        """
        self._search = value if value else None

    def limit(self, value: str):
        """
        Устанавливает максимальное количество последних сообщений для фильтрации
        """
        try:
            self._limit = int(value)
        except ValueError:
            self._limit = MESSAGE_LIMIT

    def get_filters(self) -> Dict[str, Union[str, int]]:
        """
        Возвращает текущие фильтры
        """
        return {
            'reverse': self._reverse,
            'date_from': self._date_from,
            'date_to': self._date_to,
            'search': self._search,
            'limit': self._limit
        }


class TelegramHandler:
    dialog_sort_filter: TgDialogSortFilter
    message_sort_filter: TgMessageSortFilter
    current_dialog_id: int
    url_pattern = re.compile(r"\[(.*?)\]\((.*?)\)")

    def __init__(self):
        self.dialog_sort_filter = TgDialogSortFilter()
        self.message_sort_filter = TgMessageSortFilter()
        self._connection_settings = {}
        with open(TELEGRAM_SETTINGS_FILE, 'r', encoding='utf-8') as file_env:
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
        dialogs = loop.run_until_complete(self.client.get_dialogs())
        dialog_list = []
        for dialog in dialogs:
            dialog_info = {
                'id': dialog.id,
                'title': dialog.title if dialog.title else dialog.name if dialog.name else 'No title',
                'username': dialog.entity.username if dialog.entity.username else None,
                'unread_count': dialog.unread_count,
                'last_message_date': dialog.date.isoformat(' ', 'seconds') if dialog.date else None,
                'is_user': dialog.is_user,
                'is_group': dialog.is_group,
                'is_channel': dialog.is_channel,
            }
            if self.dialog_sort_filter.check_filters(dialog_info):
                dialog_list.append(dialog_info)
        return self.dialog_sort_filter.sort_dialog_list(dialog_list)

    def get_message_list(self, dialog_id: int) -> List[Dict[str, Any]]:
        """
        Получение списка сообщений из заданного чата с учетом фильтров и сортировки
        """
        # Получаем сущность диалога по id
        dialog = self.get_entity(dialog_id)
        # Получаем текущие данные фильтра сообщений
        message_filters = self.message_sort_filter.get_filters()
        message_filters['entity'] = dialog
        # Устанавливаем параметры фильтрации по дате через id сообщения
        if message_filters.get('date_from'):
            message_from = loop.run_until_complete(
                self.client.get_messages(entity=dialog, offset_date=message_filters.get('date_from'), limit=1))
            if message_from:
                message_filters['min_id'] = message_from[0].id
        message_filters.pop('date_from')
        if message_filters.get('date_to'):
            message_to = loop.run_until_complete(
                self.client.get_messages(entity=dialog, offset_date=message_filters.get('date_to'), limit=1,
                                         reverse=True))
            if message_to:
                message_filters['max_id'] = message_to[0].id
        message_filters.pop('date_to')
        # Удаление и восстановление фильтра поиска по тексту сообщения
        search_filter = message_filters.get('search')
        message_filters.pop('search')
        messages = loop.run_until_complete(self.client.get_messages(**message_filters))
        message_filters['search'] = search_filter
        # Выборка сообщений по фильтрам
        message_list = []
        for message in messages:
            if message_filters.get('search'):
                if not message_filters.get('search').lower() in message.text.lower():
                    continue
            message_info = {
                'dialog_id': dialog_id,
                'id': message.id,
                'text': message.text,
                'date': message.date.astimezone().isoformat(' ', 'seconds')[:19] if message.date else '',
                'sender_id': message.sender_id,
                'grouped_id': message.grouped_id,
                'photo': message.photo is not None,
                'video': message.video is not None,
                'document': message.document is not None,
            }
            message_list.append(message_info)
        return message_list

    def get_message_detail(self, dialog_id: int, message_id: int) -> dict:
        """
        Получение сообщения по id диалога и id сообщения
        """
        message = loop.run_until_complete(self.client.get_messages(dialog_id, ids=message_id))
        details = {
            'dialog_id': dialog_id,
            'id': message.id,
            'date': message.date.astimezone().isoformat(' ', 'seconds')[:19] if message.date else '',
            'text': None,
            'media': None,
            'grouped_id': message.grouped_id,
        }
        # Скачивание медиафайлов
        media_file_name = clean_file_name(f'{dialog_id}_{message_id}')
        self.get_media(message, media_file_name, max_video_size=0)
        details['media'] = media_file_name

        продумать с именем файла

        # Преобразование текстовых гиперссылок в стандартные
        if message.text:
            matches = self.url_pattern.findall(message.text)
            if matches:
                message_text = message.text
                for match in matches:
                    message_text = message_text.replace(f'[{match[0]}]({match[1]})',
                                                        f'<a href = "{match[1]}" target="_blank" >{match[0]}</a>')
            else:
                message_text = message.text
        else:
            message_text = 'No text'
        details['text'] = message_text
        return details

    def get_media(self, message, media_file_name: str, max_video_size: int):
        """
        Загрузка медиа файла из сообщения
        """
        # Определяем тип медиа файла
        file_name_ext = None
        file_size = 0
        if message.file:
            file_name_ext = message.file.ext
            file_size = message.file.size
        if not file_name_ext:
            if message.photo:
                file_name_ext = '.jpg'
            if message.video:
                file_name_ext = '.mp4'
            if message.audio:
                file_name_ext = '.mp3'
        # result = []
        if file_name_ext:
            # Загружаем медиа файл
            file = f'{media_file_name}{file_name_ext}'
            if (not message.video) or (message.video and file_size < max_video_size):
                if not os.path.exists(file):
                    loop.run_until_complete(self.client.download_media(message, file=file))
                # result.append(file)
            # Если это видео, пробуем загрузить thumbnail
            if message.video:
                if message.video.thumbs:
                    file_name_ext = '_thumb.jpg'
                    file = f'{media_file_name}{file_name_ext}'
                    if not os.path.exists(file):
                        loop.run_until_complete(self.client.download_media(message, file=file, thumb=-1))
                    # result.append(file)
        # return None  # result


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


# async def main():
#     # Получаем список чатов (диалогов)
#     dialogs = client.iter_dialogs()
#     async for dialog in dialogs:
#         print(dialog.title, '   ', dialog.id)
#         # Получаем название директории для файлов данного диалога
#         dialog_dir = clean_file_name(f'{dialog.title}_{dialog.id}')
#         dialog_path = os.path.join(DIALOG_MEDIA_DIR, dialog_dir)
#         os.makedirs(dialog_path, exist_ok=True)
#         # Получаем список сообщений в каждом диалоге по пользовательскому фильтру
#         messages = client.iter_messages(dialog, limit=3)
#         async for message in messages:
#             print(message.id)
#             # Сохранение медиафайлов
#             if message.media:
#                 file_size = 0
#                 if message.file:
#                     if message.file.size:
#                         file_size = message.file.size
#                 if file_size < MAX_FILE_SIZE:
#                     local_message_date = message.date.astimezone()
#                     file_name_base = f'{local_message_date.strftime("%Y.%m.%d_%H-%M-%S")}_{message.grouped_id}_{message.id}'
#                     file_name_ext = None
#                     if message.file:
#                         if message.file.name:
#                             file_name_ext = str(message.file.name).lower().split('.')[1]
#                     if not file_name_ext:
#                         if message.video:
#                             file_name_ext = 'mp4'
#                         else:
#                             if message.photo:
#                                 file_name_ext = 'jpg'
#                             else:
#                                 if message.audio:
#                                     file_name_ext = 'mp3'
#                     file_name = os.path.join(dialog_path, f'{file_name_base}.{file_name_ext}')
#                     if not os.path.exists(file_name):
#                         await client.download_media(message, file=file_name, progress_callback=progress_callback)
#                     if message.video:
#                         if message.video.thumbs:
#                             file_name = os.path.join(dialog_path, f'{file_name_base}_thumb.jpg')
#                             if not os.path.exists(file_name):
#                                 await client.download_media(message, file=file_name, thumb=-1)
