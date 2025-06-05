import os.path
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from config.config import ProjectDirs, ProjectConst, FieldNames


def media_file_name(dialog_id: int, message_id: int, message_date: datetime, file_type: Optional[str],
                    file_ext: Optional[str]) -> str:
    """
    Формирует путь и имя файла для скачанных медиафайлов
    """
    # chat_name(id) / date / time / message_id type
    file_type_sign = 'unk'
    match file_type:
        case FieldNames.DETAILS_INFO.get('image'):
            file_type_sign = 'img'
        case FieldNames.DETAILS_INFO.get('video'):
            file_type_sign = 'vid'
        case FieldNames.DETAILS_INFO.get('video_thumbnail'):
            file_type_sign = 'vth'
        case FieldNames.DETAILS_INFO.get('audio'):
            file_type_sign = 'aud'
        case FieldNames.DETAILS_INFO.get('document'):
            file_type_sign = 'doc'
    file_name = (f'{message_date.strftime(ProjectConst.file_datetime_format)}_'
                 f'{dialog_id}_{message_id}_{file_type_sign}{file_ext}')
    return clean_file_path(file_name)


if __name__ == '__main__':
    pass
