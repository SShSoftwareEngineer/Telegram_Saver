from datetime import datetime
from enum import Enum
import re
from pathlib import Path
from typing import List, Optional

from dateutil.parser import parse

# Set the profile for the project
PROFILE = 'dev_1'

# PROFILE = 'dev_2'
# PROFILE = 'prod'

""" 
Classes.
Классы. 
"""


class ProjectDirs:
    """
    A class to hold the directory paths for a project.
    """
    media_dir = r'media_storage'
    telegram_settings_file = Path('configs') / f'.env_{PROFILE}'
    data_base_file = Path('database') / f'telegram_archive_{PROFILE}.db'


class GlobalConst:
    """
    A class to hold constant values for the project.
    """
    max_download_file_size = 50 * 2 ** 20  # 50 MB
    text_with_url_pattern = re.compile(r"\[(.*?)]\((.*?)\)")  # Regex pattern to match "[text](URL)"
    truncated_text_length = 150  # Maximum length of text to display in the web page
    last_days_by_default = 30  # Default number of last days for messages filter
    message_datetime_format = '%d-%m-%Y %H:%M :%S'  # Format for displaying date and time for messages and details
    file_datetime_format = '%Y-%m-%d %H_%M_%S'
    saved_to_db_label = '✔ Saved in the DB'  # Label to indicate that a message has been saved to the database
    save_to_db_label = 'Save to DB'  # Label for the checkbox to save a message to the database
    checked_in_db_label = '✔ Checked'
    check_in_db_label = 'Check'
    mess_group_id = 'message_group_id'
    select_to_save = 'select_to_save_to_db'
    tag_filter_separator = ';'  # Separator for tags in the filter tags field


class StatusMessages:
    """
    A class to hold status messages for the web interface.
    """
    operation: str = ''  # Current operation
    report_list: Optional[List[str]] = None  # Report messages
    messages: dict = {}  # Messages for the web interface

    def mess_update(self, operation: str, report: str, new_list: bool = False):
        """
        Sets the current status messages for the web interface.
        """
        if operation:
            self.operation = operation
        current_time = datetime.now().strftime('%H:%M:%S.%f')[:-3]  # Current time with milliseconds
        if new_list or self.report_list is None:
            self.report_list = []
        if report:
            report_string = f'{current_time} - {report}'
            self.report_list.append(report_string)
        # Формируем строку для тега в HTML формате для содержимого <select>
        select_string = ''
        if self.report_list:
            select_string = '\n'.join([f'<option>{current_report}</option>' for current_report in reversed(self.report_list)])
        self.messages = {'sb_operation': f'<strong>Operation: </strong>{self.operation}', 'sb_report': select_string}
        print(f'{current_time}  {self.operation} - {report}')  # Print the report message to the console


status_messages = StatusMessages()


class DialogTypes(Enum):
    """
    Enum for different dialog types.
    """
    Channel = 1
    Group = 2
    User = 3
    Unknown = 4

    @staticmethod
    def get_type_name(is_channel: bool, is_group: bool, is_user: bool) -> str:
        """
        Returns the type name for a given dialog type.
        """
        if is_channel:
            return DialogTypes.Channel.name
        elif is_group:
            return DialogTypes.Group.name
        elif is_user:
            return DialogTypes.User.name
        else:
            return DialogTypes.Unknown.name


class MessageFileTypes(Enum):
    """
    Constants for different types of message files.
    """
    PHOTO = (1, 'Image', '.jpg', 'pho')
    IMAGE = (2, 'Image', '.jpg', 'img')
    VIDEO = (3, 'Video', '.mp4', 'vid')
    THUMBNAIL = (4, 'Image', '.jpg', 'vth')
    AUDIO = (5, 'Audio', '.mp4', 'aud')
    WEBPAGE = (6, 'Image', '.jpg', 'wpg')
    CONTENT = (7, 'Content', '.html', 'cnt')
    UNKNOWN = (10, 'Unknown', '.unk', 'unk')

    def __init__(self, type_id: int, alt_text: str, default_ext: str, sign: str):
        """
        Initializes the MessageFileTypes enum.
        """
        self.type_id = type_id
        self.alt_text = alt_text
        self.default_ext = default_ext
        self.sign = sign

    @classmethod
    def get_file_type_by_type_id(cls, type_id: int) -> 'MessageFileTypes':
        """
        Returns the MessageFileTypes for a given file type_id.
        """
        for item in cls:
            if item.type_id == type_id:
                return item

    def __repr__(self):
        """
        Returns a string representation of the MessageFileTypes enum.
        """
        return f'{self.__class__.__name__}.{self.name}'


class TableNames:
    """
    Constants for database table names.
    """
    dialogs = 'dialogs'
    dialog_types = 'dialog_types'
    message_groups = 'message_groups'
    files = 'files'
    file_types = 'file_types'
    tags = 'tags'
    message_group_tag_links = 'message_group_tag_links'


class FormButtonCfg:
    """
    Constants for button configurations in the web interface.
    """
    tg_dialog_filter = {'sorting_field': 'tg_sorting_field', 'sorting_order': 'tg_dial_sort_order',
                        'dialog_type': 'tg_dialog_type', 'dialog_title_query': 'tg_title_query',
                        'radio': ['sorting_field', 'sorting_order', 'dialog_type'],
                        'input': ['dialog_title_query'],
                        'select': [], 'checkbox': []}
    tg_message_filter = {'sorting_order': 'tg_mess_sort_order', 'date_from': 'tg_mess_date_from',
                         'date_to': 'tg_mess_date_to', 'message_query': 'tg_message_query',
                         'radio': ['sorting_order'],
                         'input': ['date_from', 'date_to', 'message_query'],
                         'select': [], 'checkbox': []}
    db_message_filter = {'dialog_select': 'db_dialog_select', 'sorting_field': 'db_mess_sort_field',
                         'sorting_order': 'db_mess_sort_order',
                         'date_from': 'db_mess_date_from', 'date_to': 'db_mess_date_to',
                         'message_query': 'db_message_query', 'tag_query': 'db_tag_query',
                         'radio': ['sorting_field', 'sorting_order'],
                         'input': ['date_from', 'date_to', 'message_query', 'tag_query'],
                         'select': ['dialog_select'], 'checkbox': []}
    db_detail_tags = {'edit_tag_name': 'db_edit_tag_name', 'old_tag_name': 'db_old_tag_name',
                      'curr_message_tags': 'db_current_message_tags', 'all_detail_tags': 'db_all_detail_tags',
                      'tag_sorting_field': 'db_tag_sorting_field',
                      'input': ['edit_tag_name', 'old_tag_name'],
                      'select': ['curr_message_tags', 'all_detail_tags'],
                      'radio': ['tag_sorting_field'], 'checkbox': []}

    @staticmethod
    def get_form_button_cfg(form_cfg: dict) -> dict:
        """
        Returns the button configuration for a given form.
        """
        result = {'radio': [], 'input': [], 'select': [], 'checkbox': []}  # Default structure, do not change key names
        for key in result.keys():
            for field_name in form_cfg[key]:
                result[key].append({'id': form_cfg[field_name], 'name': form_cfg[field_name]})
        return result


class TagsSorting:
    """
    Constants for tag sorting options.
    """
    name_asc = {'field': 'name', 'order': 'asc'}
    name_desc = {'field': 'name', 'order': 'desc'}
    usage_count_asc = {'field': 'usage_count', 'order': 'asc'}
    usage_count_desc = {'field': 'usage_count', 'order': 'desc'}
    updated_at_asc = {'field': 'updated_at', 'order': 'asc'}
    updated_at_desc = {'field': 'updated_at', 'order': 'desc'}


""" 
Functions.
Функции. 
"""


def parse_date_string(date_str: str):
    """
    Parses a date string and returns a datetime object.
    """
    if not date_str:
        return None
    try:
        return parse(date_str, dayfirst=True)
    except (ValueError, OverflowError):
        return None


if __name__ == '__main__':
    pass
