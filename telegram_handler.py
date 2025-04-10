import os
import re
from typing import Any

from telethon import TelegramClient

from database_handler import Message, Dialog, Group, File, FileType, session

DIALOG_MEDIA_DIR = 'dialog_media'
MAX_FILE_SIZE = 10 * 1024 * 1024


def load_env(file_path: str) -> dict:
    env_vars = {}
    with open(file_path, 'r', encoding='utf-8') as file_env:
        for line in file_env:
            if not line.strip().startswith('#') and '=' in line:
                key, value = line.strip().split('=')
                env_vars[key] = value
    return env_vars


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


def progress_callback(current, total):
    print(f'{current / total:.2%}')


async def main():
    # Получаем список чатов (диалогов)
    dialogs = client.iter_dialogs()
    async for dialog in dialogs:
        print(dialog.title, '   ', dialog.id)
        # Получаем название директории для файлов данного диалога
        dialog_dir = clean_file_name(f'{dialog.title}_{dialog.id}')
        dialog_path = os.path.join(DIALOG_MEDIA_DIR, dialog_dir)
        os.makedirs(dialog_path, exist_ok=True)
        # Получаем список сообщений в каждом диалоге по пользовательскому фильтру
        messages = client.iter_messages(dialog, limit=3)
        async for message in messages:
            print(message.id)
            # Сохранение медиафайлов
            if message.media:
                file_size = 0
                if message.file:
                    if message.file.size:
                        file_size = message.file.size
                if file_size < MAX_FILE_SIZE:
                    local_message_date = message.date.astimezone()
                    file_name_base = f'{local_message_date.strftime("%Y.%m.%d_%H-%M-%S")}_{message.grouped_id}_{message.id}'
                    file_name_ext = None
                    if message.file:
                        if message.file.name:
                            file_name_ext = str(message.file.name).lower().split('.')[1]
                    if not file_name_ext:
                        if message.video:
                            file_name_ext = 'mp4'
                        else:
                            if message.photo:
                                file_name_ext = 'jpg'
                            else:
                                if message.audio:
                                    file_name_ext = 'mp3'
                    file_name = os.path.join(dialog_path, f'{file_name_base}.{file_name_ext}')
                    if not os.path.exists(file_name):
                        await client.download_media(message, file=file_name, progress_callback=progress_callback)
                    if message.video:
                        if message.video.thumbs:
                            file_name = os.path.join(dialog_path, f'{file_name_base}_thumb.jpg')
                            if not os.path.exists(file_name):
                                await client.download_media(message, file=file_name, thumb=-1)



if __name__ == "__main__":
    # app.run(debug=True)

    # Loading confidential Telegram API parameters / Загрузка конфиденциальных параметров Telegram API
    private_settings = load_env('.env')
    client = TelegramClient(session='.session',  # MemorySession(),
                            api_id=private_settings['APP_API_ID'],
                            api_hash=private_settings['APP_API_HASH']).start(
        private_settings['PHONE'], private_settings['PASSWORD'])
    with client:
        client.loop.run_until_complete(main())
