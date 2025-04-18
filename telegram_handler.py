from telethon import TelegramClient, utils
from telethon.tl.types import Chat, User, Channel, Message
import os
import re
from typing import List, Union, Optional, Dict, Any

DB_MEDIA_DIR = 'chats_media'
MAX_FILE_SIZE = 10 * 1024 * 1024


class TelegramHandler:
    # Используется паттерн Singleton для подключения к Telegram
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(TelegramHandler, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, session_name: str = None, api_id: int = None, api_hash: str = None, phone: str = None,
                 password: str = None):
        if self._initialized:
            return
        self.client = TelegramClient(session_name, api_id, api_hash)
        self.client.start(phone, password)
        self._initialized = True

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

    async def get_dialog_list(self) -> List[Dict[str, Any]]:
        """
        Получение списка всех диалогов
        """
        dialogs = await self.client.get_dialogs()
        # TODO: здесь дописать фильтры
        result = []
        for dialog in dialogs:
            dialog_info = {
                'id': dialog.id,
                'title': dialog.title if dialog.title else dialog.name if dialog.name else None,
                'username': dialog.entity.username if dialog.entity.username else None,
                'unread_count': dialog.unread_count,
                'last_message_date': dialog.date.isoformat('_', 'seconds') if dialog.date else None,
                'entity_type': self._get_entity_type(dialog),
            }
            result.append(dialog_info)
        return result

    async def get_chat_messages(self, chat_id: int, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Получение сообщений из заданного чата
        """
        # TODO: здесь дописать все фильтры: limit, по дате, по ids
        messages = await self.client.get_messages(chat_id, limit=limit)
        result = []
        for message in messages:
            message_info = {
                'id': message.id,
                'text': message.text,
                'date': message.date.isoformat('_', 'seconds') if message.date else None,
                'has_media': message.media is not None,
                'media_type': self._get_media_type(message) if message.media else None,
                'views': message.views,
                'grouped_id': message.grouped_id,
            }
            result.append(message_info)
        return result

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


def load_env(file_path: str) -> dict:
    env_vars = {}
    with open(file_path, 'r', encoding='utf-8') as file_env:
        for line in file_env:
            if not line.strip().startswith('#') and '=' in line:
                key, value = line.strip().split('=')
                env_vars[key] = value
    return env_vars


# Loading confidential Telegram API parameters / Загрузка конфиденциальных параметров Telegram API
private_settings = load_env('.env')

# Создание Telegram клиента
telegram_handler = TelegramHandler(session_name='.session',  # MemorySession(),
                                   api_id=private_settings['APP_API_ID'],
                                   api_hash=private_settings['APP_API_HASH'],
                                   phone=private_settings['PHONE'],
                                   password=private_settings['PASSWORD'])

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
# def get_dialogs():
#     with client:
#         client.loop.run_until_complete(get_dialog_list())
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
