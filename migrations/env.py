"""
Alembic environment: how the migrations connect to the database and which models they compare with.
Окружение Alembic: как миграции подключаются к базе данных и с какими моделями сравниваются.

The application passes an open connection (`config.attributes['connection']`, see `schema_migrations.py`). Started from
the command line (`alembic ...`), the environment opens the database of the selected profile itself.
Приложение передает открытое соединение (`config.attributes['connection']`, см. `schema_migrations.py`). При запуске из
командной строки (`alembic ...`) окружение само открывает базу данных выбранного профиля.
"""

from alembic import context
from sqlalchemy import create_engine
from config import ProjectDirs, ensure_profile_selected
from database_handler import Base

config = context.config
target_metadata = Base.metadata


def _configure(connection) -> None:
    """
    Common settings: the batch mode (SQLite cannot change a column in place, a table is rebuilt instead) and the
    comparison of column types (`BigInteger` instead of `Integer`).
    Общие настройки: пакетный режим (SQLite не умеет менять столбец на месте, таблица пересоздается) и сравнение типов
    столбцов (`BigInteger` вместо `Integer`).
    """

    context.configure(connection=connection, target_metadata=target_metadata, render_as_batch=True, compare_type=True)


def run_migrations() -> None:
    """
    Runs the migrations on the passed connection or on the database of the selected profile
    Выполняет миграции на переданном соединении или на базе данных выбранного профиля
    """

    connection = config.attributes.get('connection')
    if connection is not None:
        _configure(connection)
        with context.begin_transaction():
            context.run_migrations()
        return
    ensure_profile_selected()
    # Foreign keys stay off (the SQLite default): a table rebuilt by a migration must not fail on its own references
    # Внешние ключи остаются выключенными (умолчание SQLite): пересоздаваемая миграцией таблица не должна падать
    # на собственных ссылках
    engine = create_engine(f'sqlite:///{ProjectDirs.data_base_file}')
    with engine.connect() as connection:
        _configure(connection)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


run_migrations()
