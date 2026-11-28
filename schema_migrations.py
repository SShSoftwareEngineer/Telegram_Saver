"""
The module brings the database schema of the profile up to date at the start of the application (Alembic).
Модуль приводит схему базы данных профиля к актуальному виду при старте приложения (Alembic).

migrate_database: creates the schema of a new database or applies the pending migrations to an existing one
backup_before_migration: a copy of the database made before the migrations are applied
class UnknownRevisionError(RuntimeError): the database is newer than the application (the start is stopped)
"""

import logging
import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path
from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import MetaData, create_engine, inspect
from config import BASE_DIR, GlobalConst, ProjectDirs

logger = logging.getLogger(__name__)

# The revision with the schema that every database had before the migrations were introduced (`create_all`)
# Ревизия со схемой, которая была у каждой базы до введения миграций (`create_all`)
BASELINE_REVISION = '0001'
# The table where Alembic keeps the revision of the database / Таблица, где Alembic хранит ревизию базы данных
VERSION_TABLE = 'alembic_version'


class UnknownRevisionError(RuntimeError):
    """
    The database was migrated by a newer version of the application: this version does not know its schema, so the
    start is stopped and the database is not touched.
    База мигрирована более новой версией приложения: эта версия не знает ее схему, поэтому старт остановлен, а база не
    тронута.
    """

    def __init__(self, database_file: Path, current: str | None, head: str | None):
        super().__init__(
            f'The database {database_file} has the schema revision {current}, this version of the application knows '
            f'only up to {head}: the database was migrated by a newer version. The database is not changed. '
            f'Run the newer version of the code (the git branch), or restore the database from a copy in '
            f'{Path(ProjectDirs.data_base_dir) / "backup"} (the files `*_before_migration_*` hold the schema before '
            f'a migration). / База данных {database_file} имеет ревизию схемы {current}, эта версия приложения знает '
            f'только до {head}: базу мигрировала более новая версия. База не изменена. Запустите более новую версию '
            f'кода (ветку git) или восстановите базу из копии в {Path(ProjectDirs.data_base_dir) / "backup"} (файлы '
            f'`*_before_migration_*` хранят схему до миграции).')


def _alembic_config() -> Config:
    """Alembic config of the project (the scripts are in `migrations/`) / Конфигурация Alembic проекта"""

    return Config(str(BASE_DIR / 'alembic.ini'))


def backup_before_migration(database_file: Path) -> Path:
    """
    Makes a consistent copy of the database (the SQLite backup API: the database works in the WAL mode) next to the
    maintenance backups. The name does not match the maintenance pattern, so the rotation never deletes this copy.
    Делает согласованную копию базы данных (API резервного копирования SQLite: база работает в режиме WAL) рядом с
    копиями обслуживания. Имя не подходит под шаблон обслуживания, поэтому ротация эту копию никогда не удаляет.
    Attributes:
        database_file (Path): the database file
    Returns:
        Path: the copy
    """

    stamp = datetime.now().strftime(GlobalConst.file_datetime_format)
    backup_file = Path(ProjectDirs.data_base_dir) / 'backup' / f'{database_file.stem}_before_migration_{stamp}' \
                                                               f'{database_file.suffix}'
    backup_file.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(database_file)) as source, closing(sqlite3.connect(backup_file)) as target:
        source.backup(target)
    return backup_file


def migrate_database(metadata: MetaData) -> None:
    """
    Brings the schema of the database of the profile up to date:
    - a new database (no tables): the tables are created from the models and marked as the latest revision (the same as
      running all the migrations, a test checks that the models and the migrations agree);
    - a database made before the migrations (tables without `alembic_version`): marked as the baseline revision;
    - then, if the revision is not the latest, a backup copy is made and the pending migrations are applied.
    With the latest revision nothing is changed (one quick read of the version table).
    Приводит схему базы данных профиля к актуальному виду:
    - новая база (нет таблиц): таблицы создаются из моделей и помечаются последней ревизией (то же, что выполнить все
      миграции, тест проверяет, что модели и миграции согласованы);
    - база, созданная до миграций (таблицы без `alembic_version`): помечается базовой ревизией;
    - затем, если ревизия не последняя, делается резервная копия и применяются недостающие миграции.
    При последней ревизии ничего не меняется (одно быстрое чтение таблицы версии).
    Attributes:
        metadata (MetaData): the metadata of the models (used to create a new database)
    """

    database_file = Path(ProjectDirs.data_base_file)
    config = _alembic_config()
    head = ScriptDirectory.from_config(config).get_current_head()
    # Foreign keys are off here (the SQLite default): a table rebuilt by a migration must not fail on its own references
    # Здесь внешние ключи выключены (умолчание SQLite): пересоздаваемая миграцией таблица не должна падать на ссылках
    engine = create_engine(f'sqlite:///{database_file}')
    try:
        tables = set(inspect(engine).get_table_names())
        if not tables:
            metadata.create_all(engine)
            with engine.begin() as connection:
                config.attributes['connection'] = connection
                command.stamp(config, head)
            return
        with engine.begin() as connection:
            config.attributes['connection'] = connection
            if VERSION_TABLE not in tables:
                command.stamp(config, BASELINE_REVISION)
        with engine.connect() as connection:
            current = MigrationContext.configure(connection).get_current_revision()
        if current == head:
            return
        known = {script.revision for script in ScriptDirectory.from_config(config).walk_revisions()}
        if current not in known:
            raise UnknownRevisionError(database_file, current, head)
        backup_file = backup_before_migration(database_file)
        logger.warning('Database schema %s -> %s: a copy is saved to %s', current, head, backup_file)
        with engine.begin() as connection:
            config.attributes['connection'] = connection
            command.upgrade(config, 'head')
        logger.warning('Database schema is up to date (%s)', head)
    finally:
        engine.dispose()
