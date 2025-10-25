"""
The module contains

model classes, functions, and constants for working with an SQLite database using SQLAlchemy.

HTTP_ERRORS: a dictionary containing descriptions of HTTP request errors
class Base(DeclarativeBase): a declarative class for creating tables in the database
class RawMessage(Base): a model class for original Telegram messages
class VacancyMessage(Base): a model class for vacancy messages
class StatisticMessage(Base): a model class for statistics messages
class ServiceMessage(Base): a model class for service messages
def export_data_to_excel(): a function for exporting data from the database to MS Excel file
session: a session object for working with the database
"""
from typing import Dict, List, Any
from dataclasses import dataclass
from pathlib import Path
from enum import Enum
import re

# Set the profile for the project
PROFILE = '_dev_1'


# PROFILE = '_dev_2'
# PROFILE = ''

@dataclass(frozen=True)
class ProjectDirs:
    """
    A class to hold the directory paths for a project. / Класс для хранения путей к директориям проекта.
    """
    # Directory for storing downloaded media files from Telegram / Директория для загруженных медиафайлов из Telegram
    media_dir = r'media_storage'
    # Directory for exporting messages to HTML files / Директория для экспорта сообщений в HTML и другие файлы
    export_dir = r'exported_messages'
    # Telegram API settings file / Файл с настройками API Telegram
    telegram_settings_file = Path('configs') / f'.env{PROFILE}'
    # Directory for storing the SQLite database file / Директория для хранения файла базы данных SQLite
    data_base_dir = Path('database')
    # SQLite database file / Файл базы данных SQLite
    data_base_file = Path(data_base_dir) / f'telegram_archive{PROFILE}.db'


@dataclass(frozen=True)
class GlobalConst:
    """
    A class to hold constant values for the project. / Класс для хранения констант проекта.
    """
    max_download_file_size = 50 * 2 ** 20  # 50 MB - Maximum file size for downloading from Telegram
    truncated_text_length = 175  # Maximum length of text to display in the web page
    truncated_title_length = 25  # Maximum length of dialog title to display in the web page
    last_days_by_default = 30  # Default number of last days for messages filter
    text_with_url_pattern = re.compile(r"\[(.*?)]\((.*?)\)")  # Regex pattern to match "[text](URL)"
    message_datetime_format = '%d-%m-%Y %H:%M :%S'  # Format for displaying date and time for messages and details
    file_datetime_format = '%Y-%m-%d %H_%M_%S'  # Date and time format for file names
    saved_to_db_label = '✔ Saved'  # Label to indicate that a message has been saved to the database
    save_to_db_label = 'Save'  # Label for the checkbox to save a message to the database
    checked_in_db_label = ''  # '✔ Checked' # Not use now
    check_in_db_label = ''  # 'Check' # Not use now
    mess_group_id = 'message_group_id'  # Key name for message group ID in HTML templates
    select_in_telegram = 'select_in_telegram'  # Key name for message selection in Telegram for HTML templates
    select_in_database = 'select_in_database'  # Key name for message selection in database for HTML templates
    tag_filter_separator = ';'  # Separator for tags in the filter tags field
    me_dialog_title = 'Saved Messages (Favorites)'  # Title for the "Saved Messages" dialog
    dialog_no_title = '<No Title>'  # Title for dialogs without a title


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
        Arguments:
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
    The class contains types and other characteristics of message files.
    Класс содержит типы и другие характеристики файлов сообщений.
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
        Arguments:
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
    Database tables names.
    Имена таблиц базы данных.
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
    Form controls configurations in the web interface.
    Конфигурации элементов управления форм в веб-интерфейсе.
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
                         'radio': ['sorting_field', 'sorting_order'],
                         'input': ['date_from', 'date_to', 'message_query', 'tag_query'], 'select': ['dialog_select']}
    # Database tag control form configuration / Конфигурация формы управления тегов базы данных
    db_detail_tags = {'edit_tag_name': 'db_edit_tag_name', 'old_tag_name': 'db_old_tag_name',
                      'curr_message_tags': 'db_current_message_tags', 'all_detail_tags': 'db_all_detail_tags',
                      'tag_sorting_field': 'db_tag_sorting_field',
                      'input': ['edit_tag_name', 'old_tag_name'],
                      'select': ['curr_message_tags', 'all_detail_tags'], 'radio': ['tag_sorting_field']}
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
        Arguments:
            form_cfg (dict): The form configuration dictionary.
        Returns:
            dict: The button configuration dictionary.
        """
        result: Dict[str, List[Any]] = {'radio': [], 'input': [], 'select': [], 'checkbox': [],
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
    UPDATED_AT_ASC = {'field': 'updated_at', 'order': 'asc'}
    UPDATED_AT_DESC = {'field': 'updated_at', 'order': 'desc'}


if __name__ == '__main__':
    pass
