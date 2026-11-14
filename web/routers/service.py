"""
Service routes: the main page, the status bar, the database and file system maintenance.
Служебные маршруты: главная страница, строка статуса, сервисное обслуживание базы данных и файловой системы.
"""

import sqlite3
from contextlib import closing
from datetime import datetime
from html import escape
from pathlib import Path
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from configs.config import FormCfg, GlobalConst, MessageFileTypes, ProjectDirs
from database_handler import get_db_handler
from telegram_handler import get_tg_handler
from utils import limit_list, status_messages
from web.deps import state_lock, templates

router = APIRouter()


@router.get('/status_output')
def status_output() -> JSONResponse:
    """
    Updating the status bar. Without the lock: the page polls it while long operations hold the lock.
    Обновление строки статуса. Без замка: страница опрашивает его, пока долгие операции держат замок.
    """
    return JSONResponse(status_messages.messages)


@router.get('/', response_class=HTMLResponse)
def index(request: Request):
    """
    Application home page
    Главная страница приложения
    """
    with state_lock:
        dialog_list = get_tg_handler().current_state.dialog_list
        chats_count = f'({len(dialog_list)})' if dialog_list else ''
        # Rendering the main page template with displaying the number of Telegram chats
        # Рендеринг шаблона главной страницы с отображением количества чатов Telegram
        return templates.TemplateResponse(request, 'index.html', {'chats_count': chats_count})


def _format_size(size: int) -> str:
    """Human-readable file size / Размер файла в удобном для чтения виде"""
    return f'{size / 2 ** 20:.2f} MB' if size >= 2 ** 20 else f'{size / 2 ** 10:.1f} KB'


@router.post('/db_database_maintenance')
def db_database_maintenance() -> JSONResponse:
    """
    Database and file system maintenance. Nothing is deleted here: the files and directories of deleted messages are
    removed together with the messages (`/db_delete_selected_from_database`).
        1. Reporting the local files that are not referenced in the database (to delete them manually)
        2. Downloading files that are referenced in the database but are not present in the local file system
        3. Backing up the database (SQLite backup API: the database is in the WAL mode)
        4. Refreshing the lists of dialogs (unused ones are deleted) and tags (usage is recalculated,
           unused are deleted)
    Сервисное обслуживание базы данных и файловой системы. Здесь ничего не удаляется: файлы и директории удаленных
    сообщений удаляются вместе с сообщениями (`/db_delete_selected_from_database`).
        1. Отчет о локальных файлах, на которые нет ссылок в базе данных (для ручного удаления)
        2. Докачка файлов, на которые есть ссылки в базе данных, но которых нет в локальной файловой системе
        3. Резервное копирование базы данных
        4. Обновление списков диалогов (неиспользуемые удаляются) и тегов (пересчет использования, удаление
           неиспользуемых)
    """

    with state_lock:
        tg_handler = get_tg_handler()
        db_handler = get_db_handler()
        media_dir = Path(ProjectDirs.media_dir)
        # Files with the specified extensions: the database stores the paths relative to the media directory
        # Файлы с указанными расширениями: в базе данных пути хранятся относительно директории медиа
        file_ext_to_sync = [
            MessageFileTypes.IMAGE.default_ext,  # '.jpg'
            MessageFileTypes.VIDEO.default_ext,  # '.mp4'
            MessageFileTypes.CONTENT.default_ext  # '.html'
        ]
        database_files = set(db_handler.get_file_list_by_extension(file_ext_to_sync))
        local_files = {path.relative_to(media_dir).as_posix() for ext in file_ext_to_sync
                       for path in media_dir.rglob(f'*{ext}') if path.is_file()}
        # 1. Local files without a record in the database: only report them, with sizes, to delete manually
        # 1. Локальные файлы без записи в базе данных: только сообщаем о них с размерами, для ручного удаления
        orphan_files = sorted(local_files - database_files)
        orphan_lines = [f'{escape(name)} ({_format_size((media_dir / name).stat().st_size)})'
                        for name in orphan_files]
        total_size = sum((media_dir / name).stat().st_size for name in orphan_files)
        status_messages.mess_update('Synchronizing the list of local files with the database',
                                    f'Local files without a record in the database: {len(orphan_files)}'
                                    f'{f" ({_format_size(total_size)})" if orphan_files else ""}', True)
        for line in limit_list(orphan_lines, GlobalConst.status_list_max_items):
            status_messages.mess_update('', line)
        # 2. Download the files that are in the database but not in the local file system, excluding HTML files
        # 2. Докачиваем файлы, которые есть в базе данных, но отсутствуют в локальной файловой системе, кроме HTML
        downloaded_file_list = []
        for file_path in sorted(database_files - local_files):
            downloaded_file = db_handler.get_file_by_local_path(file_path)
            if downloaded_file and Path(file_path).suffix != MessageFileTypes.CONTENT.default_ext:
                downloaded_file_list.append(downloaded_file)
        if downloaded_file_list:
            tg_handler.download_message_file_from_list(downloaded_file_list)
        # 3. Database backup / Резервное копирование базы данных
        database_file = Path(ProjectDirs.data_base_file)
        database_backup = (Path(ProjectDirs.data_base_dir) / 'backup' /
                           f'{database_file.stem}_{datetime.now().strftime("%Y-%m-%d %H_%M_%S")}{database_file.suffix}')
        # Create backup file directories if they do not exist / Создаем директории резервного файла, если их нет
        database_backup.parent.mkdir(parents=True, exist_ok=True)
        # The database works in the WAL mode: the recent commits live in the `-wal` file, so copying the main file
        # gives an incomplete backup. The SQLite backup API makes a consistent copy of the live database.
        # База данных работает в режиме WAL: свежие коммиты лежат в файле `-wal`, поэтому копия основного файла
        # получается неполной. API резервного копирования SQLite делает согласованную копию работающей базы.
        with closing(sqlite3.connect(database_file)) as source, closing(sqlite3.connect(database_backup)) as target:
            source.backup(target)
        status_messages.mess_update('', 'Database backup created')
        # 4. Update the list of dialogs in the database, sorting them according to current settings and removing the
        # unused ones / Обновление списка диалогов в базе данных с сортировкой по текущим установкам и удалением
        # неиспользуемых
        db_handler.all_dialogues_list = db_handler.get_dialog_list()
        db_handler.current_state.dialog_list = db_handler.all_dialogues_list.copy()
        # Update list of tags in database, sorting them according to current settings and recalculating the number of
        # uses / Обновление списка тегов в базе данных с сортировкой по текущим установкам и пересчетом количества
        # использований
        db_handler.all_tags_list = db_handler.get_all_tag_list()
        # Updating dialogue lists and tags in the database form
        # Обновление списков диалогов и тегов в форме базы данных
        return JSONResponse({
            FormCfg.db_message_filter['dialog_select']: db_handler.get_select_content_string(
                db_handler.current_state.dialog_list, 'dialog_id', 'title'),
            FormCfg.db_detail_tags['all_detail_tags']: db_handler.get_select_content_string(
                db_handler.all_tags_list, 'id', 'name')})
