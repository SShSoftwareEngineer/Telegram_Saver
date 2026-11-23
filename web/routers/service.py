"""
Service routes: the main page, the status bar, the database and file system maintenance.
Служебные маршруты: главная страница, строка статуса, сервисное обслуживание базы данных и файловой системы.
"""

import glob
import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from configs.config import FormCfg, GlobalConst, MessageFileTypes, ProjectDirs
from database_handler import DbFile, get_db_handler
from telegram_handler import get_tg_handler
from utils import limit_list, status_messages
from web.deps import state_lock, templates
from web.message_html import write_message_html

router = APIRouter()

# Paths (relative to the media directory) that maintenance could not download: they are not retried until the restart
# Пути (относительно директории медиа), которые сервисное обслуживание не смогло скачать: до перезапуска не повторяются
_failed_downloads: set[str] = set()


def rotate_database_backups(backup_dir: Path, stem: str, suffix: str, keep: int) -> tuple[int, list[str]]:
    """
    Keeps only the `keep` latest backups in `backup_dir`, deletes the older ones. Only the files named
    `<stem>_<date><suffix>` (the date in `GlobalConst.file_datetime_format`) are considered: other files are not touched.
    The age is taken from the date in the name, not from the file time: copying a file does not change its place.
    Returns the number of deleted files and the names of the files that could not be deleted.
    Оставляет в `backup_dir` только `keep` последних резервных копий, более старые удаляет. Учитываются только файлы
    `<stem>_<дата><suffix>` (дата в формате `GlobalConst.file_datetime_format`): остальные не трогаются. Возраст берется
    из даты в имени, а не из времени файла: копирование файла не меняет его место в порядке.
    Возвращает число удаленных файлов и имена файлов, которые удалить не удалось.
    """
    backups: list[tuple[datetime, Path]] = []
    for path in backup_dir.glob(f'{glob.escape(stem)}_*{glob.escape(suffix)}'):
        if not path.is_file():
            continue
        try:
            backups.append((datetime.strptime(path.name.removeprefix(f'{stem}_').removesuffix(suffix),
                                              GlobalConst.file_datetime_format), path))
        except ValueError:
            continue  # Not a backup made by maintenance / Не копия, созданная сервисным обслуживанием
    backups.sort(key=lambda item: item[0], reverse=True)
    deleted = 0
    failed: list[str] = []
    for _, path in backups[max(keep, 1):]:  # At least the latest backup is always kept / Последняя копия остается всегда
        try:
            path.unlink()
            deleted += 1
        except OSError:
            failed.append(path.name)
    return deleted, failed


@router.get('/status_output')
def status_output(since: int | None = None) -> JSONResponse:
    """
    Updating the status bar. Without the lock: the page polls it while long operations hold the lock.
    `since` is the version the page has already shown: if it is the current one, the body is empty (nothing to
    redraw); the current version is always in the `X-Status-Version` header. Any other value (including one left
    from before a server restart) gets the messages.
    Обновление строки статуса. Без замка: страница опрашивает его, пока долгие операции держат замок.
    `since` - версия, которую страница уже показала: если она текущая, тело пустое (перерисовывать нечего); текущая
    версия всегда в заголовке `X-Status-Version`. Любое другое значение (в том числе оставшееся от запуска до
    перезапуска сервера) получает сообщения.
    """
    version = status_messages.version
    content = {} if since == version else status_messages.messages
    return JSONResponse(content, headers={'X-Status-Version': str(version)})


@router.get('/', response_class=HTMLResponse)
def index(request: Request):
    """
    Application home page
    Главная страница приложения
    """
    with state_lock:
        # The lists, the counters next to them and the filter dates all come from the current state of the handlers
        # (the context processor), so after a reload they agree on every tab
        # Списки, счетчики рядом с ними и даты фильтров берутся из текущего состояния обработчиков (контекстный
        # процессор), поэтому после перезагрузки они согласованы на каждой вкладке
        return templates.TemplateResponse(request, 'index.html')


def _format_size(size: int) -> str:
    """Human-readable file size / Размер файла в удобном для чтения виде"""
    return f'{size / 2 ** 20:.2f} MB' if size >= 2 ** 20 else f'{size / 2 ** 10:.1f} KB'


@router.post('/db_database_maintenance')
def db_database_maintenance(request: Request) -> JSONResponse:
    """
    Database and file system maintenance. Nothing is deleted here: the files and directories of deleted messages are
    removed together with the messages (`/db_delete_selected_from_database`).
        1. Reporting the local files that are not referenced in the database (to delete them manually)
        1a. Recreating the HTML files of messages (from the database, same template as when saving) that are referenced
            in the database but are not present in the local file system
        2. Downloading files that are referenced in the database but are not present in the local file system (not more
           than `GlobalConst.maintenance_max_downloads` per run; the files that failed are skipped until the restart)
        3. Backing up the database (SQLite backup API: the database is in the WAL mode)
        4. Refreshing the lists of dialogs (unused ones are deleted) and tags (usage is recalculated,
           unused are deleted)
    Сервисное обслуживание базы данных и файловой системы. Здесь ничего не удаляется: файлы и директории удаленных
    сообщений удаляются вместе с сообщениями (`/db_delete_selected_from_database`).
        1. Отчет о локальных файлах, на которые нет ссылок в базе данных (для ручного удаления)
        1а. Пересоздание HTML файлов сообщений (из базы данных, тем же шаблоном, что при сохранении), на которые есть
            ссылки в базе данных, но которых нет в локальной файловой системе
        2. Докачка файлов, на которые есть ссылки в базе данных, но которых нет в локальной файловой системе (не больше
           `GlobalConst.maintenance_max_downloads` за запуск; файлы, которые не скачались, пропускаются до перезапуска)
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
        orphan_lines = [f'{name} ({_format_size((media_dir / name).stat().st_size)})'
                        for name in orphan_files]
        total_size = sum((media_dir / name).stat().st_size for name in orphan_files)
        status_messages.mess_update('Synchronizing the list of local files with the database',
                                    f'Local files without a record in the database: {len(orphan_files)}'
                                    f'{f" ({_format_size(total_size)})" if orphan_files else ""}', True)
        for line in limit_list(orphan_lines, GlobalConst.status_list_max_items):
            status_messages.mess_update('', line)
        # 1a. Recreate the HTML files of the messages that are in the database but not in the local file system:
        # they are rendered from the database, so Telegram is not needed (and there is no limit as for downloading)
        # 1а. Пересоздаем HTML файлы сообщений, которые есть в базе данных, но отсутствуют в локальной файловой системе:
        # они строятся по базе данных, поэтому Telegram не нужен (и лимита, как у докачки, нет)
        restored_count = 0
        unrestored_lines = []
        for file_path in sorted(database_files - local_files):
            if Path(file_path).suffix != MessageFileTypes.CONTENT.default_ext:
                continue
            # The path is unique and every file record belongs to a message group (a foreign key, NOT NULL)
            # Путь уникален, а каждая запись файла принадлежит группе сообщений (внешний ключ, NOT NULL)
            db_file = db_handler.session.query(DbFile).filter_by(file_path=file_path).one()
            try:
                db_file.size = write_message_html(request, db_file.message_group, media_dir / file_path)
            except OSError as error:
                unrestored_lines.append(f'{file_path}: {error.strerror or error}')
                continue
            restored_count += 1
        db_handler.session.commit()
        if restored_count:
            status_messages.mess_update('', f'HTML files restored: {restored_count}')
        if unrestored_lines:
            status_messages.mess_update('', f'HTML files not restored: {len(unrestored_lines)}')
            for line in limit_list(unrestored_lines, GlobalConst.status_list_max_items):
                status_messages.mess_update('', line)
        # 2. Download the files that are in the database but not in the local file system, excluding HTML files.
        # Not more than `maintenance_max_downloads` per run: the lock is held all this time, so a lost media directory
        # must not freeze the application for minutes; the next run continues with the rest
        # 2. Докачиваем файлы, которые есть в базе данных, но отсутствуют в локальной файловой системе, кроме HTML.
        # Не больше `maintenance_max_downloads` за запуск: замок держится все это время, поэтому потерянная директория
        # медиа не должна подвешивать приложение на минуты; следующий запуск продолжит с остатка
        missing_files = []
        skipped_count = 0
        for file_path in sorted(database_files - local_files):
            if Path(file_path).suffix == MessageFileTypes.CONTENT.default_ext:
                continue
            if file_path in _failed_downloads:
                skipped_count += 1
                continue
            downloaded_file = db_handler.get_file_by_local_path(file_path)
            if downloaded_file:
                missing_files.append(downloaded_file)
        batch = missing_files[:GlobalConst.maintenance_max_downloads]
        if batch:
            tg_handler.download_message_file_from_list(batch)
            # A file that is still missing could not be downloaded (e.g. the message is deleted in Telegram): do not
            # try it again until the restart, otherwise such files would take the whole limit of every run
            # Файл, которого все еще нет, скачать не удалось (например, сообщение удалено в Telegram): повторно не
            # пытаемся до перезапуска, иначе такие файлы занимали бы весь лимит каждого запуска
            failed = [f['file_path'] for f in batch if not (media_dir / f['file_path']).exists()]
            _failed_downloads.update(failed)
            status_messages.mess_update('', f'Missing files processed: {len(batch)} of {len(missing_files)}, '
                                            f'failed to download: {len(failed)}')
            if len(missing_files) > len(batch):
                status_messages.mess_update('', f'Limit of {GlobalConst.maintenance_max_downloads} files per run, '
                                                f'run again to download the rest')
        if skipped_count:
            status_messages.mess_update('', f'Skipped {skipped_count} files that could not be downloaded earlier '
                                            f'(retried after the restart)')
        # 3. Database backup / Резервное копирование базы данных
        database_file = Path(ProjectDirs.data_base_file)
        database_backup = (Path(ProjectDirs.data_base_dir) / 'backup' /
                           f'{database_file.stem}_{datetime.now().strftime(GlobalConst.file_datetime_format)}'
                           f'{database_file.suffix}')
        # Create backup file directories if they do not exist / Создаем директории резервного файла, если их нет
        database_backup.parent.mkdir(parents=True, exist_ok=True)
        # The database works in the WAL mode: the recent commits live in the `-wal` file, so copying the main file
        # gives an incomplete backup. The SQLite backup API makes a consistent copy of the live database.
        # База данных работает в режиме WAL: свежие коммиты лежат в файле `-wal`, поэтому копия основного файла
        # получается неполной. API резервного копирования SQLite делает согласованную копию работающей базы.
        with closing(sqlite3.connect(database_file)) as source, closing(sqlite3.connect(database_backup)) as target:
            source.backup(target)
        status_messages.mess_update('', 'Database backup created')
        # Delete the oldest backups over the limit / Удаляем самые старые копии сверх лимита
        deleted_backups, failed_backups = rotate_database_backups(
            database_backup.parent, database_file.stem, database_file.suffix, GlobalConst.db_backup_keep)
        if deleted_backups:
            status_messages.mess_update('', f'Old backups removed: {deleted_backups} '
                                            f'(the latest {GlobalConst.db_backup_keep} are kept)')
        if failed_backups:
            status_messages.mess_update('', f'Could not remove old backups: {", ".join(failed_backups)}')
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
