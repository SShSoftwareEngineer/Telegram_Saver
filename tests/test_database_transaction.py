"""
Tests of `DatabaseHandler` without the web layer: `transaction()` (commit on success, rollback and re-raise on an
error) and the creation of the database folder.
Тесты `DatabaseHandler` без веб-слоя: `transaction()` (commit при успехе, rollback и повторный выброс при ошибке) и
создание папки базы данных.
"""

from pathlib import Path
import pytest
from configs.config import ProjectDirs
from database_handler import DatabaseHandler, DbDialog


def dialog_titles(db_handler: DatabaseHandler) -> list[str]:
    """Titles of the dialogs in the database / Названия диалогов в базе данных"""
    return [dialog.title for dialog in db_handler.session.query(DbDialog)]


def test_transaction_commits_on_success(db_handler: DatabaseHandler):
    """Without an error the changes are committed when `with` ends / Без ошибки изменения фиксируются"""
    with db_handler.transaction() as session:
        db_handler.upsert_record(DbDialog, {'dialog_id': 1}, {'title': 'Saved', 'dialog_type_id': 1})
        assert session is db_handler.session
    # A commit ends the transaction: the data is read from the database again / commit завершает транзакцию
    assert not db_handler.session.in_transaction()
    assert dialog_titles(db_handler) == ['Saved']


def test_transaction_rolls_back_and_reraises(db_handler: DatabaseHandler):
    """An error inside `with` rolls the changes back and is raised again; the session stays usable"""
    with pytest.raises(RuntimeError, match='boom'):
        with db_handler.transaction():
            db_handler.upsert_record(DbDialog, {'dialog_id': 1}, {'title': 'Lost', 'dialog_type_id': 1})
            raise RuntimeError('boom')
    assert dialog_titles(db_handler) == []
    # The session is not left in a failed state: the next transaction works / Следующая транзакция работает
    with db_handler.transaction():
        db_handler.upsert_record(DbDialog, {'dialog_id': 2}, {'title': 'Next', 'dialog_type_id': 1})
    assert dialog_titles(db_handler) == ['Next']


def test_transaction_rolls_back_after_database_error(db_handler: DatabaseHandler):
    """A database error (a violated constraint) at commit leaves the session usable (no PendingRollbackError)"""
    with pytest.raises(Exception):  # pylint: disable=broad-exception-caught
        with db_handler.transaction():
            # `title` is NOT NULL: the flush at commit fails with an IntegrityError
            # `title` NOT NULL: flush при commit падает с IntegrityError
            db_handler.session.add(DbDialog(dialog_id=5, title=None, dialog_type_id=1))  # type: ignore[arg-type]
    assert dialog_titles(db_handler) == []
    with db_handler.transaction():
        db_handler.upsert_record(DbDialog, {'dialog_id': 6}, {'title': 'After error', 'dialog_type_id': 1})
    assert dialog_titles(db_handler) == ['After error']


def test_database_folder_is_created(work_dir: Path):
    """On a fresh clone there is no `database/` folder: the handler creates it instead of failing with
    "unable to open database file" / В свежем клоне нет папки `database/`: обработчик создает ее, а не падает"""
    (work_dir / ProjectDirs.data_base_dir).rmdir()
    handler = DatabaseHandler()
    try:
        assert (work_dir / ProjectDirs.data_base_file).exists()
    finally:
        handler.session.close()
        handler.engine.dispose()
