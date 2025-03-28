import os
import re
from typing import Any

from telethon import TelegramClient
from flask import Flask, request

CHAT_MEDIA_DIR = 'chat_media'


def load_env(file_path: str) -> dict:
    """
    Loading confidential data for working with the Telegram API from the `.env` file.
    Загрузка конфиденциальных данных для работы с Telegram API из файла .env

    Arguments:
    file_path (str): a confidential data file name
    Returns:
    dict: a confidential data dictionary
    """
    env_vars = {}
    with open(file_path, 'r', encoding='utf-8') as file_env:
        for line in file_env:
            if not line.strip().startswith('#') and '=' in line:
                key, value = line.strip().split('=')
                env_vars[key] = value
    return env_vars


async def get_chat_list() -> Any:
    chat_list = await client.iter_dialogs()
    return chat_list


async def get_chat_messages(chat_id: int):
    pass


def clean_file_name(file_name):
    """
    Очищает имя файла/директории от недопустимых символов

    Args:
        filename (str): Исходное имя чата

    Returns:
        str: Безопасное имя для файловой системы
    """
    # Удаляем или заменяем недопустимые символы
    clean_filename = re.sub(r'[<>:"/\\|?*]', '_', file_name)
    # Заменяем множественные пробелы
    clean_filename = re.sub(r'\s+', '_', clean_filename)
    # Убираем лишние точки и пробелы в начале и конце
    clean_filename = clean_filename.strip('. ')
    return clean_filename


async def main():
    dialogs = client.iter_dialogs()
    async for dialog in dialogs:
        print(dialog.id, '   ', dialog.title)
        messages = client.iter_messages(dialog, limit=5)
        async for message in messages:
            print(message.id, '   ', message.text)
            # Сохранение медиафайлов
            if message.media:
                media_path = os.path.join(CHAT_MEDIA_DIR, clean_file_name(f'{dialog.title}_{dialog.id}'),
                                          f'{message.date.strftime("%Y.%m.%d_%H-%M-%S")}_{message.id}')
                os.makedirs(media_path, exist_ok=True)
                file_name = await message.download_media()
                file_name = clean_file_name(file_name)
                os.replace(file_name, os.path.join(media_path, file_name))
                if message.video:
                    if message.video.thumbs:
                        thumb_name = await message.download_media(thumb=-1)
                        os.replace(thumb_name, f'{os.path.join(media_path, file_name)}_thumb.jpg')


# text
# date
# photo
# video
# video.thumbs
# audio


# app = Flask(__name__)
#
#
# @app.route('/', methods=['GET', 'POST'])
# def index() -> str:
#     return jsonify({})


if __name__ == "__main__":
    # app.run(debug=True)

    # Loading confidential Telegram API parameters / Загрузка конфиденциальных параметров Telegram API
    private_settings = load_env('.env')
    client = TelegramClient(session='.session',  # MemorySession(),
                            api_id=private_settings['APP_API_ID'],
                            api_hash=private_settings['APP_API_HASH']).start(private_settings['PHONE'],
                                                                             private_settings['PASSWORD'])
    with client:
        client.loop.run_until_complete(main())

# Оставлять архивные подписки в базе
# Режимы: просмотр чата, отметка на сохранение, автоматические отметки по условию (продумать условия)
# Режимы: просмотр базы с возможностью удаления
# Режимы: синхронизация чата и базы с условиями (продумать условия)
# Экспорт выделенных постов в ХТМЛ файл, выделенных по условию (продумать условия)
# Проверять есть ли в базе текущее сообщение и если есть, то не добавлять его и грузить из базы
# Установить отдельно предельные размеры для файлов и медиа разных типов
# Установить фильтры: количество последних сообщений, диапазон дат, по ключевому слову, теги(?)
