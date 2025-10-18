import re
from datetime import datetime
from typing import Optional, List
from dateutil.parser import parse


class StatusMessages:
    """
    A class to hold status messages for the web interface.
    """
    operation: str = ''  # Current operation
    report_list: Optional[List[str]] = None  # Report messages
    messages: dict = {}  # Messages for the web interface

    def mess_update(self, operation: str, report: str, new_list: bool = False):
        """
        Sets the current status messages for the web interface.
        """
        if operation:
            self.operation = operation
        current_time = datetime.now().strftime('%H:%M:%S.%f')[:-3]  # Current time with milliseconds
        if new_list or self.report_list is None:
            self.report_list = []
        if report:
            report_string = f'{current_time} - {report}'
            self.report_list.append(report_string)
        # Формируем строку для тега в HTML формате для содержимого <select>
        select_string = ''
        if self.report_list:
            select_string = '\n'.join(
                [f'<option>{current_report}</option>' for current_report in reversed(self.report_list)])
        self.messages = {'sb_operation': f'<strong>Operation: </strong>{self.operation}', 'sb_report': select_string}
        print(f'{current_time}  {self.operation} - {report}')  # Print the report message to the console


# Global instance of StatusMessages
status_messages = StatusMessages()


def parse_date_string(date_str: str):
    """
    Parses a date string and returns a datetime object.
    """
    if not date_str:
        return None
    try:
        return parse(date_str, dayfirst=True)
    except (ValueError, OverflowError):
        return None


def clean_file_path(file_path: str | None) -> str | None:
    """
    Очищает имя файла или директории от недопустимых символов
    """
    clean_filepath = None
    if file_path:
        # Удаляем или заменяем недопустимые символы Windows/Linux/URL: <>:"/\\|?* + пробелы, апострофы, скобки, амперсанды, проценты
        clean_filepath = re.sub(r'[<>:"/\\|?*\'`\s\t\n\r\f\v%&()]', '_', file_path)
        # Убираем множественные символы замены подряд на одинарные, а также в начале и конце
        clean_filepath = re.sub(f'{re.escape('_')}{{2,}}', '_', clean_filepath).strip('_')
        # Убираем множественные пробелы подряд на одинарные, а также в начале и конце
        clean_filepath = re.sub(f'{re.escape(' ')}{{2,}}', ' ', clean_filepath).strip(' ')
        # Убираем лишние точки в начале и конце
        clean_filepath = clean_filepath.strip('.')
    return clean_filepath


if __name__ == '__main__':
    pass
