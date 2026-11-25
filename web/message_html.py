"""
The HTML file of a saved message: rendered from the database record, so the same code creates it when the message is saved
and when maintenance restores a lost file.
HTML файл сохраненного сообщения: строится по записи в базе данных, поэтому один и тот же код создает его при
сохранении сообщения и при восстановлении потерянного файла сервисным обслуживанием.

write_message_html: renders the HTML of a message group and writes it to a file
"""

from pathlib import Path
from fastapi import Request
from config import MessageFileTypes, ProjectDirs
from database_handler import DbMessageGroup
from utils import avatar_data_uri, format_files_report
from web.deps import render_fragment


def write_message_html(request: Request, db_message_group: DbMessageGroup, file_path: Path) -> int:
    """
    Renders `export_message.html` for the message group and writes it to `file_path` (the directories are created).
    The group must be flushed to the database: its files and tags are read from there. The record of the HTML file
    itself is not shown on its own page, whether it exists already (a repeated save, a restore) or not.
    Строит `export_message.html` для группы сообщений и записывает в `file_path` (директории создаются). Группа должна
    быть сброшена (flush) в базу данных: ее файлы и теги читаются оттуда. Запись самого HTML файла на его странице не
    показывается, существует она уже (повторное сохранение, восстановление) или нет.
    Attributes:
        request (Request): The current request (for the template context)
        db_message_group (DbMessageGroup): The message group
        file_path (Path): The HTML file to write
    Returns:
        int: The size of the written file in bytes
    """

    export_data = db_message_group.get_export_data()
    content_paths = {db_file.file_path for db_file in db_message_group.files
                     if db_file.file_type_id == MessageFileTypes.CONTENT.type_id}
    export_data['files'] = [file for file in export_data['files'] if file['file_path'] not in content_paths]
    # The file names without directories: the page opens from the directory where the files lie
    # Имена файлов без директорий: страница открывается из директории, где лежат файлы
    for file in export_data['files']:
        file['file_name'] = Path(file['file_path']).name
    # The avatar of the chat is put into the file itself (a `data:` address), the file stays standalone; without
    # an avatar in the cache the template draws a circle with the initials
    # Аватарка чата вставляется в сам файл (адрес `data:`), файл остается автономным; если аватарки в кэше нет,
    # шаблон рисует круг с инициалами
    export_data['avatar_uri'] = avatar_data_uri(Path(ProjectDirs.cache_dir), db_message_group.dialog_id)
    export_data['files_report'] = format_files_report(db_file.file_type_id for db_file in db_message_group.files)
    content = render_fragment(request, 'export_message.html', **export_data).encode('utf-8')
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_bytes(content)
    return len(content)
