from enum import Enum
import re
from datetime import datetime, timedelta
from pathlib import Path

# Set the profile for the project
PROFILE = 'dev_1'


# PROFILE = 'dev_2'
# PROFILE = 'prod'


class ProjectDirs:
    """
    A class to hold the directory paths for a project.
    """
    media_dir = r'media_storage'
    telegram_settings_file = Path('configs') / f'.env_{PROFILE}'
    data_base_file = Path('database') / f'telegram_archive_{PROFILE}.db'


class ProjectConst:
    """
    A class to hold constant values for the project.
    """
    max_download_file_size = 50 * 2 ** 10 * 2 ** 10  # 50 MB
    text_with_url_pattern = re.compile(r"\[(.*?)]\((.*?)\)")  # Regex pattern to match "[text](URL)"
    last_days_by_default = 30  # Default number of last days for messages filter
    message_datetime_format = '%d-%m-%Y %H:%M :%S'
    file_datetime_format = '%Y-%m-%d %H_%M_%S'
    saved_to_db_label = '✔ Saved to the DB'
    save_to_db_label = 'Save to the DB'
    mess_group_id = 'message_group_id'
    select_to_save = 'select_to_save_to_db'


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
    UNKNOWN = (6, 'Unknown', '.unk', 'unk')

    def __init__(self, type_id: int, alt_text: str, default_ext: str, sign: str):
        self.type_id = type_id
        self.alt_text = alt_text
        self.default_ext = default_ext
        self.sign = sign

    @staticmethod
    def get_file_type(self, file_type) -> int:
        """
        Returns the type ID for a given file type.
        """
        for member in self.__class__:
            if member.name == file_type:
                return member.type_id


class FieldNames:
    """
    Структуры для имен полей, используемых в шаблонах и запросах.
    """
    # DIALOG_INFO = {
    #     'id': 'dialog_id',
    #     'title': 'title',
    #     'user': 'username',
    #     'unread_count': 'unread_count',
    #     'last_message_date': 'last_message_date',
    #     'type_name': 'dialog_type_name',
    # }
    # DIALOG_SETTINGS = {
    #     'sort_field': 'sorting_field',
    #     'sort_order': 'sorting_order',
    #     'type_name': 'type_name',
    #     'title_query': 'title_query',
    # }
    # MESSAGE_GROUP_INFO = {
    #     'dialog_id': 'dialog_id',
    #     'sender_id': 'sender_id',
    #     'date': 'date_time',
    #     'text': 'text',
    #     'ids': 'ids',
    #     'files': 'files',
    #     'files_report': 'files_report',
    #     'selected': 'selected',
    # }
    # MESSAGE_SETTINGS = {
    #     'sort_order': 'sorting_order',
    #     'date_from': 'date_from',
    #     'date_to': 'date_to',
    #     'message_query': 'message_query',
    #     'date_from_default': (datetime.now() - timedelta(days=ProjectConst.last_days_by_default)).strftime('%d-%m-%Y'),
    # }
    # DETAILS_INFO = {
    #     'dialog_id': 'dialog_id',
    #     'mess_group_id': 'message_group_id',
    #     'date': 'date',
    #     'text': 'text',
    #     'files': 'files',
    #     'files_report': 'files_report',
    # }
    # MESSAGE_FILE_INFO = {
    #     'dialog_id': 'dialog_id',
    #     'message': 'message',
    #     'full_path': 'full_path',
    #     'web_path': 'web_path',
    #     'size': 'file_size',
    #     'alt_text': 'alt_text',
    #     'type': 'file_type',
    # }


class TableNames:
    messages = 'messages'
    dialogs = 'dialogs'
    dialog_types = 'dialog_types'
    groups = 'groups'
    files = 'files'
    file_types = 'file_types'
    tags = 'tags'
    group_tag_links = 'group_tag_links'


if __name__ == '__main__':
    pass
