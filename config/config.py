import re


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


if __name__ == '__main__':
    pass
