import re
from datetime import datetime, timedelta


class ProjectDirs:
    """
    A class to hold the directory paths for a project.
    """
    chats_media = r'chats_media'
    db_media_dir = fr'{chats_media}\database'
    cache_media_dir = fr'{chats_media}\cache'
    telegram_settings_file = r'config\.env'


class Constants:
    """
    A class to hold constant values for the project.
    """
    max_download_file_size = 10 * 2 ** 10 * 2 ** 10  # 10 MB
    text_with_url_pattern = re.compile(r"\[(.*?)]\((.*?)\)")  # Regex pattern to match "[text](URL)"
    last_days_by_default = 30  # Default number of last days for messages filter
    datetime_format = '%d-%m-%Y %H:%M :%S'
    saved_to_db_label="Saved to the DB"
    save_to_db_label = "Save to the DB"


class FieldNames:
    """
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
        'date': 'date',
        'ids': 'ids',
        'text': 'text',
        'photo': 'photo',
        'video': 'video',
        'document': 'document',
    }
    MESSAGE_SETTINGS = {
        'sort_order': 'sorting_order',
        'date_from': 'date_from',
        'date_to': 'date_to',
        'message_query': 'message_query',
        'date_from_default': (datetime.now() - timedelta(days=Constants.last_days_by_default)).strftime('%d/%m/%Y'),
    }
    DETAILS_INFO = {
        'dialog_id': 'dialog_id',
        'date': 'date',
        'text': 'text',
        'photo': 'photo',
        'video': 'video',
        'video_thumbnail': 'video_thumbnail',
        'audio': 'audio',
        'document': 'document',
    }


if __name__ == '__main__':
    pass
