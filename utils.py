"""
The module contains classes, functions, and variables that are used in other modules.

class StatusMessages: a class to hold status messages for the web interface.
parse_date_string: a function to parse a date string and return a datetime object
clean_file_path: a function to clean a file or directory name from invalid characters
status_messages: a global instance of StatusMessages
"""

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List
from dateutil.parser import parse


@dataclass
class StatusMessages:
    """
    A class to hold status messages for the web interface.
    Класс для хранения статусных сообщений для веб-интерфейса.
    Attributes:
        operation (str): Current operation.
        report_list (List[str] | None): Report messages.
        messages (dict): Messages for the web interface.
    Methods:
        mess_update(operation: str, report: str, new_list: bool = False):
            Sets the current status messages for the web interface.
    """

    operation: str = ''  # Current operation / Текущая операция
    report_list: Optional[List[str]] = None  # Report messages / Сообщения отчета
    messages: dict = field(default_factory=dict)  # Messages for the web interface / Сообщения для веб-интерфейса

    def mess_update(self, operation: str, report: str, new_list: bool = False):
        """
        Sets the current status messages for the web interface.
        Устанавливает текущие статусные сообщения для веб-интерфейса.
        Arguments:
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


def parse_date_string(date_str: str) -> Optional[datetime]:
    """
    Parses a date string and returns a datetime object.
    Парсит строку даты и возвращает объект datetime.
    Arguments:
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


def clean_file_path(file_path: Optional[str]) -> Optional[str]:
    """
    A function to clean a file or directory name from invalid characters
    Функция очищает имя файла или директории от недопустимых символов
    Arguments:
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


if __name__ == '__main__':
    pass
