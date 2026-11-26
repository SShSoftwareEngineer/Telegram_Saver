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
format_files_report: a function to form the summary line of the files of a message group (`2 Images, Video`)
limit_list: a function to cut a long list of report lines and mark the continuation
delete_media_files: a function to delete media files and the directories left empty
status_messages: a global instance of StatusMessages
"""

import base64
import re
from collections import Counter
from collections.abc import Iterable
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from html import escape
from pathlib import Path
from config import GlobalConst, MessageFileTypes

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
        progress (str): Progress of the running operation (e.g. `37%`), shown right after the spinner.
        report_list (list[str] | None): Report messages.
        messages (dict): Messages for the web interface.
        version (int): Counter of updates; the page sends the last one it has seen, so unchanged messages are not
            sent and not redrawn.
    """

    operation: str = ''
    state: str = ''
    progress: str = ''
    report_list: list[str] | None = None
    messages: dict = field(default_factory=dict)
    version: int = 0

    def mess_update(self, operation: str, report: str, new_list: bool = False, state: str = OPERATION_RUNNING,
                    progress: str = ''):
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
            progress (str): Progress of the operation (e.g. `37%`); every call sets it, so a call without it
                clears the progress
        """

        touched = request_status_touches.get()
        if touched is not None:
            touched.append(True)  # The current request has changed the status bar / Текущий запрос менял строку статуса
        self.state = state
        self.progress = progress
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
        self.progress = ''
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
        progress = f'<span class="sb-progress">{escape(self.progress)}</span> ' if self.progress else ''
        text = escape(self.operation)
        return f'<strong>Operation: </strong>{mark}{progress}<span class="sb-operation-text" title="{text}">{text}</span>'


# Global instance of StatusMessages
# Глобальный экземпляр StatusMessages
status_messages = StatusMessages()


def format_file_size(size: int | None) -> str:
    """
    File size in the units the user knows: `12.3 MB`, `45.6 KB`, `789 B` (1 MB = 2**20 bytes, as the download limit)
    Размер файла в понятных единицах: `12.3 MB`, `45.6 KB`, `789 B` (1 MB = 2**20 байт, как и предельный размер)
    """

    size = size or 0
    if size >= 2 ** 20:
        return f'{size / 2 ** 20:.1f} MB'
    if size >= 2 ** 10:
        return f'{size / 2 ** 10:.1f} KB'
    return f'{size} B'


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


# File types that are not counted in the summary line: the service HTML file of the message and the preview picture of
# a video (the video itself is counted)
# Типы файлов, которые не входят в строку-резюме: служебный HTML-файл сообщения и картинка-превью видео (само видео
# считается)
UNCOUNTED_FILE_TYPES = (MessageFileTypes.CONTENT, MessageFileTypes.THUMBNAIL)


def format_files_report(file_type_ids: Iterable[int]) -> str:
    """
    Forms the summary line of the files of a message group for the lists, e.g. `2 Images, Video`: a type with several
    files has the number and the plural form, a single file has the bare type name, the types are in alphabetical order,
    a type without files is not shown. The service file with the HTML of the message itself and the preview pictures of
    videos are not counted (`UNCOUNTED_FILE_TYPES`). The line is not stored: it is formed whenever a list is shown.
    Формирует строку-резюме файлов группы сообщений для списков, например `2 Images, Video`: у типа с несколькими
    файлами есть число и множественная форма, у одного файла - только название типа, типы идут по алфавиту, тип без
    файлов не показывается. Служебный файл с HTML самого сообщения и картинки-превью видео не считаются
    (`UNCOUNTED_FILE_TYPES`). Строка не хранится: она формируется при каждом показе списка.
    Attributes:
        file_type_ids (Iterable[int]): type IDs (`MessageFileTypes.type_id`) of the group files, one per file
    Returns:
        str: the summary line, empty if there are no counted files
    """

    counts = Counter(file_type.alt_text for file_type in map(MessageFileTypes.get_file_type_by_type_id, file_type_ids)
                     if file_type not in UNCOUNTED_FILE_TYPES)
    return ', '.join(f'{count} {alt_text}s' if count > 1 else alt_text for alt_text, count in sorted(counts.items()))


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


def find_avatar(cache_dir: Path, dialog_id: int) -> str | None:
    """
    Finds the avatar of a dialog in the cache: the file `_avatars/<dialog_id>/<photo_id>.jpg` (the newest if there are
    several). Returns its path relative to the cache directory, or None if there is none (no network, no database).
    Ищет аватарку диалога в кэше: файл `_avatars/<dialog_id>/<photo_id>.jpg` (самый новый, если их несколько).
    Возвращает его путь относительно директории кэша или None, если ее нет (без сети и базы данных).
    """

    avatar_dir = cache_dir / GlobalConst.cache_avatars_dir / str(dialog_id)
    try:
        files = [path for path in avatar_dir.glob('*.jpg') if path.is_file()]
        newest = max(files, key=lambda path: path.stat().st_mtime, default=None)
    except OSError:
        return None
    return newest.relative_to(cache_dir).as_posix() if newest else None


def avatar_data_uri(cache_dir: Path, dialog_id: int, max_bytes: int = 200 * 2 ** 10) -> str | None:
    """
    The avatar of a dialog from the cache as a `data:` address, to put it into a standalone HTML file (the file is
    opened from the disk, so it cannot link to the cache). None if there is no avatar or it is unexpectedly big.
    Аватарка диалога из кэша в виде адреса `data:` для автономного HTML файла (файл открывается с диска, поэтому
    ссылаться на кэш он не может). None, если аватарки нет или она неожиданно большая.
    """

    relative_path = find_avatar(cache_dir, dialog_id)
    if not relative_path:
        return None
    try:
        content = (cache_dir / relative_path).read_bytes()
    except OSError:
        return None
    if len(content) > max_bytes:
        return None
    return f'data:image/jpeg;base64,{base64.b64encode(content).decode("ascii")}'


def avatar_initials(title: str | None) -> str:
    """
    The initials for a chat without a photo, as in Telegram: the first letters of the first two words of the title
    (one letter for a single word, '?' if there is no letter at all).
    Инициалы для чата без фото, как в Telegram: первые буквы первых двух слов названия (одна буква для одного слова,
    '?', если букв нет совсем).
    """

    words = re.findall(r'[^\W_]+', title or '')[:2]
    return ''.join(word[0] for word in words).upper() or '?'


def avatar_color(dialog_id: int) -> str:
    """
    The background color of the stub of an avatar: it depends only on the dialog ID, so the chat has the same color
    on both tabs and after every start.
    Цвет фона заглушки аватарки: зависит только от ID диалога, поэтому у чата один и тот же цвет на обеих вкладках и
    после каждого запуска.
    """

    return f'hsl({abs(int(dialog_id)) * 47 % 360}, 45%, 48%)'


def remove_empty_dirs(directory: Path, stop: Path) -> None:
    """
    Deletes `directory` and then its parents while they are empty, up to `stop` (it stays). A directory outside of
    `stop` is never touched.
    Удаляет `directory`, затем его родителей, пока они пусты, вплоть до `stop` (он остается). Каталог вне `stop` не
    затрагивается никогда.
    """

    while directory != stop and stop in directory.parents:
        try:
            directory.rmdir()
        except OSError:  # not empty, or already deleted / не пуст или уже удален
            break
        directory = directory.parent


def _cache_files(cache_dir: Path) -> list[Path]:
    """
    The files of the cache without the chat avatars (`GlobalConst.cache_avatars_dir`): the previews and the videos
    Файлы кэша без аватарок чатов (`GlobalConst.cache_avatars_dir`): превью и видео
    """

    if not cache_dir.is_dir():
        return []
    avatars_dir = cache_dir / GlobalConst.cache_avatars_dir
    return [path for path in cache_dir.rglob('*') if path.is_file() and avatars_dir not in path.parents]


def clean_cache(cache_dir: Path, max_age_days: int, now: datetime | None = None) -> tuple[int, list[str]]:
    """
    Deletes the cached previews and videos that were last changed more than `max_age_days` ago, and the directories
    left empty. The chat avatars are never deleted. Errors do not stop the work: the file stays and its error is
    returned.
    Удаляет кэшированные превью и видео, измененные последний раз более `max_age_days` дней назад, и оставшиеся пустыми
    директории. Аватарки чатов не удаляются никогда. Ошибки не прерывают работу: файл остается, а его ошибка
    возвращается.
    Attributes:
        cache_dir (Path): Cache directory
        max_age_days (int): Maximum age of a file in days
        now (datetime | None): The current time (for tests)
    Returns:
        tuple[int, list[str]]: Number of deleted files and the error descriptions
    """

    limit = ((now or datetime.now()) - timedelta(days=max_age_days)).timestamp()
    deleted_count = 0
    errors: list[str] = []
    for path in _cache_files(cache_dir):
        try:
            if path.stat().st_mtime < limit:
                path.unlink()
                deleted_count += 1
        except OSError as error:
            errors.append(f'{path.name}: {error.strerror or error}')
    # Delete the directories left empty, the deepest first; the avatars directory and the cache itself stay
    # Удаляем оставшиеся пустыми директории, самые глубокие первыми; директория аватарок и сам кэш остаются
    avatars_dir = cache_dir / GlobalConst.cache_avatars_dir
    if cache_dir.is_dir():
        for directory in sorted((path for path in cache_dir.rglob('*') if path.is_dir()),
                                key=lambda item: len(item.parts), reverse=True):
            if directory == avatars_dir or avatars_dir in directory.parents:
                continue
            try:
                directory.rmdir()
            except OSError:  # not empty / не пуста
                pass
    return deleted_count, errors


if __name__ == '__main__':
    pass
