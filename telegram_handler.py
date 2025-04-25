import asyncio

from telethon import TelegramClient, utils
from telethon.tl.types import Chat, User, Channel, Message
import os
import re
from typing import List, Union, Optional, Dict, Any

DB_MEDIA_DIR = 'chats_media'
TELEGRAM_SETTINGS_FILE = '.env'
MAX_FILE_SIZE = 10 * 1024 * 1024

# Создаем и сохраняем цикл событий
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)


class TelegramHandler:

    def __init__(self):
        self._dialog_sorting = {'field': 'title', 'reverse': False}
        self._dialog_type_filter = None
        self._dialog_title_filter = None
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

    @property
    def dialog_sorting(self) -> dict:
        """
        Возвращает текущие настройки сортировки диалогов
        """
        return self._dialog_sorting

    @dialog_sorting.setter
    def dialog_sorting(self, value: str):
        """
        Устанавливает настройки сортировки списка диалогов Telegram
        """
        match value:
            case '0':
                self._dialog_sorting = {'field': 'title', 'reverse': False}
            case '1':
                self._dialog_sorting = {'field': 'title', 'reverse': True}
            case '2':
                self._dialog_sorting = {'field': 'last_message_date', 'reverse': False}
            case '3':
                self._dialog_sorting = {'field': 'last_message_date', 'reverse': True}

    @property
    def dialog_type_filter(self) -> str:
        """
        Возвращает текущий фильтр по типу диалогов
        """
        return self._dialog_type_filter

    @dialog_type_filter.setter
    def dialog_type_filter(self, value: str):
        """
        Устанавливает фильтр по типу диалогов
        """
        match value:
            case '0':
                self._dialog_type_filter = None
            case '1':
                self._dialog_type_filter = 'is_channel'
            case '2':
                self._dialog_type_filter = 'is_group'
            case '3':
                self._dialog_type_filter = 'is_user'

    def get_entity(self, entity_id: int) -> Any:
        """
        Получение сущности по id
        """
        entity = loop.run_until_complete(self.client.get_entity(entity_id))
        return entity

    def check_dialog_filters(self, dialog_info: dict) -> bool:
        """
        Проверка фильтров для информации о диалоге
        """
        result = True
        if self.dialog_type_filter:
            if not dialog_info[self.dialog_type_filter]:
                result = False
        return result

    def get_dialog_list(self) -> List[Dict[str, Any]]:
        """
        Получение списка всех диалогов
        """
        # TODO: здесь дописать фильтры
        dialogs = loop.run_until_complete(self.client.get_dialogs())
        result = []
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
            if self.check_dialog_filters(dialog_info):
                result.append(dialog_info)
        result.sort(key=lambda x: x[self.dialog_sorting['field']], reverse=self.dialog_sorting['reverse'])
        return result

    def get_dialog_messages(self, dialog_id: int) -> List[Dict[str, Any]]:
        """
        Получение сообщений из заданного чата
        """
        # TODO: здесь дописать все фильтры: limit, по дате, по ids
        dialog = self.get_entity(dialog_id)
        messages = loop.run_until_complete(self.client.get_messages(dialog, limit=10))
        result = []
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
            result.append(message_info)
        return result

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

    def _get_entity_type(entity) -> str:
        """
        Определение типа сущности Telethon
        """
        if isinstance(entity, User):
            return 'user'
        elif isinstance(entity, Chat):
            return 'group'
        elif isinstance(entity, Channel):
            if entity.megagroup:
                return 'supergroup'
            return 'channel'
        return 'unknown'


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
