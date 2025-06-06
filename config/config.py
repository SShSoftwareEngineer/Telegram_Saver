import re
from collections import namedtuple
from datetime import datetime, timedelta


class ProjectDirs:
    """
    A class to hold the directory paths for a project.
    """
    media_dir = r'media_storage'
    telegram_settings_file = r'config\.env'
    data_base_name = 'telegram_archive'


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


FileTypeProperties = namedtuple('FileTypeProperties', ['type', 'default_ext', 'sign'])


class MessageFileTypes:
    """
    Constants for different types of message files.
    """
    PHOTO = FileTypeProperties('Image', '.jpg', 'img')
    IMAGE = FileTypeProperties('Image', '.jpg', 'img')
    VIDEO = FileTypeProperties('Video', '.mp4', 'vid')
    THUMBNAIL = FileTypeProperties('Image', '.jpg', 'vth')
    AUDIO = FileTypeProperties('Audio', '.mp4', 'aud')
    UNKNOWN = FileTypeProperties('Unknown', 'unk', '')


class FieldNames:
    """
    Структуры для имен полей, используемых в шаблонах и запросах.
    """
    DIALOG_INFO = {
        'id': 'dialog_id',
        'title': 'title',
        'user': 'username',
        'unread_count': 'unread_count',
        'last_message_date': 'last_message_date',
        'is_user': 'is_user',
        'is_group': 'is_group',
        'is_channel': 'is_channel',
    }
    DIALOG_SETTINGS = {
        'sort_field': 'sorting_field',
        'sort_order': 'sorting_order',
        'dialog_type': 'dialog_type',
        'title_query': 'title_query',
    }
    MESSAGE_GROUP_INFO = {
        'dialog_id': 'dialog_id',
        'sender_id': 'sender_id',
        'date': 'date_time',
        'ids': 'ids',
        'text': 'text',
        'files': 'files',
        'files_report': 'files_report',
        'selected': 'selected',
    }
    MESSAGE_SETTINGS = {
        'sort_order': 'sorting_order',
        'date_from': 'date_from',
        'date_to': 'date_to',
        'message_query': 'message_query',
        'date_from_default': (datetime.now() - timedelta(days=ProjectConst.last_days_by_default)).strftime('%d-%m-%Y'),
    }
    DETAILS_INFO = {
        'dialog_id': 'dialog_id',
        'mess_group_id': 'message_group_id',
        'date': 'date',
        'text': 'text',
        'files': 'files',
        'files_report': 'files_report',
    }
    MESSAGE_FILE_INFO = {
        'dialog_id': 'dialog_id',
        'message': 'message',
        'full_path': 'full_path',
        'web_path': 'web_path',
        'size': 'file_size',
        'type': 'file_type',
    }


class TableNames:
    messages = 'messages'
    dialogs = 'dialogs'
    groups = 'groups'
    files = 'files'
    file_types = 'file_types'
    tags = 'tags'
    tags_messages = 'tags_messages'

    if __name__ == '__main__':
        pass
