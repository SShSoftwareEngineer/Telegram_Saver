"""
Tests of the schema migrations (Alembic): a new database, a database made before the migrations, the latest revision,
the agreement of the models and the migrations, Telegram IDs over int32.
Тесты миграций схемы (Alembic): новая база, база, созданная до миграций, последняя ревизия, согласованность моделей и
миграций, ID Telegram больше int32.
"""

import sqlite3
from datetime import datetime
from contextlib import closing
from pathlib import Path
import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, text
from config import ProjectDirs
from database_handler import Base, DatabaseHandler, DbDialog, DbDialogType, DbFile, DbFileType, DbMessageGroup
import schema_migrations
from schema_migrations import BASELINE_REVISION, VERSION_TABLE

BIG_DIALOG_ID = -1001234567890  # A channel ID (marked), does not fit into int32 / ID канала, не помещается в int32
BIG_USER_ID = 8837960131  # A user ID over int32 / ID пользователя больше int32


def head_revision() -> str:
    """The latest revision of the migration scripts / Последняя ревизия скриптов миграций"""
    return ScriptDirectory.from_config(schema_migrations._alembic_config()).get_current_head()


def migrate_to(database_file: Path, revision: str) -> None:
    """Applies the migrations up to `revision` on a database file / Применяет миграции до `revision` к файлу базы"""
    config = schema_migrations._alembic_config()
    engine = create_engine(f'sqlite:///{database_file}')
    with engine.begin() as connection:
        config.attributes['connection'] = connection
        command.upgrade(config, revision)
    engine.dispose()


def schema_differences(database_file: Path) -> list:
    """What differs between the database and the models (an empty list: the same) / Чем база отличается от моделей"""
    engine = create_engine(f'sqlite:///{database_file}')
    with engine.connect() as connection:
        context = MigrationContext.configure(connection, opts={'compare_type': True})
        differences = compare_metadata(context, Base.metadata)
    engine.dispose()
    return differences


def read_revision(database_file: Path) -> str | None:
    """The revision written in the database / Ревизия, записанная в базе данных"""
    with closing(sqlite3.connect(database_file)) as connection:
        try:
            row = connection.execute(f'SELECT version_num FROM {VERSION_TABLE}').fetchone()
        except sqlite3.OperationalError:
            return None
    return row[0] if row else None


def seed_old_database(database_file: Path) -> None:
    """
    Fills a database of the revision 0001 with the records that must survive the migrations (the way the old
    application kept them)
    Заполняет базу ревизии 0001 записями, которые должны пережить миграции (как их хранило старое приложение)
    """
    with closing(sqlite3.connect(database_file)) as connection:
        connection.executescript(f"""
            INSERT INTO dialog_types (dialog_type_id, name) VALUES (1, 'CHANNEL');
            INSERT INTO file_types (file_type_id, name, alt_text, default_ext, sign)
                VALUES (1, 'Image', 'Image', '.jpg', 'pho');
            INSERT INTO dialogs (dialog_id, title, dialog_type_id) VALUES ({BIG_DIALOG_ID}, 'Old channel', 1);
            INSERT INTO message_groups (grouped_id, date, sender_id, selected, dialog_id)
                VALUES ('g1', '2024-01-01 10:00:00', {BIG_USER_ID}, 0, {BIG_DIALOG_ID});
            INSERT INTO files (message_id, file_path, size, grouped_id, file_type_id)
                VALUES (7, 'chat/a.jpg', 5, 'g1', 1);
            INSERT INTO tags (name, usage_count, created_at) VALUES ('t', 1, '2024-01-01 10:00:00');
            INSERT INTO message_group_tag_links (message_group_id, tag_id) VALUES ('g1', 1);
        """)
        connection.commit()


def test_migrations_agree_with_the_models(work_dir: Path):
    """All the migrations from scratch give exactly the schema of the models (a model change needs a migration)"""
    database_file = Path(ProjectDirs.data_base_file)
    migrate_to(database_file, 'head')
    assert schema_differences(database_file) == []


def test_new_database_gets_the_latest_revision(db_handler: DatabaseHandler):
    """A new database is created from the models, marked as the latest revision and equal to the migrations' schema"""
    database_file = Path(ProjectDirs.data_base_file)
    assert read_revision(database_file) == head_revision()
    assert schema_differences(database_file) == []
    # A new database has nothing to protect: no backup / У новой базы нечего защищать: копии нет
    assert not list((Path(ProjectDirs.data_base_dir) / 'backup').glob('*before_migration*'))


def test_old_database_is_marked_and_migrated_with_a_backup(work_dir: Path):
    """A database of the time before the migrations (no `alembic_version`) is migrated: data stays, backup is made"""
    database_file = Path(ProjectDirs.data_base_file)
    migrate_to(database_file, BASELINE_REVISION)
    seed_old_database(database_file)
    with closing(sqlite3.connect(database_file)) as connection:
        connection.execute(f'DROP TABLE {VERSION_TABLE}')  # The old application knew nothing about it
        connection.commit()

    handler = DatabaseHandler()
    try:
        assert read_revision(database_file) == head_revision()
        assert schema_differences(database_file) == []
        # The data survived, the big IDs are intact, the new column is empty
        dialog = handler.session.get(DbDialog, BIG_DIALOG_ID)
        assert dialog is not None and dialog.title == 'Old channel'
        group = handler.session.get(DbMessageGroup, 'g1')
        assert group.sender_id == BIG_USER_ID and group.dialog_id == BIG_DIALOG_ID
        assert [file.file_path for file in group.files] == ['chat/a.jpg']
        assert group.files[0].unavailable_reason is None
        assert [tag.name for tag in group.tags] == ['t']
        # No broken references after the tables were rebuilt / После пересоздания таблиц нет битых ссылок
        assert handler.session.execute(text('PRAGMA foreign_key_check')).all() == []
    finally:
        handler.session.close()
        handler.engine.dispose()
    backups = list((Path(ProjectDirs.data_base_dir) / 'backup').glob('*before_migration*'))
    assert len(backups) == 1
    with closing(sqlite3.connect(backups[0])) as connection:  # The copy is the old schema with the old data
        assert connection.execute('SELECT COUNT(*) FROM message_groups').fetchone()[0] == 1
        assert 'unavailable_reason' not in [row[1] for row in connection.execute('PRAGMA table_info(files)')]


def test_latest_revision_is_not_touched(work_dir: Path):
    """A database already at the latest revision is neither migrated nor backed up at the start"""
    DatabaseHandler().engine.dispose()  # Creates the database / Создает базу данных
    database_file = Path(ProjectDirs.data_base_file)
    modified = database_file.stat().st_mtime_ns
    handler = DatabaseHandler()
    handler.session.close()
    handler.engine.dispose()
    assert read_revision(database_file) == head_revision()
    assert not list((Path(ProjectDirs.data_base_dir) / 'backup').glob('*before_migration*'))
    assert modified <= database_file.stat().st_mtime_ns


def test_unknown_revision_stops_the_start(work_dir: Path):
    """A database of a newer application version (an unknown revision) is not touched: the start fails with an error"""
    DatabaseHandler().engine.dispose()
    with closing(sqlite3.connect(ProjectDirs.data_base_file)) as connection:
        connection.execute(f"UPDATE {VERSION_TABLE} SET version_num = '9999'")
        connection.commit()
    with pytest.raises(schema_migrations.UnknownRevisionError, match='9999') as error:
        DatabaseHandler()
    assert 'backup' in str(error.value) and 'newer version' in str(error.value)  # The message tells what to do
    assert read_revision(Path(ProjectDirs.data_base_file)) == '9999'  # Nothing changed / Ничего не изменилось
    assert not list((Path(ProjectDirs.data_base_dir) / 'backup').glob('*before_migration*'))


def test_telegram_ids_over_int32_are_stored(db_handler: DatabaseHandler):
    """The IDs that do not fit into int32 are saved and read back as they are (also by SQLAlchemy BigInteger)"""
    session = db_handler.session
    session.add(DbDialog(dialog_id=BIG_DIALOG_ID, title='Channel', dialog_type_id=1))
    session.flush()
    session.add(DbMessageGroup(grouped_id='big', date=datetime(2024, 1, 1),
                               sender_id=BIG_USER_ID, dialog_id=BIG_DIALOG_ID))
    session.add(DbFile(message_id=2 ** 33, file_path='x/y.jpg', size=1, grouped_id='big', file_type_id=1,
                       unavailable_reason='deleted'))
    session.commit()
    session.expire_all()
    group = session.get(DbMessageGroup, 'big')
    assert (group.sender_id, group.dialog_id) == (BIG_USER_ID, BIG_DIALOG_ID)
    assert group.files[0].message_id == 2 ** 33 and group.files[0].unavailable_reason == 'deleted'
    assert session.get(DbDialogType, 1) is not None and session.get(DbFileType, 1) is not None
