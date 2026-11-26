"""
The module contains the project configuration: profile, directories, constants and web form settings.
Модуль содержит конфигурацию проекта: профиль, директории, константы и настройки веб-форм.

BASE_DIR: the project root, the base of all paths
PROFILE: the profile (environment variable `TELEGRAM_SAVER_PROFILE`): the name of the directory `profiles/<PROFILE>/`
         with all the data of one Telegram account
HOST, PORT: the address of the local web server
class ProjectDirs: directories and files of the profile (settings, session, database, media, export, cache)
class GlobalConst: constants of the project (limits, formats, labels, key names)
class DialogTypes(Enum): IDs and names of the dialog types in Telegram
class MessageFileTypes(Enum): names, types, extensions and signatures of message files
class TableNames: names of the database tables
class FormCfg: configurations of the web interface form controls
class TagsSorting: tag sorting options
"""

import os
from typing import Any
from dataclasses import dataclass
from pathlib import Path
from enum import Enum
from profiles import (CACHE_DIR_NAME, DATABASE_DIR_NAME, EXPORT_DIR_NAME, MEDIA_DIR_NAME, PROFILE_ENV_VAR,
                      PROFILES_DIR, list_profiles, read_profile)

# The project root: all paths are built from it, so the application works from any current directory
# Корень проекта: от него строятся все пути, поэтому приложение работает из любой текущей директории
BASE_DIR = Path(__file__).resolve().parent

# The profile of this run: the directory `profiles/<PROFILE>/` holds all the data of one Telegram account. It comes from
# the environment variable `TELEGRAM_SAVER_PROFILE` (the launcher `telegram_saver.py` sets it after the choice of the
# profile; with a direct `uvicorn web.main:app` it can be set by hand, PowerShell:
# `$env:TELEGRAM_SAVER_PROFILE='work'`),
# otherwise the only existing profile is taken. '' means that no profile is selected (see `ensure_profile_selected`).
# Профиль этого запуска: каталог `profiles/<PROFILE>/` хранит все данные одного аккаунта Telegram. Берется из переменной
# окружения `TELEGRAM_SAVER_PROFILE` (запускатель `telegram_saver.py` выставляет ее после выбора профиля; при прямом
# `uvicorn web.main:app` ее можно задать вручную, PowerShell: `$env:TELEGRAM_SAVER_PROFILE='work'`), иначе берется
# единственный существующий профиль. '' - профиль не выбран (см. `ensure_profile_selected`).
_existing_profiles = list_profiles()
PROFILE = read_profile(os.environ) or (_existing_profiles[0] if len(_existing_profiles) == 1 else '')


def ensure_profile_selected() -> None:
    """
    Raises an error if no profile is selected (the application must not create its data outside a profile).
    Выбрасывает ошибку, если профиль не выбран (приложение не должно создавать свои данные вне профиля).
    """

    if not PROFILE:
        raise RuntimeError('No profile selected: start the application with `python telegram_saver.py` or set '
                           f'{PROFILE_ENV_VAR} / Профиль не выбран: запустите `python telegram_saver.py` '
                           f'или задайте {PROFILE_ENV_VAR}')


# The address of the web server: the launcher listens on it and the request guard (`web/middleware.py`) accepts only
# requests addressed to it. The app is single-user and local, so it is never bound to a public interface.
# Адрес веб-сервера: на нем слушает запускатель, а защита запросов (`web/middleware.py`) принимает только запросы,
# адресованные ему. Приложение однопользовательское и локальное, поэтому к публичному интерфейсу оно не привязывается.
HOST = '127.0.0.1'
PORT = 5000


# The directory of the selected profile (a stub name if no profile is selected, so nothing is created outside
# `profiles/`)
# Каталог выбранного профиля (имя-заглушка, если профиль не выбран, чтобы ничего не создавалось вне `profiles/`)
_profile_dir = PROFILES_DIR / (PROFILE or '_not_selected')


@dataclass(frozen=True)
class ProjectDirs:
    """
    A class to hold the directory paths of the selected profile.
    Класс для хранения путей к каталогам выбранного профиля.
    All paths are absolute (built from the project root).
    Все пути абсолютные (строятся от корня проекта).
    Attributes:
        profile_dir (Path): Directory of the profile (`profiles/<PROFILE>/`)
        media_dir_name (str): Name of the media directory, also the URL prefix of the media files
                              (`/media_storage/...`);
                              the prefix does not depend on the profile, so the links in the database stay valid
        media_dir (Path): Directory for storing downloaded media files from Telegram
        export_dir (Path): Directory for exporting messages to HTML files
        cache_dir_name (str): Name of the cache directory, also the URL prefix of the cached files (`/cache/...`)
        cache_dir (Path): Directory of the cache (previews, chat avatars); maintenance does not check it
        telegram_settings_file (Path): Telegram API settings file (`.env` of the profile)
        session_file (Path): Telethon session file without the extension (Telethon adds `.session`)
        profile_info_file (Path): `profile.json` (ID and name of the Telegram account of the profile)
        data_base_dir (Path): Directory for storing the SQLite database file and its backups
        data_base_file (Path): SQLite database file
    """

    profile_dir = _profile_dir
    media_dir_name = MEDIA_DIR_NAME
    media_dir = _profile_dir / media_dir_name
    export_dir = _profile_dir / EXPORT_DIR_NAME
    cache_dir_name = CACHE_DIR_NAME
    cache_dir = _profile_dir / cache_dir_name
    telegram_settings_file = _profile_dir / '.env'
    session_file = _profile_dir / 'telegram'
    profile_info_file = _profile_dir / 'profile.json'
    data_base_dir = _profile_dir / DATABASE_DIR_NAME
    data_base_file = data_base_dir / 'telegram_archive.db'


@dataclass(frozen=True)
class GlobalConst:
    """
    A class to hold constant values for the project.
    Класс для хранения констант проекта.
    """

    max_download_file_size = 50 * 2 ** 20  # 50 MB - Maximum file size for downloading from Telegram
    map_service = 'openstreetmap'  # Map of the links for locations: 'openstreetmap' or 'google' (see `media_text.MAP_URLS`)
    truncated_text_length = 175  # Maximum length of text to display in the web page
    truncated_title_length = 25  # Maximum length of dialog title to display in the web page
    tg_last_days_by_default = 30  # Default number of last days for the messages filter of the Telegram tab
    db_last_days_by_default = 30  # Default number of last days for the messages filter of the database tab
    message_datetime_format = '%d-%m-%Y %H:%M:%S'  # Format for displaying date and time for messages and details
    file_datetime_format = '%Y-%m-%d %H_%M_%S'  # Date and time format for file names
    saved_to_db_label = '✔ Saved'  # Label to indicate that a message has been saved to the database
    save_to_db_label = 'Save'  # Label for the checkbox to save a message to the database
    checked_in_db_label = ''  # '✔ Checked' # Not use now
    check_in_db_label = ''  # 'Check' # Not use now
    mess_group_id = 'message_group_id'  # Key name for message group ID in HTML templates
    select_in_telegram = 'select_in_telegram'  # Key name for message selection in Telegram for HTML templates
    select_in_database = 'select_in_database'  # Key name for message selection in database for HTML templates
    tag_filter_separator = ';'  # Separator for tags in the filter tags field
    no_tags_name = '(No tags)'  # Name of the special "tag" of the messages without tags (not stored, no real tag has it)
    no_tags_id = 0  # Value of its option in the list of all tags (the IDs of real tags start from 1)
    me_dialog_title = 'Saved Messages (Favorites)'  # Title for the "Saved Messages" dialog
    dialog_no_title = '<No Title>'  # Title for dialogs without a title
    status_list_max_items = 20  # Maximum number of list items (e.g. file names) shown in the status bar report
    maintenance_max_downloads = 100  # Maximum number of missing files that maintenance downloads in one run
    db_backup_keep = 10  # Number of the latest database backups that maintenance keeps (older ones are deleted)
    cache_max_age_days = 30  # Previews and videos in the cache older than this are deleted at the start
    avatar_parallel_downloads = 5  # Number of chat avatars downloaded from Telegram at the same time
    cache_avatars_dir = '_avatars'  # Subdirectory of the cache with the chat avatars (the cleaning does not touch it)


class DialogTypes(Enum):
    """
    The class holds the IDs and names of the dialog types in Telegram.
    Класс содержит ID и названия типов диалогов в Telegram.
    """

    CHANNEL = 1
    GROUP = 2
    USER = 3
    UNKNOWN = 4

    @staticmethod
    def get_type_name(is_channel: bool, is_group: bool, is_user: bool) -> str:
        """
        Returns the type name for a given dialog type.
        Возвращает название типа для заданного типа диалога.
        Attributes:
            is_channel (bool): True if the dialog is a channel
            is_group (bool): True if the dialog is a group
            is_user (bool): True if the dialog is a user
        Returns:
            str: The type name of the dialog
        """

        if is_channel:
            return DialogTypes.CHANNEL.name
        if is_group:
            return DialogTypes.GROUP.name
        if is_user:
            return DialogTypes.USER.name
        return DialogTypes.UNKNOWN.name


class MessageFileTypes(Enum):
    """
    The class contains the names, types, extensions, and signatures of message files.
    Класс содержит названия, типы, расширения и подписи файлов сообщений.
    """

    PHOTO = (1, 'Image', '.jpg', 'pho')
    IMAGE = (2, 'Image', '.jpg', 'img')
    VIDEO = (3, 'Video', '.mp4', 'vid')
    THUMBNAIL = (4, 'Image', '.jpg', 'vth')
    AUDIO = (5, 'Audio', '.mp4', 'aud')
    WEBPAGE = (6, 'Image', '.jpg', 'wpg')
    CONTENT = (7, 'Content', '.html', 'ctx')
    UNKNOWN = (10, 'Unknown', '.unk', 'unk')

    def __init__(self, type_id: int, alt_text: str, default_ext: str, sign: str):
        """
        Initializes the MessageFileTypes enum.
        Инициализация MessageFileTypes enum.
        Attributes:
            type_id (int): The ID of the file type.
            alt_text (str): The alternative text for the file type.
            default_ext (str): The default file extension for the file type.
            sign (str): The short sign for the file type.
        """

        self.type_id = type_id
        self.alt_text = alt_text
        self.default_ext = default_ext
        self.sign = sign

    @classmethod
    def get_file_type_by_type_id(cls, type_id: int) -> 'MessageFileTypes':
        """
        Returns the MessageFileTypes for a given file type_id.
        Возвращает MessageFileTypes для заданного type_id файла.
        Attributes:
            type_id (int): The ID of the file type.
        Returns:
            MessageFileTypes: The corresponding MessageFileTypes enum member.
        """

        result = MessageFileTypes.UNKNOWN
        for item in cls:
            if item.type_id == type_id:
                result = item
        return result

    def __repr__(self):
        """
        Returns a string representation of the MessageFileTypes enum.
        """
        return f'{self.__class__.__name__}.{self.name}'


@dataclass
class TableNames:
    """
    The class contains database tables names.
    Класс содержит имена таблиц базы данных.
    """

    dialogs = 'dialogs'
    dialog_types = 'dialog_types'
    message_groups = 'message_groups'
    files = 'files'
    file_types = 'file_types'
    tags = 'tags'
    message_group_tag_links = 'message_group_tag_links'


@dataclass
class FormCfg:
    """
    Configurations of form controls in the web interface that allow you to obtain the values of all forms using
    a single processing function.
    Конфигурации элементов управления форм в веб-интерфейсе, которые позволяют получать значения всех форм с помощью
    одной функции обработки.
    Attributes:
        tg_dialog_filter (dict): Telegram dialog filter form configuration
        tg_message_filter (dict): Telegram message filter form configuration
        db_message_filter (dict): Database message filter form configuration
        db_detail_tags (dict): Database tag control form configuration
        tg_checkbox_list (dict): Configuration of checkboxes Telegram messages list
        db_checkbox_list (dict): Configuration of checkboxes database messages list
    """

    # Telegram dialog filter form configuration / Конфигурация формы фильтра диалогов Telegram
    tg_dialog_filter = {'sorting_field': 'tg_sorting_field', 'sorting_order': 'tg_dial_sort_order',
                        'dialog_type': 'tg_dialog_type', 'dialog_title_query': 'tg_title_query',
                        'radio': ['sorting_field', 'sorting_order', 'dialog_type'],
                        'input': ['dialog_title_query']}
    # Telegram message filter form configuration / Конфигурация формы фильтра сообщений Telegram
    tg_message_filter = {'sorting_order': 'tg_mess_sort_order', 'date_from': 'tg_mess_date_from',
                         'date_to': 'tg_mess_date_to', 'message_query': 'tg_message_query',
                         'radio': ['sorting_order'],
                         'input': ['date_from', 'date_to', 'message_query']}
    # Database message filter form configuration / Конфигурация формы фильтра сообщений базы данных
    db_message_filter = {'dialog_select': 'db_dialog_select', 'sorting_field': 'db_mess_sort_field',
                         'sorting_order': 'db_mess_sort_order',
                         'date_from': 'db_mess_date_from', 'date_to': 'db_mess_date_to',
                         'message_query': 'db_message_query', 'tag_query': 'db_tag_query',
                         'tag_mode': 'db_tag_mode',
                         'radio': ['sorting_field', 'sorting_order', 'tag_mode'],
                         'input': ['date_from', 'date_to', 'message_query', 'tag_query'], 'select': ['dialog_select']}
    # Database tag control form configuration / Конфигурация формы управления тегов базы данных
    db_detail_tags = {'edit_tag_name': 'db_edit_tag_name', 'old_tag_name': 'db_old_tag_name',
                      'curr_message_tags': 'db_current_message_tags', 'all_detail_tags': 'db_all_detail_tags',
                      'tag_sorting_field': 'db_tag_sorting_field',
                      # The tag buttons act on the messages checked in the list of the database tab
                      # Кнопки тегов действуют на сообщения, отмеченные в списке вкладки БД
                      'db_checkbox_list': 'db-message-checkbox',
                      'input': ['edit_tag_name', 'old_tag_name'],
                      'select': ['curr_message_tags', 'all_detail_tags'], 'radio': ['tag_sorting_field'],
                      'checkbox_list': ['db_checkbox_list']}
    # Configuration of checkboxes Telegram messages list / Конфигурация чекбоксов списка сообщений Telegram
    tg_checkbox_list = {'tg_checkbox_list': 'tg-message-checkbox',
                        'checkbox_list': ['tg_checkbox_list']}
    # Configuration of checkboxes database messages list / Конфигурация чекбоксов списка сообщений базы данных
    db_checkbox_list = {'db_checkbox_list': 'db-message-checkbox',
                        'checkbox_list': ['db_checkbox_list']}

    @staticmethod
    def get_form_cfg(form_cfg: dict) -> dict:
        """
        Returns the configuration of controls of a given form for the form processing button.
        Возвращает конфигурацию элементов управления заданной формы для кнопки обработки формы.
        Attributes:
            form_cfg (dict): The form configuration dictionary.
        Returns:
            dict: The button configuration dictionary.
        """

        result: dict[str, list[Any]] = {'radio': [], 'input': [], 'select': [], 'checkbox': [],
                                        'checkbox_list': []}  # Default structure, do not change key names
        for key, value in result.items():
            if key == 'checkbox_list':
                for field_name in form_cfg.get(key) or []:
                    value.append({
                        'selector': f'input.{form_cfg[field_name]}',
                        'name': form_cfg[field_name]
                    })
            else:
                for field_name in form_cfg.get(key) or []:
                    value.append({'id': form_cfg[field_name], 'name': form_cfg[field_name]})
        return result


@dataclass
class TagsSorting:
    """
    The class contains tag sorting options.
    Класс содержит опции сортировки тегов.
    """

    NAME_ASC = {'field': 'name', 'order': 'asc'}
    NAME_DESC = {'field': 'name', 'order': 'desc'}
    USAGE_COUNT_ASC = {'field': 'usage_count', 'order': 'asc'}
    USAGE_COUNT_DESC = {'field': 'usage_count', 'order': 'desc'}
    CREATED_AT_ASC = {'field': 'created_at', 'order': 'asc'}
    CREATED_AT_DESC = {'field': 'created_at', 'order': 'desc'}


if __name__ == '__main__':
    pass
