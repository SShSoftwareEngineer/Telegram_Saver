"""
Profiles: a profile is a directory `profiles/<profile name>/` with all the data of one Telegram account (settings,
session, database, media, export, cache). The module has no project imports (the launcher uses it before
`config` is read, because `config` takes the profile when it is imported).
Профили: профиль - это каталог `profiles/<имя профиля>/` со всеми данными одного аккаунта Telegram (настройки, сессия,
база данных, медиа, экспорт, кэш). Модуль не импортирует модули проекта (запускатель использует его до чтения
`config`, потому что `config` берет профиль при своем импорте).

PROFILES_DIR: the directory with the profile directories
PROFILE_ENV_VAR: the environment variable that passes the profile to `config`
read_profile(): the profile from the environment
list_profiles(): the profile_names of the existing profiles
create_profile(): creates the directory of a new profile with the settings file from the template
choose_profile(): the profile of this run: argument, environment variable, the only profile or the menu
read_profile_info(), write_profile_info(): `profile.json` (the ID and the name of the account of the profile)
"""

import json
import re
import shutil
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import NoReturn

ROOT_DIR = Path(__file__).resolve().parent
PROFILES_DIR = ROOT_DIR / 'profiles'
SETTINGS_TEMPLATE = ROOT_DIR / '.env.example'
PROFILE_ENV_VAR = 'TELEGRAM_SAVER_PROFILE'
PROFILE_ARG = '--profile'
PROFILE_INFO_FILE = 'profile.json'
# The names of the directories of a profile (`config.ProjectDirs` builds the paths from them)
# Имена каталогов профиля (пути в `config.ProjectDirs` строятся из них)
DATABASE_DIR_NAME = 'database'
BACKUP_DIR_NAME = 'backup'  # Inside the database directory / Внутри каталога базы данных
MEDIA_DIR_NAME = 'media_storage'
EXPORT_DIR_NAME = 'exported_messages'
CACHE_DIR_NAME = 'cache'
PROFILE_SUBDIRS = (Path(DATABASE_DIR_NAME) / BACKUP_DIR_NAME, Path(MEDIA_DIR_NAME), Path(EXPORT_DIR_NAME),
                   Path(CACHE_DIR_NAME))
_NAME_PATTERN = re.compile(r'[A-Za-z0-9_-]+')


def is_valid_profile_name(profile_name: str) -> bool:
    """
    The profile name becomes a directory name, so only letters, digits, `_` and `-` are allowed (no path
    separators, dots).
    Имя профиля становится именем каталога, поэтому допустимы только буквы, цифры, `_` и `-` (без разделителей
    путей, точек).
    """
    return bool(_NAME_PATTERN.fullmatch(profile_name))


def read_profile(environ: Mapping[str, str]) -> str:
    """
    Returns the profile from the environment variable `TELEGRAM_SAVER_PROFILE` ('' if it is not set).
    Возвращает профиль из переменной окружения `TELEGRAM_SAVER_PROFILE` ('' если она не задана).
    Attributes:
        environ (Mapping[str, str]): The environment (`os.environ`)
    Returns:
        str: The profile name
    """

    profile = environ.get(PROFILE_ENV_VAR, '')
    if profile and not is_valid_profile_name(profile):
        raise ValueError(f'{PROFILE_ENV_VAR}={profile!r}: only letters, digits, "_" and "-" are allowed\n'
                         f'допустимы только буквы, цифры, "_" и "-"')
    return profile


def list_profiles(profiles_dir: Path = PROFILES_DIR) -> list[str]:
    """
    Returns the profile_names of the existing profiles (the subdirectories with a valid name) in alphabetical order.
    Возвращает имена существующих профилей (подкаталоги с допустимым именем) по алфавиту.
    """

    if not profiles_dir.is_dir():
        return []
    return sorted((path.name for path in profiles_dir.iterdir() if path.is_dir() and is_valid_profile_name(path.name)),
                  key=str.casefold)


def read_profile_info(profile_dir: Path) -> dict:
    """
    Returns the content of `profile.json` of the profile ({} if there is no file or it is broken).
    Возвращает содержимое `profile.json` профиля ({} если файла нет или он поврежден).
    """

    try:
        info = json.loads((profile_dir / PROFILE_INFO_FILE).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}
    return info if isinstance(info, dict) else {}


def write_profile_info(profile_dir: Path, user_id: int, name: str) -> None:
    """
    Writes the ID and the name of the Telegram account to `profile.json` of the profile.
    Записывает ID и имя аккаунта Telegram в `profile.json` профиля.
    """

    profile_dir.mkdir(parents=True, exist_ok=True)
    (profile_dir / PROFILE_INFO_FILE).write_text(
        json.dumps({'user_id': user_id, 'name': name}, ensure_ascii=False, indent=2), encoding='utf-8')


def create_profile(profile_name: str, profiles_dir: Path = PROFILES_DIR, template: Path = SETTINGS_TEMPLATE) -> Path:
    """
    Creates the directory of a new profile with its structure (`database/backup/`, `media_storage/`,
    `exported_messages/`, `cache/`) and the settings file `.env` copied from the template. The files (database, session,
    `profile.json`) are created by the application itself. If something fails, the half-made directory is removed, so
    the name stays free.
    Создает каталог нового профиля с его структурой (`database/backup/`, `media_storage/`, `exported_messages/`,
    `cache/`) и файлом настроек `.env`, скопированным из шаблона. Файлы (база данных, сессия, `profile.json`)
    приложение создает само. При ошибке недоделанный каталог удаляется, поэтому имя остается свободным.
    Attributes:
        profile_name (str): The name of the profile (the directory name)
        profiles_dir (Path): The directory with the profiles
        template (Path): The template of the settings file
    Returns:
        Path: The directory of the profile
    """

    if not is_valid_profile_name(profile_name):
        raise ValueError(f'{profile_name!r}: only letters, digits, "_" and "-" are allowed\n'
                         f'допустимы только буквы, цифры, "_" и "-"')
    profile_dir = profiles_dir / profile_name
    if profile_dir.exists():
        raise FileExistsError(f'Profile {profile_name!r} already exists\nПрофиль {profile_name!r} уже существует')
    profile_dir.mkdir(parents=True)
    try:
        for subdir in PROFILE_SUBDIRS:
            (profile_dir / subdir).mkdir(parents=True)
        shutil.copyfile(template, profile_dir / '.env')
    except OSError:
        shutil.rmtree(profile_dir, ignore_errors=True)
        raise
    return profile_dir


def profile_title(profile_name: str, profiles_dir: Path = PROFILES_DIR) -> str:
    """
    The profile name with the name of the account from `profile.json` if it is known: `work (Ivan Ivanov)`.
    Имя профиля с именем аккаунта из `profile.json`, если оно известно: `work (Иван Иванов)`.
    """

    account_name = read_profile_info(profiles_dir / profile_name).get('name')
    return f'{profile_name} ({account_name})' if account_name else profile_name


def _ask_new_profile(ask: Callable[[str], str], tell: Callable[[str], None], profiles_dir: Path) -> NoReturn:
    """
    Asks for the name of a new profile until it is valid and free, creates it and exits (the settings file has to be
    filled in first).
    Запрашивает имя нового профиля, пока оно не станет допустимым и свободным, создает профиль и завершает работу
    (сначала нужно заполнить файл настроек).
    """

    while True:
        profile_name = ask('Name of the new profile (letters, digits, "_", "-"; empty - cancel) / '
                           'Имя нового профиля (буквы, цифры, "_", "-"; пусто - отмена): ').strip()
        if not profile_name:
            raise SystemExit('Canceled / Отменено')
        try:
            create_profile(profile_name, profiles_dir)
        except (ValueError, FileExistsError) as error:
            tell(str(error))
            continue
        except OSError as error:
            raise SystemExit(f'Could not create the profile\nНе удалось создать профиль: {error}') from error
        settings_file = profiles_dir / profile_name / '.env'
        tell(f'Created {profiles_dir / profile_name}. Fill in {settings_file} and start the application again\n'
             f'Заполните {settings_file} и запустите приложение снова.')
        raise SystemExit(0)


def choose_profile(argv: Sequence[str], environ: Mapping[str, str], profiles_dir: Path = PROFILES_DIR,
                   ask: Callable[[str], str] = input, tell: Callable[[str], None] = print) -> str:
    """
    Chooses the profile of this run: the `--profile <profile name>` argument, the environment variable, the only
    existing profile, otherwise the menu of the existing profiles (alphabetical, with the account name) and the
    item for a new one. With no profiles it offers to create one. A new profile is only created, the application
    is not started.
    Выбирает профиль этого запуска: аргумент `--profile <имя профиля>`, переменная окружения, единственный
    существующий профиль, иначе меню существующих профилей (по алфавиту, с именем аккаунта) и пункт нового. Если
    профилей нет, предлагает создать. Новый профиль только создается, приложение не запускается.
    Attributes:
        argv (Sequence[str]): The command line arguments without the program name
        environ (Mapping[str, str]): The environment
        profiles_dir (Path): The directory with the profiles
        ask, tell: Input and output functions (replaced in tests)
    Returns:
        str: The name of an existing profile
    """

    profile_name = ''
    if PROFILE_ARG in argv:
        index = list(argv).index(PROFILE_ARG)
        profile_name = argv[index + 1] if index + 1 < len(argv) else ''
        if not profile_name:
            raise SystemExit(f'{PROFILE_ARG} needs a profile name\n{PROFILE_ARG} требует имя профиля')
    elif argv and argv[0].startswith(f'{PROFILE_ARG}='):
        profile_name = argv[0].split('=', 1)[1]
    profile_name = profile_name or read_profile(environ)
    profile_names = list_profiles(profiles_dir)
    if profile_name:
        if not is_valid_profile_name(profile_name) or profile_name not in profile_names:
            raise SystemExit(f'Profile {profile_name!r} not found in {profiles_dir}\n'
                             f'Профиль {profile_name!r} не найден')
        return profile_name
    if len(profile_names) == 1:
        return profile_names[0]
    if not profile_names:
        tell(f'No profiles in {profiles_dir}\nПрофилей нет в {profiles_dir}')
        return _ask_new_profile(ask, tell, profiles_dir)
    while True:
        tell('Profiles / Профили:')
        for number, item in enumerate(profile_names, 1):
            tell(f'  {number}. {profile_title(item, profiles_dir)}')
        tell('  0. New profile / Новый профиль')
        answer = ask('Choose a number / Выберите номер: ').strip()
        if answer == '0':
            return _ask_new_profile(ask, tell, profiles_dir)
        if answer.isdigit() and 1 <= int(answer) <= len(profile_names):
            return profile_names[int(answer) - 1]
        tell('Wrong choice / Неверный выбор')
