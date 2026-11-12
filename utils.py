"""
The module contains classes, functions, and variables that are used in other modules.

class StatusMessages: a class to hold status messages for the web interface.
parse_date_string: a function to parse a date string and return a datetime object
clean_file_path: a function to clean a file or directory name from invalid characters
limit_list: a function to cut a long list of report lines and mark the continuation
delete_media_files: a function to delete media files and the directories left empty
status_messages: a global instance of StatusMessages
"""

import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from dateutil.parser import parse


@dataclass
class StatusMessages:
    """
    A class to hold status messages for the web interface.
    Класс для хранения статусных сообщений для веб-интерфейса.
    Attributes:
        operation (str): Current operation.
        report_list (list[str] | None): Report messages.
        messages (dict): Messages for the web interface.
    """

    operation: str = ''
    report_list: list[str] | None = None
    messages: dict = field(default_factory=dict)

    def mess_update(self, operation: str, report: str, new_list: bool = False):
        """
        Sets the current status messages for the web interface.
        Устанавливает текущие статусные сообщения для веб-интерфейса.
        Attributes:
            operation (str): Current operation description
            report (str): Report message to add
            new_list (bool): If True, starts a new report list
        """

        if operation:
            self.operation = operation
        current_time = datetime.now().strftime('%H:%M:%S.%f')[:-3]  # Current time with milliseconds
        if new_list or self.report_list is None:
            self.report_list = []
        if report:
            report_string = f'{current_time} - {report}'
            self.report_list.append(report_string)
        # Forming a string for a tag in HTML format for the content <select>
        # Формируем строку для тега в HTML формате для содержимого <select>
        select_string = ''
        if self.report_list:
            select_string = '\n'.join(
                [f'<option>{current_report}</option>' for current_report in reversed(self.report_list)])
        self.messages = {'sb_operation': f'<strong>Operation: </strong>{self.operation}', 'sb_report': select_string}
        # Print the report message to the console
        # Вывод сообщения отчета в консоль
        print(f'{current_time}  {self.operation} - {report}')


# Global instance of StatusMessages
# Глобальный экземпляр StatusMessages
status_messages = StatusMessages()


def parse_date_string(date_str: str) -> datetime | None:
    """
    Parses a date string and returns a datetime object.
    Парсит строку даты и возвращает объект datetime.
    Attributes:
        date_str (str): Date string to parse
    Returns:
        datetime | None: Parsed datetime object or None if parsing fails
    """

    if not date_str:
        return None
    try:
        return parse(date_str, dayfirst=True)
    except (ValueError, OverflowError):
        return None


def clean_file_path(file_path: str | None) -> str | None:
    """
    A function to clean a file or directory name from invalid characters
    Функция очищает имя файла или директории от недопустимых символов
    Attributes:
        file_path (str | None): The original file or directory name
    Returns:
        str | None: The cleaned file or directory name
    """

    clean_filepath = None
    if file_path:
        # Replace invalid Windows/Linux/URL characters: spaces, apostrophes, parentheses, ampersands, percent signs
        # Заменяем недопустимые символы Windows/Linux/URL: <>:"/\\|?* + пробелы, апострофы, скобки, амперсанды, проценты
        clean_filepath = re.sub(r'[<>:"/\\|?*\'`\s\t\n\r\f\v%&()]', '_', file_path)
        # Replace multiple consecutive replacement characters with single ones, as those at the beginning and end
        # Убираем множественные символы замены подряд на одинарные, а также в начале и конце
        clean_filepath = re.sub(f'{re.escape('_')}{{2,}}', '_', clean_filepath).strip('_')
        # Remove multiple consecutive spaces and replace them with single spaces, as well as at the beginning and end
        # Убираем множественные пробелы подряд на одинарные, а также в начале и конце
        clean_filepath = re.sub(f'{re.escape(' ')}{{2,}}', ' ', clean_filepath).strip(' ')
        # Remove extra dots at the beginning and end
        # Убираем лишние точки в начале и конце
        clean_filepath = clean_filepath.strip('.')
    return clean_filepath


def limit_list(items: list[str], max_items: int) -> list[str]:
    """
    Cuts a long list of report lines to `max_items` and adds '...' as a sign of the continuation
    Обрезает длинный список строк отчета до `max_items` и добавляет '...' как признак продолжения
    Attributes:
        items (list[str]): Report lines
        max_items (int): Maximum number of lines to keep
    Returns:
        list[str]: The same lines or the first `max_items` of them and '...'
    """

    if len(items) <= max_items:
        return items
    return [*items[:max_items], '...']


def delete_media_files(media_dir: str | Path, file_paths: Iterable[str]) -> tuple[int, list[str]]:
    """
    Deletes media files (paths are relative to the media directory) and then the directories left empty, going up the
    tree until the media directory (it always stays). A non-empty directory stops the climb. Errors do not stop the
    work: the file stays and its error is returned. A path outside the media directory is never touched.
    Удаляет файлы медиа (пути относительно директории медиа), затем директории, оставшиеся пустыми, поднимаясь вверх по
    дереву до директории медиа (она остается всегда). Непустая директория останавливает подъем. Ошибки не прерывают
    работу: файл остается, а его ошибка возвращается. Путь вне директории медиа никогда не затрагивается.
    Attributes:
        media_dir (str | Path): Media directory
        file_paths (Iterable[str]): File paths relative to the media directory
    Returns:
        tuple[int, list[str]]: Number of deleted files and the error descriptions
    """

    root = Path(media_dir).resolve()
    deleted_count = 0
    errors: list[str] = []
    for file_path in file_paths:
        full_path = (root / file_path).resolve()
        if full_path == root or not full_path.is_relative_to(root):
            errors.append(f'{file_path}: outside of the media directory')
            continue
        try:
            if full_path.is_file():
                full_path.unlink()
                deleted_count += 1
        except OSError as error:
            errors.append(f'{file_path}: {error.strerror or error}')
            continue
        # Delete the empty directories up to the media directory / Удаляем пустые директории вплоть до директории медиа
        parent = full_path.parent
        while parent != root:
            try:
                parent.rmdir()
            except FileNotFoundError:
                pass
            except OSError:  # the directory is not empty (or is busy): the directories above are not empty either
                break
            parent = parent.parent
    return deleted_count, errors


if __name__ == '__main__':
    pass
