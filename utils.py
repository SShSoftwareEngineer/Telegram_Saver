import re
from datetime import datetime

from config.config import ProjectDirs


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


def cache_file_name(date_time: datetime, dialog_id: int, message_id: str) -> str:
    """
    Формирует имя файла для кэшированных медиафайлов
    """

    продумать о включении типа файла и поменять все в телеграм хендлере

    return clean_file_name(f'{date_time.strftime("%Y-%m-%d_%H:%M:%S")}_{dialog_id}_{message_id}')


if __name__ == '__main__':
    pass
