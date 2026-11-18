"""
The module contains classes, functions, and variables that are used in other modules.
Модуль содержит классы, функции и переменные, которые используются в других модулях.

class StatusMessages: a class to hold status messages for the web interface.
OPERATION_RUNNING, OPERATION_DONE, OPERATION_ERROR: states of the operation shown in the status bar
request_status_touches: a context variable that tells the request middleware the request used the status bar
parse_date_string: a function to parse a filter date (ISO) into the start or the end of that local day
local_day_start: a function returning the start of the local day, the given number of days ago
to_utc: a function to convert a datetime to UTC (naive datetimes are local time)
to_local: a function to convert a datetime to the local time zone of the system (naive datetimes are local time)
clean_file_path: a function to clean a file or directory name from invalid characters
limit_list: a function to cut a long list of report lines and mark the continuation
delete_media_files: a function to delete media files and the directories left empty
status_messages: a global instance of StatusMessages
"""

import re
from collections.abc import Iterable
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from html import escape
from pathlib import Path

# States of the operation shown in the status bar / Состояния операции в строке статуса
OPERATION_RUNNING = 'running'
OPERATION_DONE = 'done'
OPERATION_ERROR = 'error'

# A list the request middleware puts here for the time of a request: `mess_update` adds an item to it, so the
# middleware knows that this very request (not a parallel status poll) has used the status bar. A mutable list is used
# because the route runs in a thread with a copy of the context: the list is shared, a new value would not be.
# Список, который middleware запросов кладет сюда на время запроса: `mess_update` добавляет в него элемент, поэтому
# middleware знает, что строкой статуса пользовался именно этот запрос (а не параллельный опрос статуса). Взят
# изменяемый список, потому что роут выполняется в потоке с копией контекста: список общий, новое значение - нет.
request_status_touches: ContextVar[list[bool] | None] = ContextVar('request_status_touches', default=None)


@dataclass
class StatusMessages:
    """
    A class to hold status messages for the web interface.
    Класс для хранения статусных сообщений для веб-интерфейса.
    Attributes:
        operation (str): Current operation.
        state (str): State of the operation: running, done or error (empty before the first operation).
        report_list (list[str] | None): Report messages.
        messages (dict): Messages for the web interface.
        version (int): Counter of updates; the page sends the last one it has seen, so unchanged messages are not
            sent and not redrawn.
    """

    operation: str = ''
    state: str = ''
    report_list: list[str] | None = None
    messages: dict = field(default_factory=dict)
    version: int = 0

    def mess_update(self, operation: str, report: str, new_list: bool = False, state: str = OPERATION_RUNNING):
        """
        Sets the current status messages for the web interface. Every call marks the operation as running; the end
        of the operation is marked by `finish` (the request middleware calls it when the request is over).
        Устанавливает текущие статусные сообщения для веб-интерфейса. Каждый вызов помечает операцию как идущую;
        конец операции отмечает `finish` (его вызывает middleware запросов, когда запрос завершен).
        Attributes:
            operation (str): Current operation description
            report (str): Report message to add
            new_list (bool): If True, starts a new report list
            state (str): State of the operation (`OPERATION_RUNNING` by default; the error handler passes
                `OPERATION_ERROR`)
        """

        touched = request_status_touches.get()
        if touched is not None:
            touched.append(True)  # The current request has changed the status bar / Текущий запрос менял строку статуса
        self.state = state
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
        # The texts (file names, chat titles, error messages) are escaped here, once, because the string goes to the
        # page as HTML; `report_list` and the console output keep the original text. Callers must not escape them.
        # Тексты (имена файлов, названия чатов, сообщения об ошибках) экранируются здесь, один раз, потому что строка
        # попадает на страницу как HTML; `report_list` и вывод в консоль сохраняют исходный текст. Вызывающий код
        # не должен экранировать их сам.
        # Chronological order, the newest line is the last; the page selects it, so the closed list shows it
        # Хронологический порядок, новая строка последняя; страница выбирает ее, поэтому закрытый список показывает ее
        select_string = ''
        if self.report_list:
            select_string = '\n'.join([f'<option>{escape(current_report)}</option>'
                                       for current_report in self.report_list])
        self.messages = {'sb_operation': self._operation_html(), 'sb_report': select_string}
        self.version += 1
        # Print the report message to the console
        # Вывод сообщения отчета в консоль
        print(f'{current_time}  {self.operation} - {report}')

    def finish(self, error: bool = False):
        """
        Marks the current operation as finished (a check mark or a cross instead of the spinner). Does nothing if there
        is no operation or it is already marked. The reports are not touched.
        Помечает текущую операцию как завершенную (галочка или крестик вместо крутилки). Ничего не делает, если
        операции нет или она уже отмечена. Отчеты не меняются.
        Attributes:
            error (bool): The operation has failed
        """

        new_state = OPERATION_ERROR if error else OPERATION_DONE
        if not self.operation or self.state == new_state:
            return
        self.state = new_state
        self.messages = {**self.messages, 'sb_operation': self._operation_html()}
        self.version += 1

    def _operation_html(self) -> str:
        """
        HTML of the operation title: the label, the state mark (always in the same place, right after the label) and
        the escaped operation text. The spinner is a CSS animation, so the page needs no script for it.
        HTML заголовка операции: метка, значок состояния (всегда на одном месте, сразу после метки) и экранированный
        текст операции. Крутилка - CSS-анимация, поэтому странице не нужен для нее скрипт.
        """

        mark = {OPERATION_RUNNING: '<span class="sb-spinner" title="In progress"></span> ',
                OPERATION_DONE: '<span class="sb-mark" title="Finished">✅</span> ',
                OPERATION_ERROR: '<span class="sb-mark" title="Failed">❌</span> '}.get(self.state, '')
        return f'<strong>Operation: </strong>{mark}{escape(self.operation)}'


# Global instance of StatusMessages
# Глобальный экземпляр StatusMessages
status_messages = StatusMessages()


def parse_date_string(date_str: str | None, end_of_day: bool = False) -> datetime | None:
    """
    Parses the date of a filter (`<input type="date">` always sends ISO `YYYY-MM-DD`) into a boundary of that day in the
    local time of the system: 00:00:00 or, with `end_of_day`, 23:59:59.999999. The result is aware, so Telethon (it
    takes a naive datetime for UTC) and the database (stores UTC) get the right moment. Any other format is not a
    date of the form: the result is None, the filter is off.
    Разбирает дату фильтра (`<input type="date">` всегда присылает ISO `YYYY-MM-DD`) в границу этого дня в локальном
    времени системы: 00:00:00 или, при `end_of_day`, 23:59:59.999999. Результат aware, чтобы Telethon (наивную дату он
    считает UTC) и база данных (хранит UTC) получали верный момент. Любой другой формат - не дата формы: результат
    None, фильтр выключен.
    Attributes:
        date_str (str | None): date string from the form
        end_of_day (bool): the end of the day instead of its start
    Returns:
        datetime | None: aware datetime in the local time zone, or None if the string is empty or not a valid date
    """

    if not date_str:
        return None
    try:
        day = datetime.strptime(date_str.strip(), '%Y-%m-%d')
        if end_of_day:
            day = day.replace(hour=23, minute=59, second=59, microsecond=999999)
        return to_local(day)
    except (ValueError, OverflowError, OSError):
        return None


def local_day_start(days_ago: int = 0) -> datetime:
    """
    Start (00:00:00) of the local day, the given number of days ago, as an aware datetime
    Начало (00:00:00) локального дня, заданное число дней назад, как aware дата-время
    Attributes:
        days_ago (int): number of days back from today
    Returns:
        datetime: aware datetime in the local time zone
    """

    day = (datetime.now() - timedelta(days=days_ago)).replace(hour=0, minute=0, second=0, microsecond=0)
    return to_local(day)


def to_utc(value: datetime) -> datetime:
    """
    Converts a datetime to UTC. A naive datetime is local time of the system (the Python rule), not UTC.
    Переводит дату-время в UTC. Наивная дата-время - это локальное время системы (правило Python), а не UTC.
    Attributes:
        value (datetime): date and time
    Returns:
        datetime: aware datetime in UTC
    """

    return value.astimezone(timezone.utc)


def to_local(value: datetime) -> datetime:
    """
    Converts a datetime to the local time zone of the system (the time zone of the OS settings). A naive datetime is
    already local time: it only gets the time zone.
    Переводит дату-время в локальный часовой пояс системы (пояс из настроек ОС). Наивная дата-время уже локальная:
    ей только присваивается часовой пояс.
    Attributes:
        value (datetime): date and time
    Returns:
        datetime: aware datetime in the local time zone
    """

    return value.astimezone()


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
