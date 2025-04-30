import asyncio
from calendar import month
from dataclasses import dataclass
from datetime import datetime

from telethon import TelegramClient, utils
from telethon.tl.types import Chat, User, Channel, Message
import os
import re
from typing import List, Union, Optional, Dict, Any

DB_MEDIA_DIR = 'chats_media'
TELEGRAM_SETTINGS_FILE = '.env'
MAX_FILE_SIZE = 10 * 1024 * 1024
MESSAGE_LIMIT = 20

# Создаем и сохраняем цикл событий
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)


@dataclass
class TgMessageSortFilter:
    _sort_order: str = 'asc'
    _date_from: Optional[datetime] = None
    _text_filter: Optional[str] = None
    _limit: int = MESSAGE_LIMIT

    @property
    def sort_order(self) -> bool:
        """
        Возвращает параметр Reverse для функции сортировки
        """
        result = False if self._sort_order == 'asc' else True
        return result

    @sort_order.setter
    def sort_order(self, value: str):
        """
        Устанавливает порядок сортировки
        """
        self._sort_order = 'asc' if value == '0' else 'desc'

    @property
    def date_from(self) -> Optional[datetime]:
        """
        Возвращает минимальную дату сообщения для фильтрации
        """
        return self._date_from

    @date_from.setter
    def date_from(self, value: str):
        """
        Устанавливает минимальную дату сообщения для фильтрации
        """
        if value:
            date_split = re.split(r'[/.-]', value)
            if len(date_split)==3:
                from_day, from_month, from_year = date_split
                try:
                    self._date_from = datetime(int(from_year), int(from_month), int(from_day))
                except ValueError:
                    self._date_from = None
        else:
            self._date_from = None

    @property
    def text_filter(self) -> Optional[str]:
        """
        Возвращает текущий фильтр по названию диалогов
        """
        return self._text_filter

    @text_filter.setter
    def text_filter(self, value: str):
        """
        Устанавливает фильтр по названию диалогов
        """
        self._text_filter = value if value else None

    @property
    def limit(self) -> int:
        """
        Возвращает максимальное количество последних сообщений для фильтрации
        """
        return self._limit

    @limit.setter
    def limit(self, value: str):
        """
        Устанавливает максимальное количество последних сообщений для фильтрации
        """
        try:
            self._limit = int(value)
        except ValueError:
            self._limit = MESSAGE_LIMIT


@dataclass
class TgDialogSortFilter:
    _sort_field: str = 'title'
    _sort_order: str = 'asc'
    _type_filter: Optional[str] = None
    _title_filter: Optional[str] = None

    @property
    def sort_field(self) -> str:
        """
        Возвращает текущее поле сортировки
        """
        return self._sort_field

    @sort_field.setter
    def sort_field(self, value: str):
        """
        Устанавливает поле сортировки
        """
        self._sort_field = 'title' if value == '0' else 'last_message_date'

    @property
    def sort_order(self) -> bool:
        """
        Возвращает параметр Reverse для функции сортировки
        """
        result = False if self._sort_order == 'asc' else True
        return result

    @sort_order.setter
    def sort_order(self, value: str):
        """
        Устанавливает направление сортировки
        """
        self._sort_order = 'asc' if value == '0' else 'desc'

    @property
    def type_filter(self) -> Optional[str]:
        """
        Возвращает текущий фильтр по типу диалогов
        """
        return self._type_filter

    @type_filter.setter
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

    @property
    def title_filter(self) -> Optional[str]:
        """
        Возвращает текущий фильтр по названию диалогов
        """
        return self._title_filter

    @title_filter.setter
    def title_filter(self, value: str):
        """
        Устанавливает фильтр по названию диалогов
        """
        self._title_filter = value if value else None

    def check_dialog_filters(self, dialog_info: dict) -> bool:
        """
        Проверка фильтров по названию и по типу для конкретного диалога
        """
        title_filter_result = True
        if self.title_filter:
            title_filter_result = str(dialog_info['title']).lower().find(self.title_filter.lower()) != -1
        type_filter_result = True
        if self.type_filter:
            type_filter_result = dialog_info[self.type_filter]
        return all([title_filter_result, type_filter_result])

    def sort_dialog_list(self, dialog_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Сортировка списка диалогов по заданному полю в заданном порядке
        """
        return sorted(dialog_list, key=lambda x: x[self.sort_field], reverse=self.sort_order)


class TelegramHandler:
    dialog_sort_filter: TgDialogSortFilter
    message_sort_filter: TgMessageSortFilter
    current_dialog_id: int

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
            if self.dialog_sort_filter.check_dialog_filters(dialog_info):
                dialog_list.append(dialog_info)
        return self.dialog_sort_filter.sort_dialog_list(dialog_list)

    def get_message_list(self, dialog_id: int) -> List[Dict[str, Any]]:
        """
        Получение списка сообщений из заданного чата с учетом фильтров и сортировки
        """
        dialog = self.get_entity(dialog_id)
        message_filter = {'entity': dialog,
                          'limit': self.message_sort_filter.limit if self.message_sort_filter.limit else MESSAGE_LIMIT,
                          'reverse': self.message_sort_filter.sort_order, }
        if self.message_sort_filter.date_from:
            message_filter['offset_date'] = self.message_sort_filter.date_from
        if self.message_sort_filter.text_filter:
            message_filter['search'] = self.message_sort_filter.text_filter
        messages = loop.run_until_complete(self.client.get_messages(**message_filter))
        message_list = []
        for message in messages:
            message_info = {
                'dialog_id': dialog_id,
                'id': message.id,
                'text': message.text if message.text else 'No text',
                'date': message.date.astimezone().isoformat(' ', 'seconds')[:19] if message.date else '',
                'has_media': message.media is not None,
                'views': message.views,
                'grouped_id': message.grouped_id,
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
            'text': message.text if message.text else 'No text',
            'date': message.date.astimezone().isoformat(' ', 'seconds')[:19] if message.date else '',
            'grouped_id': message.grouped_id,
        }
        return details

    async def download_media(self, chat_id: int, message_id: int, path: str) -> Optional[str]:
        """
        Получение медиа файла из сообщения
        """
        message = await self.client.get_messages(chat_id, ids=message_id)
        if not message or not message.media:
            return None
        return await self.client.download_media(message, path)

    # def _get_entity_type(entity) -> str:
    #     """
    #     Определение типа сущности Telethon
    #     """
    #     if isinstance(entity, User):
    #         return 'user'
    #     elif isinstance(entity, Chat):
    #         return 'group'
    #     elif isinstance(entity, Channel):
    #         if entity.megagroup:
    #             return 'supergroup'
    #         return 'channel'
    #     return 'unknown'


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

#
# from database_handler import Message, Dialog, Group, File, FileType, session
#

# # def progress_callback(current, total):
# #     print(f'{current / total:.2%}')
#
# async def get_dialog_list():
#     # Получаем список чатов (диалогов)
#     dialogs = client.iter_dialogs()
#     async for dialog in dialogs:
#         print(dialog.title, '   ', dialog.id)
#         # Получаем название директории для файлов данного диалога
#         dialog_dir = clean_file_name(f'{dialog.title}_{dialog.id}')
#         dialog_path = os.path.join(DB_MEDIA_DIR, dialog_dir)
#         os.makedirs(dialog_path, exist_ok=True)
#     return dialogs
#
#
#
# # async def main():
# #     # Получаем список чатов (диалогов)
# #     dialogs = client.iter_dialogs()
# #     async for dialog in dialogs:
# #         print(dialog.title, '   ', dialog.id)
# #         # Получаем название директории для файлов данного диалога
# #         dialog_dir = clean_file_name(f'{dialog.title}_{dialog.id}')
# #         dialog_path = os.path.join(DIALOG_MEDIA_DIR, dialog_dir)
# #         os.makedirs(dialog_path, exist_ok=True)
# #         # Получаем список сообщений в каждом диалоге по пользовательскому фильтру
# #         messages = client.iter_messages(dialog, limit=3)
# #         async for message in messages:
# #             print(message.id)
# #             # Сохранение медиафайлов
# #             if message.media:
# #                 file_size = 0
# #                 if message.file:
# #                     if message.file.size:
# #                         file_size = message.file.size
# #                 if file_size < MAX_FILE_SIZE:
# #                     local_message_date = message.date.astimezone()
# #                     file_name_base = f'{local_message_date.strftime("%Y.%m.%d_%H-%M-%S")}_{message.grouped_id}_{message.id}'
# #                     file_name_ext = None
# #                     if message.file:
# #                         if message.file.name:
# #                             file_name_ext = str(message.file.name).lower().split('.')[1]
# #                     if not file_name_ext:
# #                         if message.video:
# #                             file_name_ext = 'mp4'
# #                         else:
# #                             if message.photo:
# #                                 file_name_ext = 'jpg'
# #                             else:
# #                                 if message.audio:
# #                                     file_name_ext = 'mp3'
# #                     file_name = os.path.join(dialog_path, f'{file_name_base}.{file_name_ext}')
# #                     if not os.path.exists(file_name):
# #                         await client.download_media(message, file=file_name, progress_callback=progress_callback)
# #                     if message.video:
# #                         if message.video.thumbs:
# #                             file_name = os.path.join(dialog_path, f'{file_name_base}_thumb.jpg')
# #                             if not os.path.exists(file_name):
# #                                 await client.download_media(message, file=file_name, thumb=-1)
#
#
